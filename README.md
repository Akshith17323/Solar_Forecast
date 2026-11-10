# Solar Forecast / General ML Backend Starter

**Status: boilerplate and planning, not a completed forecasting system.**

This repository starts the engineering foundation while the problem statement,
dataset/API, target, units, model, and deployment platform are still undecided.
There is **one reusable backend**, with a solar example profile and a general
numeric-prediction example. No second copy of the backend is needed.

## What works now

- FastAPI backend with interactive API documentation at `/docs`.
- Typed YAML profiles and environment-based settings.
- CSV and JSON-record validation with actionable errors.
- Explicit column mapping, finite-number/bounds checks, timezone-aware UTC
  normalization, duplicate-time checks, and optional interval checks.
- Separate historical/inference contracts; future target columns are rejected.
- Replaceable data-provider, predictor, and advisor interfaces.
- Optional Streamlit shell, offline validation script, synthetic fixtures, tests,
  and a GitHub Actions workflow.

**Not implemented yet:** real data ingestion, provider-specific unit conversion,
snapshot/Parquet pipelines, feature engineering, training/evaluation, artifact
loading, calibrated uncertainty, RAG/LangGraph, authentication, or public hosting.
Model/provider/advisor endpoints return an explicit `503 ..._not_configured` until
their adapters are registered. The sample data is synthetic and proves no accuracy.

## Run locally

Run commands from this repository's root. Supported Python: **3.11–3.13**;
the default is 3.11. Use a virtual environment rather than the system Python.

### Recommended: uv

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if needed:

```bash
brew install uv
```

```bash
uv sync --frozen --extra dev --extra ui
cp .env.example .env
uv run uvicorn project_backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/docs>. In a **second terminal**, from the same folder:

```bash
uv run streamlit run app.py
```

The UI normally opens at <http://localhost:8501>. No API key is required to run
validation. Copy `.env.example` only if `.env` does not already exist.

### Alternative: pip

With Python 3.11 already installed:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,ui]"
python -m uvicorn project_backend.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, activate `.venv` and run `python -m streamlit run app.py`.
`uv.lock` is the reproducible dependency lock; the pip alternative resolves the
compatible version ranges in `pyproject.toml`.

## Try the scaffold

Offline validation:

```bash
uv run python -m scripts.validate_data data/sample/solar_history.csv
uv run python -m scripts.validate_data data/sample/solar_future.csv --mode inference
```

HTTP validation:

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/data/validate/csv?mode=historical' \
  -F 'file=@data/sample/solar_history.csv'
```

Forecast contract check:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/forecast \
  -H 'Content-Type: application/json' \
  --data-binary @data/sample/forecast_request.json
```

The last command **intentionally returns HTTP 503, `model_not_configured`**.
`horizon_points` counts input rows; it does not imply hours until frequency is
agreed. No production predictor or fake demo predictor is bundled.

## Use it for a general project

The core in `src/project_backend/` contains no hard-coded solar fields. Change the
profile, then implement the chosen adapters without rewriting the API shell.

```bash
uv run python -m scripts.validate_data data/sample/general_tabular.csv \
  --profile config/general.example.yaml
```

Start the API with that profile instead:

```bash
APP_PROFILE_PATH=config/general.example.yaml uv run uvicorn project_backend.main:app \
  --reload --host 127.0.0.1 --port 8000
```

This general example has no timestamp requirement. It supports **numeric outputs**;
classification or other output types require extending the response contract first.

## Main endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Process liveness, not proof of model readiness |
| `GET /api/v1/status` | Which adapters are configured |
| `GET /api/v1/project` | Public, non-secret schema/profile |
| `POST /api/v1/data/validate` | Validate JSON records |
| `POST /api/v1/data/validate/csv` | Validate an uploaded CSV; does not persist it |
| `POST /api/v1/data/provider/validate` | Extension point for a trusted, configured API adapter |
| `POST /api/v1/forecast` | Validate future input and call the selected predictor |
| `POST /api/v1/advice` | Extension point for evidence-grounded advisory reports |

## Structure

```text
app.py                         Optional Streamlit client
config/                        Solar and general example profiles
src/project_backend/
  api.py                       App factory, routes, errors, request IDs
  config.py                    Settings and typed profiles
  schemas.py                   Request/response contracts
  providers.py                 CSV loader and external API interface
  validation.py                Shared deterministic input validation
  services.py                  Predictor/advisor interfaces and orchestration
  main.py                      Default API entry point
scripts/validate_data.py       Offline CSV validation
data/sample/                   Documented synthetic fixtures
data/{raw,interim,processed}/  Ignored local/generated data
artifacts/                     Ignored generated model/metric artifacts
tests/                         Offline unit and API contract tests
notebooks/                     Kaggle-compatible planning/inspection starter
publishing/kaggle/             Safe-to-edit publishing metadata templates
docs/                          Backend, decisions, and publishing guides
.github/workflows/ci.yml       Lint, format, and tests
```

Existing planning documents are preserved:
[project roadmap](PROJECT_CONTEXT_AND_TASKS.md),
[scope notes](Key_points.md), and
[ML/MLOps lifecycle](ML_AND_MLOPS_LIFECYCLE.md).
Their earlier recommendations are not enforced as final decisions by this scaffold.

## Check the code

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Tests use synthetic local fixtures and test-only adapters, not live services.

## Documentation and next steps

1. [Record the open project decisions](docs/PROJECT_DECISIONS.md).
2. [Understand configuration and adapter extension points](docs/BACKEND_GUIDE.md).
3. [Publish to GitHub and optionally Kaggle](docs/PUBLISHING_GUIDE.md).

**Recommended submission:** GitHub repository + hosted app + demo video. Kaggle is
an optional notebook/data showcase, not a replacement for a backend host. Nothing
has been pushed, publicly uploaded, or deployed by generating this scaffold.

## Safety and licensing

- Keep secrets in `.env` locally and a secret manager when hosted.
- Never upload the whole repository to Kaggle; use a reviewed staging folder.
- No authentication/rate limiting is implemented. Keep development bound to
  localhost; add authorization, proxy-level body limits, and deployment safeguards
  before allowing public uploads or paid/provider-backed requests.
- Setting `APP_ENV=production` does not implement these protections.
- No project license has been selected. Review third-party data/document rights
  and choose a license for your own code before public redistribution.
- The original supplied PDF is preserved locally but ignored by Git until its
  redistribution rights are checked.
# Solar_Forecast
