from pathlib import Path

import pytest
from pydantic import ValidationError

from project_backend.config import ColumnRule, ProjectProfile, Settings, load_profile


def test_general_profile_has_no_solar_time_or_bounds_requirement():
    profile = load_profile(Path("config/general.example.yaml"))
    assert profile.timestamp_column is None
    assert profile.columns["target"].minimum is None


@pytest.mark.parametrize(
    "rule",
    [
        {"dtype": "number", "minimum": 5, "maximum": 1},
        {"dtype": "string", "minimum": 0},
        {"dtype": "number", "maximum": float("inf")},
    ],
)
def test_invalid_column_bounds_rejected(rule):
    with pytest.raises(ValidationError):
        ColumnRule.model_validate(rule)


@pytest.mark.parametrize(
    "change",
    [
        {"target_column": "not_a_column"},
        {"column_mapping": {"original": "not_a_column"}},
        {"column_mapping": {"timestamp": "power_generation"}},
        {"timestamp_column": "temperature"},
        {"timestamp_column": None, "expected_interval_minutes": 60},
    ],
)
def test_invalid_profile_references_rejected(profile, change):
    with pytest.raises(ValidationError):
        ProjectProfile.model_validate(profile.model_dump() | change)


def test_timestamp_cannot_be_optional_or_nullable(profile):
    data = profile.model_dump()
    data["columns"]["timestamp"]["nullable"] = True
    with pytest.raises(ValidationError):
        ProjectProfile.model_validate(data)


def test_profile_rejects_secret_fields_without_printing_values(profile):
    with pytest.raises(ValidationError) as error:
        ProjectProfile.model_validate(profile.model_dump() | {"api_key": "sensitive-value"})
    assert "sensitive-value" not in str(error.value)


def test_environment_selects_profile(monkeypatch):
    monkeypatch.setenv("APP_PROFILE_PATH", "config/general.example.yaml")
    assert Settings(_env_file=None).profile_path == Path("config/general.example.yaml")


@pytest.mark.parametrize("content", ["", "[]", "broken: ["])
def test_invalid_yaml_has_clear_failure(tmp_path, content):
    path = tmp_path / "profile.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        load_profile(path)
