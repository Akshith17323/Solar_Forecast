"""Deterministic validation shared by HTTP endpoints and offline scripts."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from project_backend.config import ColumnRule, ProjectProfile
from project_backend.errors import AppError
from project_backend.schemas import DataMode, TimeRange, ValidationIssue, ValidationReport


@dataclass
class ValidatedData:
    records: list[dict[str, Any]]
    report: ValidationReport


def _parse_value(value: Any, rule: ColumnRule) -> Any:
    if rule.dtype == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError("Expected a finite number, not a boolean or structured value.")
        try:
            number = float(value)
        except (ValueError, OverflowError) as exc:
            raise ValueError("Expected a finite number.") from exc
        if not math.isfinite(number):
            raise ValueError("NaN and infinite values are not allowed.")
        if rule.minimum is not None and number < rule.minimum:
            raise ValueError(f"Value must be at least {rule.minimum} in the configured unit.")
        if rule.maximum is not None and number > rule.maximum:
            raise ValueError(f"Value must be at most {rule.maximum} in the configured unit.")
        return number
    if rule.dtype == "datetime":
        if isinstance(value, datetime):
            timestamp = value
        elif isinstance(value, str):
            try:
                timestamp = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(
                    "Use an ISO 8601 timestamp, for example 2026-01-01T08:00:00Z."
                ) from exc
        else:
            raise ValueError("Expected an ISO 8601 timestamp with a timezone offset.")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Timestamp needs Z or an explicit offset; naive times are rejected.")
        try:
            return timestamp.astimezone(UTC)
        except (ValueError, OverflowError) as exc:
            raise ValueError("Timestamp is outside the supported UTC datetime range.") from exc
    if rule.dtype == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        raise ValueError("Expected true or false.")
    if not isinstance(value, str):
        raise ValueError("Expected a string.")
    return value


def validate_records(
    records: list[dict[str, Any]],
    profile: ProjectProfile,
    *,
    mode: DataMode = "historical",
    max_records: int = 10_000,
    max_issues: int = 100,
) -> ValidatedData:
    if mode not in {"historical", "inference"}:
        raise ValueError("mode must be historical or inference.")
    if len(records) > max_records:
        raise AppError("too_many_records", f"Limit the request to {max_records} rows.", 413)

    issues: list[ValidationIssue] = []
    warnings: list[str] = []
    normalized: list[dict[str, Any]] = []
    columns_seen: set[str] = set()
    ignored_columns: set[str] = set()
    timestamps: list[datetime] = []
    timestamp_rows: list[int] = []
    seen_timestamps: set[datetime] = set()
    issue_count = 0

    def issue(code: str, message: str, row: int | None = None, column: str | None = None) -> None:
        nonlocal issue_count
        issue_count += 1
        if len(issues) < max_issues:
            issues.append(ValidationIssue(code=code, message=message, row=row, column=column))

    if not records:
        issue("empty_dataset", "Provide at least one data row.")

    for index, record in enumerate(records, start=1):
        mapped: dict[str, Any] = {}
        clean: dict[str, Any] = {}
        for original, value in record.items():
            name = profile.column_mapping.get(original, original)
            columns_seen.add(name)
            if name not in profile.columns:
                if profile.unknown_columns == "reject":
                    issue(
                        "unknown_column",
                        "Map this column in the profile or remove it.",
                        index,
                        name,
                    )
                else:
                    ignored_columns.add(name)
                continue
            if name in mapped:
                issue("column_collision", "Two input columns map to the same name.", index, name)
                continue
            mapped[name] = value

        if mode == "inference" and profile.target_column in mapped:
            issue(
                "target_in_inference",
                "Remove the target from future input to prevent accidental target leakage.",
                index,
                profile.target_column,
            )

        for name, rule in profile.columns.items():
            if mode == "inference" and name == profile.target_column:
                continue
            if name not in mapped:
                if rule.required:
                    issue("missing_column", "Required column is absent from this row.", index, name)
                continue
            value = mapped[name]
            if value is None or (isinstance(value, str) and not value.strip()):
                if rule.nullable:
                    clean[name] = None
                else:
                    issue(
                        "missing_value",
                        "Supply a value or configure a nullable policy.",
                        index,
                        name,
                    )
                continue
            try:
                clean[name] = _parse_value(value, rule)
            except ValueError as exc:
                issue("invalid_value", str(exc), index, name)

        timestamp = clean.get(profile.timestamp_column) if profile.timestamp_column else None
        if isinstance(timestamp, datetime):
            if timestamp in seen_timestamps:
                issue(
                    "duplicate_timestamp",
                    "Timestamps must be unique for this series.",
                    index,
                    profile.timestamp_column,
                )
            seen_timestamps.add(timestamp)
            timestamps.append(timestamp)
            timestamp_rows.append(index)
        normalized.append(clean)

    deltas = [
        (later - earlier).total_seconds()
        for earlier, later in zip(timestamps, timestamps[1:], strict=False)
    ]
    if any(delta <= 0 for delta in deltas):
        if mode == "inference":
            issue("timestamp_order", "Future timestamps must be strictly increasing.")
        else:
            warnings.append("Sort timestamps chronologically before splitting or training.")
    if profile.expected_interval_minutes is not None:
        expected_seconds = profile.expected_interval_minutes * 60
        for offset, delta in enumerate(deltas, start=1):
            if delta != expected_seconds:
                if mode == "inference":
                    issue(
                        "interval_mismatch",
                        "Supply every expected forecast interval in order.",
                        timestamp_rows[offset],
                        profile.timestamp_column,
                    )
                elif "Irregular intervals detected; review gaps before training." not in warnings:
                    warnings.append("Irregular intervals detected; review gaps before training.")
    if ignored_columns:
        warnings.append("Unconfigured columns were ignored and will not be passed to the model.")
    if profile.target_column and profile.columns[profile.target_column].unit is None:
        warnings.append("Target unit is undecided. Configure it before evaluation or deployment.")

    time_range = TimeRange(start=min(timestamps), end=max(timestamps)) if timestamps else None
    report = ValidationReport(
        valid=issue_count == 0,
        schema_version=profile.schema_version,
        row_count=len(records),
        columns=sorted(columns_seen),
        issues=issues,
        issues_truncated=issue_count > len(issues),
        warnings=warnings,
        time_range=time_range,
    )
    return ValidatedData(records=normalized, report=report)
