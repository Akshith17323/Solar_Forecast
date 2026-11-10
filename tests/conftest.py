from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from project_backend.api import create_app
from project_backend.config import ProjectProfile, Settings, load_profile
from project_backend.providers import load_csv

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def profile() -> ProjectProfile:
    return load_profile(ROOT / "config/project.yaml")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        profile_path=ROOT / "config/project.yaml",
        max_records=10_000,
        max_upload_bytes=2 * 1024 * 1024,
        max_forecast_points=168,
        max_issues=100,
        cors_origins=["http://localhost:8501"],
    )


@pytest.fixture
def history() -> list[dict]:
    return load_csv(ROOT / "data/sample/solar_history.csv")


@pytest.fixture
def future() -> list[dict]:
    return load_csv(ROOT / "data/sample/solar_future.csv")


@pytest.fixture
def client(settings: Settings, profile: ProjectProfile):
    with TestClient(create_app(settings=settings, profile=profile)) as test_client:
        yield test_client
