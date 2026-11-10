"""Replaceable model/advisor boundaries; no fake production implementations."""

import math
from dataclasses import dataclass
from typing import Any, Protocol

from project_backend.config import ProjectProfile, Settings
from project_backend.errors import AppError
from project_backend.providers import ExternalDataProvider
from project_backend.schemas import (
    AdviceRequest,
    AdvisoryReport,
    ForecastRequest,
    ForecastResponse,
    PredictionPoint,
)
from project_backend.validation import validate_records


class Predictor(Protocol):
    model_version: str

    def predict(self, records: list[dict[str, Any]]) -> list[float]:
        """Return one numeric prediction per canonical row in the same order."""
        ...


class Advisor(Protocol):
    def generate(self, forecast: ForecastResponse) -> AdvisoryReport:
        """Use trusted retrieved evidence; verify citations against that evidence."""
        ...


@dataclass
class ServiceRegistry:
    predictor: Predictor | None = None
    provider: ExternalDataProvider | None = None
    advisor: Advisor | None = None


def generate_forecast(
    request: ForecastRequest,
    profile: ProjectProfile,
    settings: Settings,
    services: ServiceRegistry,
) -> ForecastResponse:
    horizon = request.horizon_points or len(request.records)
    if horizon != len(request.records):
        raise AppError("horizon_mismatch", "Supply exactly one input row per horizon point.", 422)
    if horizon > settings.max_forecast_points:
        raise AppError(
            "horizon_too_large", f"Limit the horizon to {settings.max_forecast_points} points.", 422
        )

    data = validate_records(
        request.records,
        profile,
        mode="inference",
        max_records=settings.max_records,
        max_issues=settings.max_issues,
    )
    if not data.report.valid:
        raise AppError(
            "invalid_forecast_input",
            "Fix the input using the validation details.",
            422,
            [item.model_dump() for item in data.report.issues],
        )
    if profile.target_column is None:
        raise AppError(
            "target_not_configured", "Choose a numeric target in the project profile.", 503
        )
    if services.predictor is None:
        raise AppError(
            "model_not_configured",
            "No forecasting model is configured. "
            "Select data, evaluate a baseline, then register a predictor.",
            503,
        )

    try:
        values = services.predictor.predict(data.records)
    except Exception as exc:
        raise AppError(
            "prediction_failed", "Model inference failed. Review the configured adapter.", 503
        ) from exc

    target = profile.columns[profile.target_column]
    if len(values) != len(data.records):
        raise AppError(
            "invalid_model_output", "The model returned the wrong number of predictions.", 500
        )
    points: list[PredictionPoint] = []
    for index, (record, value) in enumerate(zip(data.records, values, strict=True), start=1):
        try:
            if isinstance(value, bool):
                raise ValueError
            prediction = float(value)
            if not math.isfinite(prediction):
                raise ValueError
            if target.minimum is not None and prediction < target.minimum:
                raise ValueError
            if target.maximum is not None and prediction > target.maximum:
                raise ValueError
        except (TypeError, ValueError, OverflowError) as exc:
            raise AppError(
                "invalid_model_output",
                "Predictions must be finite and within configured target bounds.",
                500,
            ) from exc
        points.append(
            PredictionPoint(
                row=index,
                timestamp=record.get(profile.timestamp_column)
                if profile.timestamp_column
                else None,
                prediction=prediction,
            )
        )

    return ForecastResponse(
        model_version=services.predictor.model_version,
        schema_version=profile.schema_version,
        target_column=profile.target_column,
        target_unit=target.unit,
        horizon_points=horizon,
        predictions=points,
        warnings=data.report.warnings,
    )


def generate_advice(
    request: AdviceRequest, profile: ProjectProfile, services: ServiceRegistry
) -> AdvisoryReport:
    if (
        request.forecast.schema_version != profile.schema_version
        or request.forecast.target_column != profile.target_column
    ):
        raise AppError(
            "forecast_schema_mismatch", "Use a forecast from the active project schema.", 422
        )
    if services.advisor is None:
        raise AppError(
            "advisor_not_configured",
            "No advisor is configured. "
            "Add verified retrieval and an advisory-only workflow after forecasting works.",
            503,
        )
    return AdvisoryReport.model_validate(services.advisor.generate(request.forecast))
