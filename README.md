# Solar Forecast / General ML Backend Starter

**Status: boilerplate and planning, not a completed forecasting system.**

This repository starts the engineering foundation for a public-API forecasting
application. The selected direction is **public APIs, any country**; current
research recommends **Elia's Belgian regional solar-generation estimates plus
Open-Meteo forecast weather**, initially predicting next-hour average power in MW.
The model, final ingestion/feature contract, and deployment platform are pending.
There is **one reusable backend**, with a solar example profile and a general
numeric-prediction example. No second copy of the backend is needed.

## Data sources and verdict

**Verdict: use Elia + Open-Meteo as the primary operational data sources.**
**NASA POWER is a supporting source** for historical solar-resource analysis and
retrospective weather validation. Source selection uses direct public APIs and
excludes Kaggle-sourced datasets.

**Proposed task:** forecast Belgium's next-hour average photovoltaic generation
estimate in **MW**, using recent generation estimates and weather forecasts
available at issue time, then evaluate against subsequently published estimates.

| Source | Role in this project | Official links |
|---|---|---|
| **Elia Open Data** | Historical and ongoing Belgian regional PV generation estimates; supplies the target and generation history | [Live feed: `ods210`](https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods210), [recent history: `ods209`](https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods209), [legacy history: `ods032`](https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods032) |
| **Open-Meteo / NOAA GFS** | Forecast irradiance, temperature, and cloud cover; supplies weather predictors | [Forecast API](https://open-meteo.com/en/docs), [Previous Runs archive](https://open-meteo.com/en/docs/previous-runs-api), [GFS documentation](https://open-meteo.com/en/docs/gfs-api) |
| **NASA POWER — supporting** | Satellite/model-derived historical solar radiation, temperature, and cloud data for resource analysis and retrospective comparisons | [API explorer](https://power.larc.nasa.gov/api/pages/#/), [Hourly API documentation](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/), [solar sources and latency](https://power.larc.nasa.gov/docs/methodology/data/sources_fluxes/) |

### How to use these sources

- **Elia:** select `region="Belgium"` and, in the new schema,
  `gridconnectiontype="Total"`. These are measured/upscaled regional estimates,
  not individual-plant meter readings. Source intervals are 15 minutes; live
  running averages can be provisional. The **2026-10-26 migration** changed
  historical `ods032.measured` to `ods209.measured_upscaled`; the current feed uses
  `ods210.measured`. Preserve source versions when joining history and live data.
- **Open-Meteo:** use forecast `temperature_2m`, `cloud_cover`, and
  `shortwave_radiation`, with the model pinned to `gfs_global`. Match the model and
  forecast-age policy between training and deployment. The initial reproducible
  proposal uses `_previous_day1` fields for both archived and current-date
  requests; moving to latest-run forecasts requires a matched evaluation.
- **NASA POWER:** relevant fields are `ALLSKY_SFC_SW_DWN`, `T2M`, and `CLOUD_AMT`.
  Its temporal products provide historical/lagged weather estimates, rather than
  the electrical-generation target or operational next-hour weather forecasts.
  Respect each field's availability delay, treat `-999` as missing,
  and read the response units: hourly and daily solar-radiation units differ.
  Request `time-standard=UTC` explicitly; the hourly default is Local Solar Time.

### Direct data examples

These links return JSON. Weather examples use **Brussels (50.85, 4.35)** as a
single-point access check; the national model needs a weather grid across Belgium.

- [Elia: latest non-null Belgium/Total generation estimates](https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods210/records?where=region%3D%22Belgium%22%20AND%20gridconnectiontype%3D%22Total%22%20AND%20measured%20is%20not%20null&order_by=datetime%20desc&limit=4)
- [Open-Meteo: latest GFS weather forecasts](https://api.open-meteo.com/v1/forecast?latitude=50.85&longitude=4.35&hourly=temperature_2m,cloud_cover,shortwave_radiation&models=gfs_global&timezone=GMT&forecast_days=2)
- [Open-Meteo: archived day1 GFS forecasts, July 1–2, 2025](https://previous-runs-api.open-meteo.com/v1/forecast?latitude=50.85&longitude=4.35&hourly=temperature_2m_previous_day1,cloud_cover_previous_day1,shortwave_radiation_previous_day1&models=gfs_global&timezone=GMT&start_date=2025-07-01&end_date=2025-07-02)
- [NASA POWER: historical hourly solar/weather data, July 1–2, 2025](https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=ALLSKY_SFC_SW_DWN,T2M,CLOUD_AMT&community=RE&longitude=4.35&latitude=50.85&start=20250701&end=20250702&format=JSON&time-standard=UTC)

**Verification on 2026-11-10:** Elia's downloaded 2024–2025 export contains
**70,176** quarter-hour rows, **69,888** non-null targets, and **17,256** complete
target hours before weather/lag matching. Same-day Elia access and live/archived
Open-Meteo requests were verified. NASA's historical example returned all three
variables for 48 hours; a November 1–10 hourly UTC probe had temperature through
November 8 but missing solar/cloud values. These are access and availability
checks, not model-accuracy results.

**Access notes:** the reviewed requests worked without API keys. Open-Meteo's
[free hosted API is for noncommercial use](https://open-meteo.com/en/pricing),
and its [CC BY 4.0 data require attribution](https://open-meteo.com/en/licence).
Elia metadata identifies the [Elia Open Data Licence](https://opendata.elia.be/pages/licence/);
its full terms and exact quotas remain to be confirmed because the terms page was
temporarily unavailable during review. Cache responses and record retrieval times
and revisions when implementing the collectors.

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

1. [Review the operational data recommendation and evidence](docs/DATASET_RESEARCH_AND_PROBLEM_STATEMENT.md).
2. [Record the remaining project decisions](docs/PROJECT_DECISIONS.md).
3. [Understand configuration and adapter extension points](docs/BACKEND_GUIDE.md).
4. [Publish to GitHub and optionally Kaggle](docs/PUBLISHING_GUIDE.md).

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
