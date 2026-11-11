# API Data, Training, and MLOps Implementation Plan

**Status:** Planning
**Assumption:** The reader already understands ML concepts. This document records implementation decisions and execution order only.
**Related documents:** `Key_points.md`, `PROJECT_CONTEXT_AND_TASKS.md`

## 1. Decisions

1. Target **microgrid operators and solar-plant analysts** first.
2. Produce an hourly, next-24-hour forecast.
3. Obtain measured aggregate generation from a public plant/microgrid dataset, SCADA/EMS export, or authorized API.
4. Obtain weather and radiation inputs from an API.
5. Calculate solar geometry locally with `pvlib`; add plane-of-array features only when valid representative orientation metadata exists.
6. Save immutable API responses, then normalize them into versioned Parquet datasets.
7. Train only from a frozen dataset version—not directly from changing live endpoints.
8. Use archived forecasts at the production lead time for realistic evaluation.
9. Package preprocessing, features, post-processing, and predictor as one versioned artifact.
10. Train offline; production performs read-only artifact loading and inference.
11. Require manual model promotion for the first releases.
12. Keep a physical PV estimate and last known-good model as fallbacks.
13. Use one aggregate site/meter and exclude household roofs, sub-arrays, and multiple orientation groups from the MVP.

## 2. Data-source plan

### Generation target

Select one source in this order:

1. Licensed public dataset containing measured solar-plant or microgrid generation.
2. Authorized plant SCADA or microgrid EMS API/export.
3. Site meter or operator CSV export.
4. Simulated output for pipeline tests only; never use it as evidence of real-world accuracy.

Required target fields:

```text
site_id
timestamp
interval_minutes
power_generation_mw and/or energy_generation_mwh
rated_dc_capacity_mw
timezone
```

Useful installation metadata:

```text
latitude_deg
longitude_deg
site_elevation_m
representative_tilt_deg
representative_azimuth_deg
rated_ac_capacity_mw
mounting_type
tracking_type
commissioned_at
module_type
```

The MVP uses one aggregate generation signal. Treat tilt and azimuth as optional site-level representative values; do not model household roofs, separate array blocks, or mixed orientations initially.

### Weather source

Initial candidate: Open-Meteo, pending license/quota review.

Required fields:

```text
forecast_issued_at_utc
valid_at_utc
forecast_lead_hours
ghi_w_m2 or shortwave_radiation_w_m2
dni_w_m2
dhi_w_m2
cloud_cover_pct
temperature_c
relative_humidity_pct
wind_speed_m_s
surface_pressure_hpa
precipitation_mm
source_provider
source_model
retrieved_at_utc
```

Use:

- Historical/reanalysis weather for exploration and physical baselines.
- Archived forecasts or previous model runs for day-ahead training and evaluation.
- Live forecast endpoint for production inference.
- PVGIS as an installation-yield/physical-reference source.
- NASA POWER only as a reviewed reference or backup source.

Do not merge provider series without source flags and a documented harmonization rule.

## 3. Data storage contract

```text
data/
├── raw/
│   ├── generation/<source>/<snapshot-id>/
│   └── weather/<provider>/<endpoint>/<snapshot-id>/
├── interim/
│   ├── generation/<version>/*.parquet
│   └── weather/<version>/*.parquet
├── processed/
│   └── solar-site-day-ahead/<dataset-version>/
│       ├── training_dataset.parquet
│       ├── dataset_manifest.json
│       ├── data_quality.json
│       └── split_manifest.json
└── sample/
    └── licensed_demo_data.parquet
```

Raw API snapshots should include the original JSON/CSV response and request metadata. Never overwrite a snapshot.

### Snapshot metadata

```json
{
  "snapshot_id": "<provider>-<timestamp>-<hash>",
  "provider": "<provider>",
  "endpoint": "<endpoint>",
  "request_parameters": {},
  "retrieved_at_utc": "<timestamp>",
  "response_checksum": "<sha256>",
  "provider_dataset_or_model": "<identifier>",
  "license_reference": "<manifest-entry>",
  "extractor_code_commit": "<git-commit>"
}
```

### Dataset manifest

```json
{
  "dataset_name": "solar-site-day-ahead",
  "dataset_version": "1.0.0",
  "target": "energy_generation_mwh",
  "forecast_horizon_hours": 24,
  "sites": [],
  "date_range": {},
  "source_snapshot_ids": [],
  "row_count": 0,
  "schema_hash": "<hash>",
  "feature_version": "solar-features-v1",
  "split_version": "chronological-v1",
  "build_code_commit": "<git-commit>",
  "created_at_utc": "<timestamp>"
}
```

## 4. API ingestion pipeline

Implement provider adapters behind one interface:

```text
fetch_history(location, start, end, variables)
fetch_archived_forecast(location, issue_time, horizon, variables)
fetch_live_forecast(location, horizon, variables)
normalize(raw_response)
provider_metadata(raw_response)
```

Required behavior:

- Explicit connect/read timeouts.
- Bounded retries with exponential backoff and jitter.
- Handling for 429 and provider overload responses.
- Local response cache keyed by provider, endpoint, and normalized parameters.
- No API key values in logs or snapshot metadata.
- Request IDs and checksums.
- Schema/version checks before normalization.
- Unit conversion at the canonical boundary.
- UTC storage plus site timezone metadata.
- Structured failure result rather than silent missing values.

Suggested scripts:

```text
scripts/fetch_generation.py
scripts/fetch_weather_history.py
scripts/fetch_archived_forecasts.py
scripts/fetch_live_forecast.py
scripts/normalize_sources.py
```

## 5. Dataset build pipeline

Execution order:

1. Validate source schemas.
2. Convert timestamps to timezone-aware UTC.
3. Preserve local timezone as site metadata.
4. Normalize power, energy, radiation, temperature, pressure, and wind units.
5. Resample with variable-specific aggregation rules.
6. Remove exact duplicates and report conflicting duplicates.
7. Detect missing intervals and impossible values.
8. Apply documented target exclusions; do not interpolate long target gaps.
9. Join generation to weather by `site_id` and `valid_at_utc`.
10. Preserve `forecast_issued_at_utc` and `forecast_lead_hours`.
11. Calculate solar-position, clear-sky, and plane-of-array fields.
12. Add safe lags and shifted rolling features.
13. Apply capacity normalization when training across sites.
14. Write one deterministic Parquet dataset.
15. Generate data-quality, lineage, and split manifests.
16. Hash the output and assign a dataset version.

Suggested scripts:

```text
scripts/build_dataset.py
scripts/validate_dataset.py
scripts/create_splits.py
```

Dataset builds must be idempotent for identical source snapshots and configuration.

## 6. Feature contract

### Weather

- GHI/shortwave radiation.
- DNI and DHI.
- Total/low/mid/high cloud cover where available.
- Temperature, humidity, wind, pressure, and precipitation.
- Forecast lead time.

### Solar and installation

- Solar zenith/elevation/azimuth.
- Extraterrestrial irradiance.
- Air mass.
- Sunrise/sunset and daylight flag.
- Clear-sky GHI/DNI/DHI.
- Representative array angle of incidence when valid orientation metadata exists.
- Plane-of-array global/direct/diffuse irradiance.
- Representative site tilt and azimuth when available.
- DC system and AC inverter capacity.
- System age when supported.

### Temporal

- Hour sine/cosine.
- Day-of-year sine/cosine.
- Optional month/season for reporting or validated model use.

### Historical generation

- Previous interval.
- Same interval previous day.
- Shifted rolling mean/variance.
- Recent daily energy totals where available at prediction time.

Each feature must record:

```text
name
dtype
unit
source
calculation_version
availability_at_prediction_time
missing_value_policy
```

## 7. Training pipeline

Suggested entry points:

```text
scripts/train.py
scripts/tune.py
scripts/evaluate.py
scripts/package_model.py
scripts/register_model.py
```

Recommended run sequence:

```bash
python -m scripts.validate_dataset --dataset-version 1.0.0
python -m scripts.train --config config/model.yaml
python -m scripts.tune --config config/tuning.yaml
python -m scripts.evaluate --run-id <run-id>
python -m scripts.package_model --run-id <run-id>
python -m scripts.register_model --artifact <artifact-path> --stage candidate
```

### Baselines

- Previous-hour persistence.
- Same-hour previous-day persistence.
- Seasonal/hour average.
- Physical PV estimate.

### Initial candidates

- Ridge.
- Extra Trees or Random Forest.
- HistGradientBoostingRegressor.
- Residual correction over the physical estimate.

### Validation

- Frozen chronological test period.
- Expanding or rolling validation windows.
- Site holdout when claiming generalization to unseen microgrids or solar plants.
- Metrics by daylight, season, lead time, site, cloud regime, and capacity range.

### Required reported metrics

- MAE.
- RMSE.
- Capacity-normalized MAE/RMSE where capacity is known.
- Daily-energy error and bias.
- Baseline improvement.
- Artifact size and inference latency.

## 8. Experiment record

Track every run with MLflow or a structured local run registry.

Required fields:

```text
run_id
started_at_utc
code_commit
dataset_version
source_snapshot_ids
feature_version
split_version
model_class
hyperparameters
random_seed
validation_windows
metrics
artifact_path
artifact_checksum
status
notes
```

Failed and stopped tuning trials should also remain visible.

## 9. Model artifact contract

```text
artifacts/models/<model-name>/<model-version>/
├── pipeline.joblib
├── model_manifest.json
├── hyperparameters.yaml
├── input_schema.json
├── feature_schema.json
├── metrics.json
├── test_predictions.parquet
├── model_card.md
└── checksums.txt
```

The artifact must contain or reference:

- Preprocessing.
- Feature ordering.
- Predictor.
- Post-processing and physical bounds.
- Expected input schema and units.
- Dataset, feature, split, and code versions.
- Training and test periods.
- Baseline and champion metrics.
- Package versions.

Model stages:

```text
candidate → staging → production → archived
```

Production must reference an immutable version, never an unversioned `latest` file.

## 10. Promotion gates

A model can move to staging only if:

- [ ] Source licensing and attribution are recorded.
- [ ] Dataset schema and quality checks pass.
- [ ] Dataset/split/feature versions are present.
- [ ] Leakage tests pass.
- [ ] It beats the required baseline on chronological validation.
- [ ] No critical site/season/daylight segment fails the agreed threshold.
- [ ] Test predictions are finite and physically bounded.
- [ ] The package loads in a clean environment.
- [ ] Inference output matches the production schema.
- [ ] Artifact size, memory, and latency fit the host.
- [ ] Model card, metrics, manifest, and checksums are complete.

Initial production promotion is manual after staging smoke tests.

## 11. CI pipeline

Run on every pull request or relevant commit:

1. Ruff format/lint check.
2. Unit tests.
3. Source-schema fixture tests.
4. Timestamp and unit-conversion tests.
5. Solar-feature reference tests.
6. Lag/rolling leakage tests.
7. Chronological-split tests.
8. Small fixture training run.
9. Artifact save/reload parity test.
10. Inference-schema contract test.
11. Streamlit import/startup smoke test.

CI must use committed licensed fixtures and mocked API responses. It must not rely on live provider availability.

## 12. Delivery and deployment pipeline

### Staging

1. Build with pinned production dependencies.
2. Download or include the candidate artifact by immutable version.
3. Verify checksums.
4. Start the app.
5. Run the demonstration solar-site fixture.
6. Test one live weather request and cached fallback.
7. Check latency, memory, output schema, exports, and model version.

### Production

1. Promote the same tested artifact; do not retrain during deployment.
2. Load the artifact once at startup.
3. Resolve location and system metadata.
4. Fetch and cache live forecast weather.
5. Validate API freshness, horizon, and units.
6. Generate deterministic solar/time features.
7. Retrieve required recent generation history.
8. Run inference and physical post-processing.
9. Return predictions with model/data provenance and warnings.
10. Preserve the prior production artifact for rollback.

## 13. Production fallback order

1. Current production ML model with live weather.
2. Current production model with valid cached weather.
3. Physical PV estimate with live or cached weather.
4. Bundled demonstration scenario.
5. Clear unavailable response; never fabricate a forecast.

Fallback use must be visible in the UI and logs.

## 14. Monitoring contract

### Service

- Availability and startup failures.
- API request status, timeout, latency, and quota errors.
- Inference latency and memory.
- Forecast/report request failures.

### Input quality

- Schema mismatch.
- Missing and duplicate timestamps.
- Stale issue time.
- Incomplete forecast horizon.
- Out-of-range values.
- Site metadata missingness.

### Drift

- Weather and radiation distributions.
- Solar/plane-of-array feature distributions.
- Prediction distribution and clipping rate.
- Site capacity, tilt, azimuth, and geography.
- Missingness by source and field.

### Delayed performance

After actual generation arrives:

- Rolling MAE and RMSE.
- Daylight-only error.
- Daily-energy bias.
- Error by site, season, cloud regime, and lead time.
- Production-model versus baseline performance.

Do not log API keys, sensitive site coordinates, or unnecessary raw SCADA/EMS time series.

## 15. Retraining policy

Candidate triggers:

- Minimum volume of new validated actual generation reached.
- Rolling production metrics cross a reviewed threshold.
- Sustained input/prediction drift.
- Weather provider changes schema or source model.
- New geography or installation type enters scope.
- Scheduled seasonal review.

Retraining flow:

```text
new immutable snapshots
→ new dataset version
→ quality and leakage gates
→ challenger training/tuning
→ identical-window champion comparison
→ candidate registration
→ staging
→ manual approval
→ production or rejection
```

Never overwrite the production artifact during retraining.

## 16. Rollback policy

Rollback when:

- Artifact loading or inference fails.
- Provider-schema changes cause invalid features.
- Latency or memory exceeds operating limits.
- A severe prediction regression is confirmed.
- Output-schema compatibility breaks.

Rollback actions:

1. Point production to the previous immutable artifact.
2. Preserve current inputs, version IDs, and error context.
3. Run the standard smoke fixture.
4. Record the incident and affected period.
5. Archive or repair the failed model before any new promotion.

## 17. Solo-project tool choices

| Area | Initial choice |
|---|---|
| API client | `httpx` or `requests` |
| Dataframes/storage | pandas, PyArrow, Parquet |
| Validation | Pydantic/Pandera and pytest |
| Solar calculations | pvlib |
| Modeling | scikit-learn pipelines |
| Tuning | small randomized search; Optuna when justified |
| Experiment tracking | MLflow locally or structured run JSON initially |
| Data/artifact versions | checksums/manifests; DVC when files require it |
| CI | GitHub Actions |
| Serving | Streamlit loading a joblib artifact |
| Monitoring | structured logs and scheduled metric reports initially |

Do not add Kubernetes, Kubeflow, Kafka, Airflow, or an online feature store during the first release.

## 18. Ordered execution checklist

### Source and contracts

- [ ] 1. Confirm the initial country or region.
- [ ] 2. Confirm the target unit and 24-hour forecast contract.
- [ ] 3. Select a measured solar-plant or microgrid generation source.
- [ ] 4. Select historical, archived-forecast, and live-weather endpoints.
- [ ] 5. Complete license, attribution, and quota review.
- [ ] 6. Freeze site, target, weather, and forecast-time schemas.
- [ ] 7. Define data, feature, split, and model version formats.

### Ingestion and dataset

- [ ] 8. Implement the weather provider interface.
- [ ] 9. Implement generation file/API ingestion.
- [ ] 10. Add retries, timeout, rate-limit handling, and cache.
- [ ] 11. Save immutable raw responses and metadata.
- [ ] 12. Add snapshot checksums.
- [ ] 13. Normalize timestamps and units.
- [ ] 14. Write canonical Parquet tables.
- [ ] 15. Implement data-quality checks and report.
- [ ] 16. Join generation and fixed-lead forecast weather.
- [ ] 17. Add `pvlib` physical features.
- [ ] 18. Build and hash dataset version 1.
- [ ] 19. Freeze chronological splits.

### Training and packaging

- [ ] 20. Implement persistence and physical baselines.
- [ ] 21. Implement the versioned feature pipeline.
- [ ] 22. Add leakage tests.
- [ ] 23. Train the initial candidate models.
- [ ] 24. Configure chronological tuning.
- [ ] 25. Add experiment tracking.
- [ ] 26. Produce segmented validation metrics.
- [ ] 27. Select the champion.
- [ ] 28. Run the frozen test evaluation.
- [ ] 29. Package the full inference pipeline.
- [ ] 30. Generate model manifest, schemas, metrics, card, and checksums.
- [ ] 31. Verify clean-environment load and prediction parity.

### CI, registry, and deployment

- [ ] 32. Add API response fixtures and sample data.
- [ ] 33. Add the CI test pipeline.
- [ ] 34. Create model registry stages.
- [ ] 35. Implement promotion-gate checks.
- [ ] 36. Implement live-weather inference adapter.
- [ ] 37. Implement cache and physical fallbacks.
- [ ] 38. Deploy candidate artifact to staging.
- [ ] 39. Run staging smoke, latency, and memory checks.
- [ ] 40. Manually promote the first production model.
- [ ] 41. Confirm production reports artifact and data-source versions.
- [ ] 42. Test rollback to the previous artifact.

### Monitoring and retraining

- [ ] 43. Add service and API monitoring.
- [ ] 44. Add input-quality and staleness monitoring.
- [ ] 45. Add feature and prediction drift reports.
- [ ] 46. Join delayed actuals to stored forecasts.
- [ ] 47. Add rolling performance and baseline reports.
- [ ] 48. Define reviewed alert thresholds.
- [ ] 49. Implement reproducible challenger retraining.
- [ ] 50. Require staging and manual promotion for retrained candidates.
- [ ] 51. Document incidents, rollback, and model retirement.

## 19. Open decisions

- [ ] Microgrid operator versus solar-plant analyst as the first UI persona.
- [ ] Initial geography.
- [ ] Measured solar-plant or microgrid generation dataset/API.
- [ ] Power versus energy target.
- [ ] Minimum site history required for an operational forecast.
- [ ] Require one homogeneous fixed-tilt site versus omit orientation/plane-of-array features initially.
- [ ] Weather provider/model and fixed forecast lead time.
- [ ] Confirm one aggregate site/meter as the MVP dataset boundary.
- [ ] Physical-baseline implementation depth.
- [ ] MLflow/DVC use from day one versus after the first reproducible run.
- [ ] Hosting platform and artifact-size limit.
- [ ] Retraining cadence and promotion thresholds after baseline results exist.
