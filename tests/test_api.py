from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from project_backend.api import create_app
from project_backend.config import load_profile
from project_backend.schemas import AdvisoryReport
from project_backend.services import ServiceRegistry


class TestOnlyPredictor:
    __test__ = False
    model_version = "test-only-v1"

    def predict(self, records):
        # Only an API-contract fixture, never a shipped forecasting baseline.
        assert all("power_generation" not in row for row in records)
        return [float(row.get("irradiance", row.get("feature_1", 0))) for row in records]


def configured_client(settings, profile, predictor=None, provider=None, advisor=None):
    return TestClient(
        create_app(
            settings=settings,
            profile=profile,
            services=ServiceRegistry(predictor=predictor, provider=provider, advisor=advisor),
        ),
        raise_server_exceptions=False,
    )


def test_liveness_and_adapter_status(client):
    response = client.get("/health")
    assert response.status_code == 200
    UUID(response.headers["X-Request-ID"])
    status = client.get("/api/v1/status").json()
    assert status["backend_ready"]
    assert not status["model_configured"]
    assert not status["provider_configured"]
    assert not status["advisor_configured"]


def test_profile_is_public_and_does_not_expose_environment(client):
    body = client.get("/api/v1/project").json()
    assert body["target_column"] == "power_generation"
    assert "profile_path" not in body
    assert "cors_origins" not in body


def test_json_and_csv_validation(client, history):
    response = client.post("/api/v1/data/validate", json={"records": history})
    assert response.status_code == 200
    assert response.json()["valid"]
    content = Path("data/sample/solar_history.csv").read_bytes()
    upload = client.post(
        "/api/v1/data/validate/csv", files={"file": ("../not-saved.csv", content, "text/csv")}
    )
    assert upload.status_code == 200
    assert upload.json()["valid"]


def test_inference_upload(client):
    response = client.post(
        "/api/v1/data/validate/csv?mode=inference",
        files={"file": ("future.csv", Path("data/sample/solar_future.csv").read_bytes())},
    )
    assert response.status_code == 200
    assert response.json()["valid"]


def test_validation_report_not_success_claim_for_bad_data(client):
    response = client.post("/api/v1/data/validate", json={"records": [{}]})
    assert response.status_code == 200
    assert not response.json()["valid"]


def test_invalid_request_redacts_inputs_and_logs(client, caplog):
    sensitive = "credential-that-must-not-be-echoed"
    response = client.post("/api/v1/data/validate", json={"records": sensitive})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert sensitive not in response.text
    assert sensitive not in caplog.text


def test_csv_upload_limit(settings, profile):
    settings.max_upload_bytes = 4
    with configured_client(settings, profile) as client:
        response = client.post(
            "/api/v1/data/validate/csv", files={"file": ("x.csv", b"value\n12\n")}
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"


def test_forecast_is_explicitly_unconfigured(client, future):
    response = client.post("/api/v1/forecast", json={"records": future})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_not_configured"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_forecast_rejects_target_before_calling_model(client, history):
    response = client.post("/api/v1/forecast", json={"records": history})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_forecast_input"


def test_forecast_horizon_requires_matching_inputs(client, future):
    response = client.post("/api/v1/forecast", json={"records": future, "horizon_points": 24})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "horizon_mismatch"


def test_registered_predictor_receives_canonical_rows(settings, profile, future):
    with configured_client(settings, profile, predictor=TestOnlyPredictor()) as client:
        response = client.post("/api/v1/forecast", json={"records": future, "horizon_points": 4})
    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == "test-only-v1"
    assert [point["prediction"] for point in body["predictions"]] == [180, 350, 550, 650]
    assert body["predictions"][0]["timestamp"].startswith("2026-01-02T08:00:00")


@pytest.mark.parametrize("values", [[], [float("nan")] * 4, [-1] * 4, [True] * 4, ["bad"] * 4])
def test_invalid_model_output_is_not_returned(settings, profile, future, values):
    class InvalidPredictor:
        model_version = "test-invalid"

        def predict(self, records):
            return values

    with configured_client(settings, profile, predictor=InvalidPredictor()) as client:
        response = client.post("/api/v1/forecast", json={"records": future})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "invalid_model_output"


def test_model_exception_is_sanitized(settings, profile, future, caplog):
    class FailingPredictor:
        model_version = "test-failing"

        def predict(self, records):
            raise RuntimeError("sensitive-provider-credential")

    with configured_client(settings, profile, predictor=FailingPredictor()) as client:
        response = client.post("/api/v1/forecast", json={"records": future})
    assert response.status_code == 503
    assert "sensitive-provider-credential" not in response.text + caplog.text


def test_provider_is_unconfigured_without_network_calls(client):
    response = client.post("/api/v1/data/provider/validate", json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_not_configured"


def test_injected_provider_uses_same_validator(settings, profile, history):
    class TestOnlyProvider:
        def fetch_records(self, parameters):
            assert parameters == {"source_version": "test"}
            return history

    with configured_client(settings, profile, provider=TestOnlyProvider()) as client:
        response = client.post(
            "/api/v1/data/provider/validate", json={"parameters": {"source_version": "test"}}
        )
    assert response.status_code == 200
    assert response.json()["valid"]


def test_unexpected_provider_error_is_sanitized(settings, profile, caplog):
    class FailingProvider:
        def fetch_records(self, parameters):
            raise RuntimeError("secret-in-provider-error")

    with configured_client(settings, profile, provider=FailingProvider()) as client:
        response = client.post("/api/v1/data/provider/validate", json={})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret-in-provider-error" not in response.text + caplog.text


def test_advisor_unconfigured_and_schema_guard(settings, profile, future):
    with configured_client(settings, profile, predictor=TestOnlyPredictor()) as client:
        forecast = client.post("/api/v1/forecast", json={"records": future}).json()
        response = client.post("/api/v1/advice", json={"forecast": forecast})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "advisor_not_configured"
        forecast["schema_version"] = "other-schema"
        mismatch = client.post("/api/v1/advice", json={"forecast": forecast})
        assert mismatch.status_code == 422


def test_advisory_schema_rejects_unknown_reference_ids():
    with pytest.raises(ValidationError):
        AdvisoryReport.model_validate(
            {
                "summary": "Test-only report",
                "recommendations": [
                    {"action": "Example", "rationale": "Test", "reference_ids": ["missing"]}
                ],
                "assumptions": [],
                "limitations": [],
                "references": [],
            }
        )


def test_general_numeric_prediction_has_no_timestamp_requirement(settings):
    profile = load_profile(Path("config/general.example.yaml"))
    with configured_client(settings, profile, predictor=TestOnlyPredictor()) as client:
        response = client.post(
            "/api/v1/forecast", json={"records": [{"feature_1": -2, "category": "x"}]}
        )
    assert response.status_code == 200
    assert response.json()["predictions"][0]["timestamp"] is None
    assert response.json()["predictions"][0]["prediction"] == -2


def test_unknown_route_has_consistent_error_shape(client):
    response = client.get("/missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"
