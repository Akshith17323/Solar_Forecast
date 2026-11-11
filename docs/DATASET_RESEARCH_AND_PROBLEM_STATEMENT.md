# Operational data recommendation and problem statement

**Updated: 2026-11-11. User-selected direction: public APIs, any country.**

## 1. Recommendation

Build a **Belgian regional solar-generation forecasting application**, using
**Elia's public generation APIs** and **Open-Meteo weather forecasts**.

The selection criterion is access to both historical generation and an ongoing
operational feed for the same forecasted population. Kaggle-sourced datasets are
excluded. The user confirmed that the application should work entirely through
public APIs and that any country is acceptable.

| Role | Direct source | Verified access |
|---|---|---|
| Current generation estimates | [Elia `ods210`](https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods210) | HTTP 200 without credentials; same-day measured values and future provider forecasts |
| Historical generation estimates | [Elia `ods032`](https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods032) and [its replacement `ods209`](https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods209) | Historical coverage query plus downloaded 2024–2025 records and a recent sample |
| Forecast weather | [Open-Meteo Forecast API](https://open-meteo.com/en/docs) | Live GFS temperature, cloud cover, and irradiance response verified |
| Archived forecast weather | [Open-Meteo Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api) | Historical and current-date `gfs_global` / `_previous_day1` responses verified |

### Proposed title

**Weather-Aware Regional Solar Generation Forecasting for Belgium**

### Proposed problem statement

> Build a public-API application that forecasts Belgium's next-hour average
> photovoltaic generation estimate in MW using recent Elia generation estimates
> and weather forecasts available at issue time. Track errors against subsequently
> published generation estimates, compare with simple baselines across seasons,
> and help energy analysts anticipate near-term changes in solar supply.

| Scope item | Recommended first implementation |
|---|---|
| Intended user | Energy analyst monitoring Belgian solar supply |
| Forecast population | `region="Belgium"`, `gridconnectiontype="Total"` in the new Elia schema |
| Primary target | Average estimated PV power over the upcoming hour, **MW** |
| Optional energy display | Derived estimated hourly energy, **MWh** |
| Issue time / horizon | Issue hourly at UTC time T; predict **[T, T+1 hour)** |
| Generation input frequency | Quarter-hour intervals |
| Weather variables | Forecast GHI in W/m², temperature in °C, cloud cover in % |
| Application behavior | Scheduled API collection, timestamped predictions, freshness indicators, subsequent error tracking |
| Later advisory milestone | Evidence-grounded summaries of expected generation changes and variability |

Elia publishes **measured and upscaled regional estimates**. The forecast target
and its errors must be labelled accordingly; this is not a raw meter feed from an
individual plant. The PDF permits short- or long-term forecasting, so a next-hour
first version fits the brief. A sequence of hourly predictions has multiple issue
times and should be displayed with those times.

## 2. Elia source contract and schema transition

The official legacy metadata announces a migration on **2026-10-26**:

| Dataset | Purpose | Generation target field | Relevant dimensions |
|---|---|---|---|
| `ods032` | Historical data before migration | `measured` | `region`; no grid-connection field |
| `ods209` | Historical data after migration | **`measured_upscaled`** | `region`, `gridconnectiontype` |
| `ods210` | Current near-real-time feed | **`measured`** | `region`, `gridconnectiontype` |

The old near-real-time dataset `ods087` was replaced by `ods210`. The migration
also introduced TSO/DSO/Total categories and D+10 forecasts, and removed the
Wallonie/Vlaanderen region totals while retaining provinces. The live dimension
query returned **36 region/connection combinations**, including Belgium/Total.
Select that aggregate once; adding it to province totals or adding Total to
TSO/DSO would double-count generation.

Non-null Belgium target coverage in the saved queries:

- Legacy `ods032`: **2020-09-30 22:00 through 2026-10-25 22:45 UTC**.
- New `ods209`, Total: **2026-10-25 23:00 through 2026-11-08 22:45 UTC**.
- These boundaries are one quarter-hour apart. This supports a proposed schema
  bridge; it does not establish identical estimation methods or population
  coverage. Preserve source version and inspect capacity/estimation changes when
  mapping legacy Belgium records to the new Total category.

`datetime` labels the **start** of the interval. Live/legacy records identify
`resolutioncode=PT15M`; the new historical metadata declares 15-minute granularity
but its inspected records omit `resolutioncode`. Normalize the interval duration
explicitly for each source version.

Live metadata describes `measured` as a **running average**. A non-null value can
be provisional, and even a completed interval may be revised. Future rows contain
provider forecasts with null measured values. Preserve that distinction.

Example live query, verified without an API key:

```text
https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods210/records?where=region%3D%22Belgium%22%20AND%20gridconnectiontype%3D%22Total%22%20AND%20measured%20is%20not%20null&order_by=datetime%20desc&limit=4
```

`mostrecentforecast` and `dayaheadforecast` are **Elia's predictions**, not observed
generation or outputs from our model. Keep their attribution and forecast-time
availability when using them as external comparisons. A retrospectively downloaded
`mostrecentforecast` is not an as-of-issue-time feature.

## 3. What was downloaded and audited

The source-selection review originally saved 12 bounded API responses. After the
training dataset was frozen, only the historical generation CSV was retained at:

```text
data/raw/elia_generation/belgium_2024_2025.csv
```

Its provenance and SHA-256 are in `data/raw/elia_generation/source_manifest.json`.
The removed metadata, live-feed, coverage, and single-point weather probes are
documented in [deferred data sources](DEFERRED_DATA_SOURCES.md) for the later API phase.

### Historical Belgian generation, 2024–2025

The bounded CSV export includes generation, capacity, interval duration, region,
and Elia's day-ahead forecast. All statistics below concern the downloaded bytes.

| Audit item | Result |
|---|---:|
| Quarter-hour rows | **70,176** |
| Non-null generation targets | **69,888** |
| Null generation targets | **288** |
| Missing timestamps / duplicate timestamps | **0 / 0** |
| Complete four-quarter target hours | **17,256** |
| Complete target hours in UTC 2024 / 2025 | **8,496 / 8,760** |
| Observed target range | **0–7,753.81 MW** |
| Reported capacity range | **8,788.791–11,763.732 MW** |

The 288 null targets occur at **23:45 Europe/Brussels** between January 1 and
October 15, 2024. This is a recurring missing-value pattern, not 288 missing
timestamps or three contiguous missing days. Retain the nulls and their quality
flags; the complete-hour counts exclude affected hours.

These are target-availability counts **before** weather matching, lag construction,
publication-delay assumptions, revision checks, and modeling. A changing regional
capacity is relevant to forecasting; a single fixed plant-capacity assumption
would be inappropriate.

### Recent and live responses

- A November 8 UTC historical query returned **96 rows**, of which **92** had
  `measured_upscaled`; the maximum was **1,781.79 MW**. The final four target cells
  were null at retrieval. Their UTC times belong to the following Belgian local day.
- The saved live page contains **100 of 1,056** matching rows; it is intentionally
  a bounded page, not a complete forecast export.
- At **05:08:17 UTC on November 10**, that page contained **24** non-null generation
  intervals, most recently **04:45–05:00 UTC**. All were nighttime zeros. The other
  **76** saved target cells were null, while provider forecasts could be populated.
- This verifies same-day public access and schema behavior. A single nighttime
  snapshot does not measure sustained daytime availability, publication latency,
  or revision frequency.

### Weather access probes and aligned archive

Three 48-hour GFS responses were initially saved for a Brussels coordinate: latest live
forecasts, current-date `_previous_day1` forecasts, and archived `_previous_day1`
forecasts for July 1–2, 2025. Requested coordinates were **50.85, 4.35**; the API
returned grid coordinates **50.901398, 4.3359375**.

The first offline experiment now uses the versioned nine-point grid in
`config/belgium_weather_grid.json`. The downloaded archive contains **158,112
point-hours** from January 1, 2024 through January 1, 2026. After endpoint alignment,
**16,831 target hours** have all four generation quarters and all 27 weather values:
8,071 hours in 2024 and 8,760 in 2025. All points are complete from weather valid
time January 19, 2024 12:00 UTC onward. Earlier null values remain missing.

Open-Meteo returned 125 cloud-cover rounding artifacts at -1% or 101%. Raw values
and flags are retained; the modeling column is explicitly clipped to 0–100%.
The earlier California weather downloads are not inputs for Belgium. The fixed
nine-point grid is a reproducible first experiment, not a claim that equal spatial
coverage perfectly represents installed PV capacity.

## 4. Forecast-time design for a running application

### Generation collection and targets

1. Preserve immutable responses with retrieval time, source dataset/version,
   region, connection type, interval start/end, and provider processing metadata.
2. Start with a **15-minute collection schedule** and measure observed freshness.
   Metadata says “5 Minutes” refresh while the description says quarter-hour
   updates; neither establishes a guaranteed delay for final measurements.
3. At issue time T, allow generation lags only when the interval has ended and the
   value was actually retrieved by T. Completed live intervals remain provisional.
   Track revisions when the daily archive becomes available.
4. Persist the rolling feed across local midnight. During this review, the daily
   history lagged the live feed by a local day; an on-demand query of the two APIs
   alone did not supply a complete uninterrupted recent-history window.
5. Define the hourly target from four non-null quarter-hour estimates. Its mean
   has units MW; summing quarter-hour MW × 0.25 hours gives estimated MWh. Missing
   intervals produce an incomplete target flag rather than a zero-generation label.
6. Display latest interval end, retrieval time, and provisional/stale status. Save
   the exact inputs used for every prediction so later revisions cannot rewrite
   the historical input record.

Historical archives do not supply original observation-arrival times. A backtest
using final archived lags therefore needs an explicitly labelled availability
assumption and delay sensitivity analysis. Replace that assumption with measured
collector behavior for forward evaluation.

### Weather consistency

For the first reproducible model experiment, use pinned **`gfs_global` forecasts
with `_previous_day1` fields** in both historical training and current-date
prediction requests. Both access paths were verified. This intentionally uses
older weather forecasts while generation lags provide more recent information.

The documented weather offset is a nominal 24 hours before each valid time; it is
independent of the one-hour solar forecast horizon. For [T,T+1 hour), radiation at
T+1 represents the preceding-hour mean. Temperature/cloud values at T+1 can be
endpoint predictors, with their instantaneous meaning retained.

Use a fixed set of points across Belgium and preserve each point's forecasts as
features. Record requested/returned coordinates, elevation behavior, units, model,
product, and nominal lead. Any learned spatial weighting must be fitted using
training data only.

The archive responses lack exact historical publication times. A nominal lead is
not a publication log. For an endpoint T+1, the nominal day1 reference is T−23 hours;
any assumed publication allowance used in a backtest must be recorded explicitly.
For live predictions, the response must already have been received by issue time.

Also collect the latest Forecast API snapshots for a later, matched evaluation of
fresher weather inputs. Switching to latest-run predictors changes the feature-age
policy and requires evaluation; a previous-day1 historical score should not be
presented as validation of that changed policy. Historical/reanalysis observed
weather is not a substitute for forecast-time weather inputs.

## 5. Evaluation and fit to the project brief

Use chronological development in **2024** and a held-out **2025** target year.
The first jointly complete target hour is January 19, 2024 11:00 UTC. A proposed split is:

- Training: first usable 2024 date through September 30.
- Validation/model selection: October–December 2024.
- Final refit: available 2024 data after model selection.
- Held-out evaluation: January–December 2025, with coverage counts reported.

Compare available-power persistence and previous-day persistence with a simple
regression/tree model. Report **MAE/RMSE in MW**, all-hours/daylight performance,
monthly/seasonal errors, ramp-period errors, and evaluated sample counts. Define
daylight using solar geometry, so zero-output daylight periods remain visible.
Use the same target-quality and input-availability policies for every model.

Forward shadow evaluation must cover the current schema, current capacity, daytime
operation, and revisions. A score on legacy 2025 estimates alone does not establish
performance after the October 2026 migration. Elia's own forecasts may provide an
attributed comparison when their issuance/availability can be aligned fairly.

| Brief requirement | Operational implementation |
|---|---|
| Solar generation and weather | Direct operator/API history plus ongoing scheduled collection |
| Irradiance, temperature, clouds | Matched forecast variables at multiple Belgian grid points |
| Regression/time-series models | Available generation lags, weather, time/solar features |
| MAE, RMSE, seasonality | Chronological evaluation plus subsequently observed live errors |
| Forecast UI | Prediction, issue time, source freshness, observed/estimated target, error history |
| Retrieval/agentic reasoning | Later numerical forecast summaries grounded in curated guidance |
| Grid/storage advice | Generation variability support; quantitative dispatch additionally requires load, battery/SOC, and other operating constraints |
| Delivery | Hosted app, GitHub repository, and demo video |

## 6. Access terms and operating budget

- **Elia:** the reviewed requests succeeded without authentication or payment.
  Metadata identifies **“Elia Open Data Licence”** and links its
  [licence page](https://opendata.elia.be/pages/licence/). That page returned a
  temporary portal-unavailable message, and the general disclaimer fetch failed.
  Exact reuse conditions and service quotas remain unverified. Public reachability
  is established; unlimited requests, a service guarantee, and unrestricted
  commercial reuse are not established by this review.
- **Open-Meteo:** [data licence](https://open-meteo.com/en/licence) is CC BY 4.0;
  attribute Open-Meteo and NOAA GFS and describe modifications. The
  [free hosted API](https://open-meteo.com/en/pricing) is for **noncommercial use**
  and has no uptime guarantee. Current stated limits include 600 calls/minute,
  5,000/hour, 10,000/day, and 300,000/month. Multi-location/long requests can count
  as multiple calls. Commercial hosted usage requires the appropriate paid plan.
- A proposed 15-minute Elia polling cadence is **96 requests/day** for one query;
  validate that budget against Elia's terms. Cache weather across UI visitors and
  archive each response once instead of refetching during every training run.

## 7. Next implementation steps

1. Resolve the remaining Elia terms/quota details and document the versioned
   Belgium/Total target mapping and weather grid.
2. Implement the persistent live collector and source-specific historical adapters;
   reconcile units, intervals, revisions, and the schema transition.
3. Freeze temporal splits and the reviewed `previous_day1` feature-age policy;
   evaluate persistence and one weather-aware baseline on the aligned archive.
4. Extend the backend forecast contract with **issue time and validated recent
   history**, which lag-based prediction requires.
5. Evaluate baselines and one model, register the selected versioned predictor,
   and add live prediction/error/freshness charts.
6. Build the grounded advisory and hosting deliverables around those outputs.

The backend is still a scaffold; the research download is not a scheduled
collector or a trained predictor. Large source exports belong in the ingestion
pipeline rather than the starter's size-limited upload validation endpoint.

### Reproduce this audit

With the project's UI dependencies installed:

```bash
uv run --frozen --no-sync python docs/research/audit_public_api_sample.py
```

The helper verifies all 12 payload hashes and regenerates the offline audit
summary. The earlier plant-level study is preserved in
[PVDAQ historical benchmark audit](research/PVDAQ_HISTORICAL_AUDIT.md); it is not
the source for the proposed Belgian deployment.

Research guides/helpers are covered by `/docs/` in `.gitignore`. Downloaded data,
manifests, and generated audit summaries are covered by `/data/raw/*`.
