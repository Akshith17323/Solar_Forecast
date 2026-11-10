"""FastAPI application factory, with explicit dependency injection for adapters."""

import logging
from time import perf_counter
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from project_backend import __version__
from project_backend.config import ProjectProfile, Settings, load_profile
from project_backend.errors import AppError
from project_backend.providers import parse_csv_bytes
from project_backend.schemas import (
    AdviceRequest,
    AdvisoryReport,
    DataMode,
    ErrorDetail,
    ErrorResponse,
    ForecastRequest,
    ForecastResponse,
    ProviderRequest,
    ServiceStatus,
    ValidationReport,
    ValidationRequest,
)
from project_backend.services import ServiceRegistry, generate_advice, generate_forecast
from project_backend.validation import validate_records

logger = logging.getLogger("uvicorn.error")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_profile(request: Request) -> ProjectProfile:
    return request.app.state.profile


def get_services(request: Request) -> ServiceRegistry:
    return request.app.state.services


SettingsDep = Annotated[Settings, Depends(get_settings)]
ProfileDep = Annotated[ProjectProfile, Depends(get_profile)]
ServicesDep = Annotated[ServiceRegistry, Depends(get_services)]


def _error_response(
    request: Request,
    code: str,
    message: str,
    status_code: int,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details or []), request_id=request_id
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers={"X-Request-ID": request_id},
    )


def create_app(
    settings: Settings | None = None,
    profile: ProjectProfile | None = None,
    services: ServiceRegistry | None = None,
) -> FastAPI:
    settings = settings or Settings()
    profile = profile or load_profile(settings.profile_path)
    services = services or ServiceRegistry()
    app = FastAPI(
        title=profile.project_name,
        version=__version__,
        description="Planning scaffold: no dataset, trained model or live API is bundled.",
    )
    app.state.settings = settings
    app.state.profile = profile
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        request.state.request_id = str(uuid4())
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info(
            "request_completed request_id=%s method=%s status=%s duration_ms=%.1f",
            request.state.request_id,
            request.method,
            response.status_code,
            (perf_counter() - started) * 1000,
        )
        return response

    @app.exception_handler(AppError)
    async def application_error(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(request, exc.code, exc.message, exc.status_code, exc.details)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"location": list(item["loc"]), "message": item["msg"], "type": item["type"]}
            for item in exc.errors()[: settings.max_issues]
        ]
        return _error_response(
            request, "invalid_request", "Check the request against /docs.", 422, details
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return _error_response(
            request, "http_error", "Requested route or method is unavailable.", exc.status_code
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "request_failed request_id=%s exception_type=%s",
            getattr(request.state, "request_id", "unknown"),
            type(exc).__name__,
        )
        return _error_response(
            request, "internal_error", "Unexpected backend error. Check service configuration.", 500
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/status", response_model=ServiceStatus)
    def status(active: ProfileDep, registry: ServicesDep) -> ServiceStatus:
        return ServiceStatus(
            model_configured=registry.predictor is not None,
            provider_configured=registry.provider is not None,
            advisor_configured=registry.advisor is not None,
            project_status=active.status,
        )

    @app.get("/api/v1/project", response_model=ProjectProfile)
    def project(active: ProfileDep) -> ProjectProfile:
        return active

    @app.post("/api/v1/data/validate", response_model=ValidationReport)
    def validate_json(
        payload: ValidationRequest, active: ProfileDep, limits: SettingsDep
    ) -> ValidationReport:
        return validate_records(
            payload.records,
            active,
            mode=payload.mode,
            max_records=limits.max_records,
            max_issues=limits.max_issues,
        ).report

    @app.post("/api/v1/data/validate/csv", response_model=ValidationReport)
    async def validate_csv(
        file: Annotated[UploadFile, File()],
        active: ProfileDep,
        limits: SettingsDep,
        mode: Annotated[DataMode, Query()] = "historical",
    ) -> ValidationReport:
        try:
            content = await file.read(limits.max_upload_bytes + 1)
        finally:
            await file.close()
        records = parse_csv_bytes(
            content, max_bytes=limits.max_upload_bytes, max_records=limits.max_records
        )
        return validate_records(
            records, active, mode=mode, max_records=limits.max_records, max_issues=limits.max_issues
        ).report

    @app.post("/api/v1/data/provider/validate", response_model=ValidationReport)
    def validate_provider(
        payload: ProviderRequest,
        active: ProfileDep,
        limits: SettingsDep,
        registry: ServicesDep,
    ) -> ValidationReport:
        if registry.provider is None:
            raise AppError(
                "provider_not_configured", "Select a data API and register its adapter first.", 503
            )
        records = registry.provider.fetch_records(payload.parameters)
        return validate_records(
            records,
            active,
            mode=payload.mode,
            max_records=limits.max_records,
            max_issues=limits.max_issues,
        ).report

    @app.post("/api/v1/forecast", response_model=ForecastResponse)
    def forecast(
        payload: ForecastRequest,
        active: ProfileDep,
        limits: SettingsDep,
        registry: ServicesDep,
    ) -> ForecastResponse:
        return generate_forecast(payload, active, limits, registry)

    @app.post("/api/v1/advice", response_model=AdvisoryReport)
    def advice(payload: AdviceRequest, active: ProfileDep, registry: ServicesDep) -> AdvisoryReport:
        return generate_advice(payload, active, registry)

    return app
