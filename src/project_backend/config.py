"""Typed, provider-independent project configuration."""

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    profile_path: Path = Path("config/project.yaml")
    env: Literal["development", "test", "production"] = "development"
    max_upload_bytes: int = Field(default=2 * 1024 * 1024, gt=0)
    max_records: int = Field(default=10_000, gt=0)
    max_forecast_points: int = Field(default=168, gt=0)
    max_issues: int = Field(default=100, gt=0)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:8501", "http://127.0.0.1:8501"]
    )


class ClientSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    backend_url: str = "http://127.0.0.1:8000"


class ColumnRule(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, hide_input_in_errors=True)

    dtype: Literal["number", "string", "datetime", "boolean"]
    required: bool = True
    nullable: bool = False
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def check_bounds(self) -> Self:
        if self.dtype != "number" and (self.minimum is not None or self.maximum is not None):
            raise ValueError("Only numeric columns can have minimum/maximum bounds.")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum.")
        return self


class ProjectProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    project_name: str = Field(min_length=1)
    status: Literal["planning", "prototype", "validated"] = "planning"
    problem_statement: str | None = None
    schema_version: str = Field(min_length=1)
    timestamp_column: str | None = None
    target_column: str | None = None
    expected_interval_minutes: int | None = Field(default=None, gt=0)
    unknown_columns: Literal["reject", "ignore"] = "reject"
    column_mapping: dict[str, str] = Field(default_factory=dict)
    columns: dict[str, ColumnRule] = Field(min_length=1)

    @model_validator(mode="after")
    def check_contract(self) -> Self:
        if any(not name.strip() for name in self.columns):
            raise ValueError("Column names must not be empty.")
        for name in (self.timestamp_column, self.target_column):
            if name is not None and name not in self.columns:
                raise ValueError("Timestamp/target columns must exist in columns.")
        if self.timestamp_column is not None:
            timestamp = self.columns[self.timestamp_column]
            if timestamp.dtype != "datetime" or not timestamp.required or timestamp.nullable:
                raise ValueError("The timestamp column must be required, non-nullable datetime.")
        if self.target_column is not None:
            target = self.columns[self.target_column]
            if target.dtype != "number" or not target.required or target.nullable:
                raise ValueError("This starter supports a required, non-nullable numeric target.")
        if self.expected_interval_minutes is not None and self.timestamp_column is None:
            raise ValueError("An expected interval requires a timestamp column.")
        for original, canonical in self.column_mapping.items():
            if not original.strip() or canonical not in self.columns:
                raise ValueError("Column mappings must point to a configured column.")
            if original in self.columns and original != canonical:
                raise ValueError("A mapping must not rename another canonical column.")
        return self


def load_profile(path: Path) -> ProjectProfile:
    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot load project profile: {path}. Check its path and YAML.") from exc
    if not isinstance(content, dict):
        raise ValueError("Project profile must be a YAML object, not an empty file or list.")
    return ProjectProfile.model_validate(content)
