"""Stable HTTP schemas, independent of any selected dataset or model library."""

from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

DataMode = Literal["historical", "inference"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)


class ValidationIssue(StrictSchema):
    code: str
    message: str
    row: int | None = None  # 1-based data row, excluding the CSV header.
    column: str | None = None


class TimeRange(StrictSchema):
    start: AwareDatetime
    end: AwareDatetime


class ValidationReport(StrictSchema):
    valid: bool
    schema_version: str
    row_count: int
    columns: list[str]
    issues: list[ValidationIssue]
    issues_truncated: bool = False
    warnings: list[str]
    time_range: TimeRange | None = None


class ValidationRequest(StrictSchema):
    records: list[dict[str, Any]]
    mode: DataMode = "historical"


class ProviderRequest(StrictSchema):
    parameters: dict[str, Any] = Field(default_factory=dict)
    mode: DataMode = "historical"


class ForecastRequest(StrictSchema):
    records: list[dict[str, Any]] = Field(min_length=1)
    horizon_points: int | None = Field(default=None, gt=0)


class PredictionPoint(StrictSchema):
    row: int
    timestamp: AwareDatetime | None = None
    prediction: float


class ForecastResponse(StrictSchema):
    model_version: str = Field(min_length=1)
    schema_version: str
    target_column: str
    target_unit: str | None
    horizon_points: int
    predictions: list[PredictionPoint]
    warnings: list[str]


class Reference(StrictSchema):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: HttpUrl | None = None


class Recommendation(StrictSchema):
    action: str
    rationale: str
    reference_ids: list[str] = Field(min_length=1)


class AdvisoryReport(StrictSchema):
    advisory_only: Literal[True] = True
    summary: str
    recommendations: list[Recommendation]
    assumptions: list[str]
    limitations: list[str]
    references: list[Reference]

    @model_validator(mode="after")
    def check_reference_ids(self) -> Self:
        ids = {reference.source_id for reference in self.references}
        if len(ids) != len(self.references):
            raise ValueError("Reference IDs must be unique.")
        if any(set(item.reference_ids) - ids for item in self.recommendations):
            raise ValueError("Every recommendation must cite a reference in the report.")
        return self


class AdviceRequest(StrictSchema):
    forecast: ForecastResponse


class ServiceStatus(StrictSchema):
    backend_ready: bool = True
    model_configured: bool
    provider_configured: bool
    advisor_configured: bool
    project_status: str


class ErrorDetail(StrictSchema):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class ErrorResponse(StrictSchema):
    error: ErrorDetail
    request_id: str
