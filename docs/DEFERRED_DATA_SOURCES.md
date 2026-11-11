# Deferred data sources

**Updated:** 2026-11-11
**Current priority:** frozen data for model training and evaluation.

Only data required to reproduce the model-training files is kept locally:

- `data/raw/elia_generation/` — Belgian generation target for 2024–2025.
- `data/raw/belgium_weather_archive/` — nine-point Belgian archived GFS forecasts.
- `data/processed/model_training/` — chronological train, validation, and test files.
- `data/sample/` — small synthetic fixtures required by backend tests.

The source-selection downloads below were removed because they are not inputs to
the current model. This document preserves where they came from and why they may
be useful later.

## 1. PVDAQ system 2107 and California weather

### Why deferred

PVDAQ system 2107 is a site-level California solar array. It is useful as a
plant-level benchmark, but it does not match the selected problem of forecasting
Belgium's regional PV estimate and no ongoing operational telemetry connection was
established. Its California Open-Meteo files must never be joined to Belgian Elia
generation.

### Removed PVDAQ files

Publisher: PVDAQ / DOE Solar Data Prize, system 2107
Dataset DOI: `10.25984/1846021`
Licence recorded by the source review: CC BY 4.0
Dataset page: <https://data.openei.org/submissions/4568>

| Removed file | Original URL | SHA-256 |
|---|---|---|
| `2107_system_metadata.json` | <https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI/metadata/2107_system_metadata.json> | `17e4f7f448fcb2bec43f7610b40c1f7f4fc794ccc185e41dcde0514afba73ae5` |
| `2107_meter_15m_data_2025.csv` | <https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI/data/2107_meter_15m_data_2025.csv> | `20fe6e7124bcd65715e69df0d8f5776019632c776cbe39fecb0d65908d9b14ff` |
| `2107_environment_15m_data_2025.csv` | <https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI/data/2107_environment_15m_data_2025.csv> | `0459cbea5f75a8fa5515ed2fb9a45639d4e1fabd56421661e3b377343fcec83c` |
| `2107_irradiance_15m_data_2025.csv` | <https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI/data/2107_irradiance_15m_data_2025.csv> | `c32cb8948d13645b10c05322ad32f7b61195b9e08d0ef0d6b673cea105cd4544` |

The removed files contained 67,191 meter rows, 67,179 environment rows, and
105,787 irradiance rows. See `docs/research/PVDAQ_HISTORICAL_AUDIT.md` for the
original quality review and timezone cautions.

### Removed California Open-Meteo files

Requested point: `38.996306, -122.134111`; returned GFS grid point approximately
`38.952164, -122.109375`. Variables were `temperature_2m_previous_day1`,
`cloud_cover_previous_day1`, and `shortwave_radiation_previous_day1`.

Re-download from the Open-Meteo Previous Runs endpoint using these periods:

- `2024-02-01` through `2024-12-31`
- `2025-01-01` through `2025-12-31`
- `2026-01-01` for final endpoint alignment

Endpoint: <https://previous-runs-api.open-meteo.com/v1/forecast>
Documentation: <https://open-meteo.com/en/docs/previous-runs-api>

Use this source only if the project deliberately changes to a California
plant-level forecasting task.

## 2. Elia live and schema-migration probes

### Why deferred

These bounded JSON responses were used to verify API access and the October 2026
schema transition. They are not needed to train the frozen 2024–2025 model. Fresh
responses should be collected after model selection when inference integration and
forward shadow evaluation begin; stale snapshots should not be treated as current
operational data.

### Removed files and later purpose

| Removed file | Later use |
|---|---|
| `ods032_metadata.json` | Confirm legacy target field `measured` and source metadata. |
| `ods209_metadata.json` | Implement post-migration history using `measured_upscaled`. |
| `ods210_metadata.json` | Implement current-feed target field `measured`. |
| `legacy_coverage.json` / `recent_coverage.json` | Recheck historical coverage and migration continuity. |
| `live_dimensions.json` | Validate `region="Belgium"`, `gridconnectiontype="Total"`. |
| `belgium_recent_day.json` | Test the future `ods209` adapter. |
| `belgium_live_page.json` | Test pagination, provisional values, and the future `ods210` adapter. |
| `audit_summary.json` | Reproducible source-selection results, superseded for training by the processed dataset manifest. |

Official endpoints:

- Legacy history `ods032`: <https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods032>
- Current history `ods209`: <https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods209>
- Live feed `ods210`: <https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods210>

For later API work, select Belgium/Total exactly once, persist retrieval times,
preserve source dataset/version, paginate complete responses, and measure
publication latency and revisions before enabling 1-hour generation lags.

## 3. Single-point Brussels weather probes

### Why deferred

The three 48-hour responses only demonstrated API reachability and schema. They
were superseded by the complete nine-point Belgian weather archive used for model
training.

Removed files:

- `brussels_archive_previous_day1.json` — archived July 1–2, 2025 forecasts.
- `brussels_live_previous_day1.json` — current-date day-1-offset forecast probe.
- `brussels_live_gfs.json` — latest-run forecast probe.

When API integration starts, use `config/belgium_weather_grid.json` and request all
nine configured points with the same variable names and units expected by the
trained model. Do not restore the single-point probe as the production feature set.

## 4. Removed selection-audit files

The old `data/raw/dataset_review/` tree and its aggregate audit JSON were removed.
The research scripts under `docs/research/` are retained as historical references;
they require re-downloading the sources above before they can be rerun.

The authoritative model-training provenance is now:

- `data/raw/elia_generation/source_manifest.json`
- `data/raw/belgium_weather_archive/download_manifest.json`
- `data/processed/model_training/dataset_manifest.json`
