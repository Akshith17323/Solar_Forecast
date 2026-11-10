from datetime import UTC
from pathlib import Path

import pytest

from project_backend.config import load_profile
from project_backend.errors import AppError
from project_backend.providers import load_csv
from project_backend.validation import validate_records


def codes(data):
    return {item.code for item in data.report.issues}


def test_valid_history_is_normalized_without_mutating_source(profile, history):
    data = validate_records(history, profile)
    assert data.report.valid
    assert data.report.row_count == 4
    assert data.records[0]["power_generation"] == 10.0
    assert data.records[0]["timestamp"].tzinfo == UTC
    assert isinstance(history[0]["timestamp"], str)
    assert data.report.warnings  # Units are deliberately undecided.


def test_future_does_not_require_target(profile, future):
    data = validate_records(future, profile, mode="inference")
    assert data.report.valid
    assert all("power_generation" not in row for row in data.records)


def test_target_is_rejected_and_never_forwarded_in_inference(profile, future):
    future[0]["power_generation"] = 99
    data = validate_records(future, profile, mode="inference")
    assert "target_in_inference" in codes(data)
    assert "power_generation" not in data.records[0]


def test_explicit_column_mapping_and_collision(profile, history):
    profile = profile.model_copy(update={"column_mapping": {"DATE_TIME": "timestamp"}})
    history[0]["DATE_TIME"] = history[0].pop("timestamp")
    assert validate_records(history, profile).report.valid
    history[0]["timestamp"] = history[0]["DATE_TIME"]
    assert "column_collision" in codes(validate_records(history, profile))


@pytest.mark.parametrize("value", ["NaN", "inf", "-inf", "not_numeric", True, [], {}, -1])
def test_invalid_numeric_values(profile, history, value):
    history[0]["power_generation"] = value
    assert "invalid_value" in codes(validate_records(history, profile))


def test_naive_timestamp_not_assumed_utc(profile, history):
    history[0]["timestamp"] = "2026-01-01T08:00:00"
    assert "invalid_value" in codes(validate_records(history, profile))


def test_utc_conversion_overflow_is_a_validation_issue(profile, history):
    history[0]["timestamp"] = "0001-01-01T00:00:00+14:00"
    assert "invalid_value" in codes(validate_records(history, profile))


def test_timezone_offset_is_normalized(profile, history):
    history[0]["timestamp"] = "2026-01-01T13:30:00+05:30"
    data = validate_records(history, profile)
    assert data.report.valid
    assert data.records[0]["timestamp"].hour == 8


def test_duplicate_equivalent_utc_timestamp_rejected(profile, history):
    history[1]["timestamp"] = "2026-01-01T13:30:00+05:30"
    assert "duplicate_timestamp" in codes(validate_records(history, profile))


def test_history_order_warns_future_order_fails(profile, history, future):
    historical = validate_records(list(reversed(history)), profile)
    assert historical.report.valid
    assert any("chronologically" in item for item in historical.report.warnings)
    inference = validate_records(list(reversed(future)), profile, mode="inference")
    assert "timestamp_order" in codes(inference)


def test_configured_cadence_checks_gaps(profile, history, future):
    profile = profile.model_copy(update={"expected_interval_minutes": 60})
    del future[1]
    del history[1]
    assert "interval_mismatch" in codes(validate_records(future, profile, mode="inference"))
    historical = validate_records(history, profile)
    assert historical.report.valid
    assert any("Irregular" in item for item in historical.report.warnings)


def test_missing_required_and_unknown_columns(profile, history):
    del history[0]["power_generation"]
    history[0]["unmapped_source_column"] = "unused"
    data = validate_records(history, profile)
    assert {"missing_column", "unknown_column"} <= codes(data)


def test_ignored_fields_do_not_reach_model(profile, history):
    profile = profile.model_copy(update={"unknown_columns": "ignore"})
    history[0]["unmapped_source_column"] = "unused"
    data = validate_records(history, profile)
    assert data.report.valid
    assert "unmapped_source_column" not in data.records[0]
    assert any("ignored" in warning for warning in data.report.warnings)


def test_present_blank_optional_column_needs_nullable_policy(profile, history):
    history[0]["temperature"] = ""
    assert "missing_value" in codes(validate_records(history, profile))
    profile.columns["temperature"].nullable = True
    data = validate_records(history, profile)
    assert data.report.valid
    assert data.records[0]["temperature"] is None


def test_empty_input_and_truncated_issues_are_still_invalid(profile):
    assert "empty_dataset" in codes(validate_records([], profile))
    data = validate_records([{}, {}, {}], profile, max_issues=1)
    assert not data.report.valid
    assert len(data.report.issues) == 1
    assert data.report.issues_truncated


def test_general_tabular_profile_allows_negative_numeric_target():
    profile = load_profile(Path("config/general.example.yaml"))
    records = load_csv(Path("data/sample/general_tabular.csv"))
    records[0]["target"] = -4
    data = validate_records(records, profile)
    assert data.report.valid
    assert data.report.time_range is None


def test_record_limit(profile, history):
    with pytest.raises(AppError) as error:
        validate_records(history, profile, max_records=1)
    assert error.value.status_code == 413
