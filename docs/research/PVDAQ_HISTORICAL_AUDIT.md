# PVDAQ historical benchmark audit

**Audited: 2026-11-10. Status: historical research evidence.**

This preserves the earlier audit of **PVDAQ system 2107, Farm Solar Array,
Arbuckle, California**, paired with archived GFS weather. Metadata lists **893 kW
DC**, which is not an AC export limit. The proposed benchmark predicts next-hour
mean AC power in kW and derived interval energy in kWh.

The user subsequently selected **public APIs, any country**, with an operational
application as the goal. The [current source recommendation and problem statement](../DATASET_RESEARCH_AND_PROBLEM_STATEMENT.md)
uses Elia's Belgian regional generation feeds. The PVDAQ archive has no verified
live telemetry connection for this project; its counts and evaluation proposal
below apply only to this historical plant-level benchmark.

## 1. What was actually downloaded and verified

The reviewed local payloads originally totaled **7,706,083 bytes, approximately
7.7 MB**. They were removed after the Belgian model-training dataset was frozen.
Original URLs, hashes, and restoration guidance are preserved in
[`docs/DEFERRED_DATA_SOURCES.md`](../DEFERRED_DATA_SOURCES.md).

### PVDAQ subset

The official `2107_OEDI` directory contains these useful small objects:

| Downloaded file | Rows | Main contents |
|---|---:|---|
| [2107_system_metadata.json](https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI/metadata/2107_system_metadata.json) | — | Site, array, instruments, units, aggregation and interval alignment |
| [2107_meter_15m_data_2025.csv](https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI/data/2107_meter_15m_data_2025.csv) | **67,191** | Measured AC power, kW |
| [2107_environment_15m_data_2025.csv](https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI/data/2107_environment_15m_data_2025.csv) | 67,179 | Ambient temperature, wind speed/direction |
| [2107_irradiance_15m_data_2025.csv](https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI/data/2107_irradiance_15m_data_2025.csv) | 105,787 | Measured plane-of-array irradiance |

**The `_2025` filenames contain both 2024 and 2025 records.** Their actual start
is 2024-02-01 and end is 2025-12-31. Appending separate `_2024` files blindly would
overlap data. The JSON metadata and older inventory have older coverage dates;
use the actual records and [May 2026 change log](https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/change_log_2023_Solar_Data_Prize_20260519.pdf)
to identify the inspected increment. Larger historical files exist, but are not
needed to establish this first cohort.

### Weather archive

Downloaded **16,824 hourly records** from Open-Meteo's **Previous Runs API**, with
`models=gfs_global`, `timezone=GMT`, and these fields:

| Field | Meaning | Unit |
|---|---|---|
| `temperature_2m_previous_day1` | Archived forecast of 2 m air temperature | °C |
| `cloud_cover_previous_day1` | Archived forecast total cloud cover | % |
| `shortwave_radiation_previous_day1` | Archived forecast global horizontal irradiance, preceding-hour mean | W/m² |

The snapshots span **2024-02-01 00:00 through 2026-01-01 23:00 UTC**, with **zero
nulls in these three fields**. The extra January day covers the UTC boundary of
the plant's final local day. These are model forecasts, not measured weather.

Requested coordinates: **38.996306, -122.134111**. The API returned a grid location
of **38.952164, -122.109375**, with elevation **110 m**; site metadata lists 10 m.
Record those differences instead of treating gridded predictors as site sensors.
The snapshots preserve the default API elevation behavior; an elevation override
would create a different feature dataset and must be versioned.

Example verified request:

```text
https://previous-runs-api.open-meteo.com/v1/forecast?latitude=38.996306&longitude=-122.134111&start_date=2025-07-01&end_date=2025-07-01&hourly=temperature_2m_previous_day1,cloud_cover_previous_day1,shortwave_radiation_previous_day1&models=gfs_global&timezone=GMT
```

Under the candidate interval/time policy below, **16,795 complete hourly power
targets** have all three weather predictors: 8,037 target hours in local 2024 and
8,758 in local 2025. These are availability counts **before** lag construction,
telemetry-delay handling, outage review, or model evaluation.

## 2. Important findings from the real data

### Generation target and physical meaning

- Source target: **`meter_revenue_grade_ac_output_meter_149578`**.
- Metadata identifies a revenue-grade meter, **AC power in kW**, aggregation
  `avg`, scale 1, offset 0, and **left-aligned** acquisition (`time_interval=L`).
- Source timestamp: `measured_on`, with no explicit UTC offset. System metadata
  specifies `PST8PDT` / US Pacific; the inspected meter jumps match local DST.
- Candidate policy: interpret meter timestamps as `America/Los_Angeles`, convert
  to UTC, and treat a quarter-hour record at `q` as covering `[q,q+15 min)`.
- For four complete equal-duration quarters, hourly mean power is their mean.
  Hourly energy is `sum(quarter_hour_kW × 0.25 h)`. Numerically it equals the hourly
  mean power over a one-hour interval, but **kW and kWh are different quantities**.
- No null target cells or duplicate raw timestamps were found. Values range from
  **0 to 707.84 kW**. This observed maximum is not a certified AC capacity limit.

The eight recorded fall-back timestamps whose UTC offsets cannot be recovered
unambiguously are excluded in the research count. Missing occurrences are not
invented. The two spring-forward jumps are normal clock transitions, not evidence
of plant outages. Only hours with all four unambiguous quarters are counted.

Two local days have entirely zero generation: **2024-10-18** and **2024-11-06**.
Irradiance gaps also occur around these dates. Investigate whether these represent
actual outages or recording problems; zero cells alone cannot distinguish them.
Do not silently fill targets, remove difficult periods to improve scores, or treat
schema validation as proof of sensor quality.

### Plant weather needs extra care

- Ambient temperature is in **°F**, not °C; conversion would be `(F - 32) × 5/9`.
  Wind is mph; irradiance is W/m². There are **20 null temperature readings**.
- The environment file is headed `utc_measured_on`, but its peak mean temperature
  occurs at raw clock hour **22 in 2024** and **15 in 2025**. This suggests a clock
  discontinuity. It is a diagnostic, not proof of the correct replacement timezone.
- The irradiance file mixes five- and fifteen-minute spacing despite `_15m` in
  its name, and includes substantial gaps. Unequal intervals need an explicit
  aggregation/coverage policy.
- Measured **plane-of-array irradiance (POA)** is not the same variable as the
  weather API's **global horizontal irradiance (GHI)**.

**Historical benchmark proposal:** use the AC meter as the target/history and archived GFS
weather as the weather features. Retain the plant weather for quality investigation
and later lagged-feature experiments after its clock/cadence issues are resolved.

## 3. Historical benchmark forecast-time contract

Let **T** be an hourly issue time in UTC. Predict the average AC power over
**[T, T+1 hour)**, labelled by its interval start.

1. **Generation history:** use only intervals whose end plus an assumed telemetry
   delay is at or before T. Start with a documented **15-minute delay assumption**.
   Under the left-aligned convention, the latest usable quarter starts at T−30 min
   and ends at T−15 min. Fit lag/rolling features using that cutoff.
2. **Weather:** use the pinned `gfs_global` / `_previous_day1` archive product.
   The documented nominal forecast lead is 24 hours **before each valid time**;
   this is independent of our one-hour solar-forecast horizon.
3. **Interval alignment:** radiation stamped T+1 hour represents the mean over
   [T,T+1 hour). Join it to the power target for that interval. Initially use the
   temperature/cloud forecasts at T+1 as endpoint predictors; they are not hourly
   measured averages.
4. **Availability assumption:** for that endpoint, nominal weather initialization
   is T−23 hours. Allowing a conservative six-hour publication delay places it at
   T−17 hours, before issue time. This is an explicit assumption using the documented
   archive offset, not an actual historical publication timestamp from the response.
5. **Time features:** hour, day-of-year, solar position, and clear-sky estimates can
   be calculated for the target interval because the clock/location are known.
6. Keep source product, model, nominal lead, retrieval time, interval conventions,
   and hashes with the experiment. Exact run/publication logs are needed for a
   later operational availability claim; a live deployment should use the same
   feature-age policy or be evaluated again after changing it.

The public PVDAQ download is an archive, not a low-latency telemetry feed. A
historical replay assumes an operator could access its own measurements with the
declared delay; the hosted demo must describe this accurately.

**Do not train a purported forecast using actual future measured irradiance,
temperature, future AC/DC power, or end-of-day yield.** Such information is not
available when issuing the prediction.

Open-Meteo products have different meanings:

- **Historical Weather:** retrospective/reanalysis weather; not a future forecast.
- **Historical Forecast:** a stitched time series of successive runs, not a
  reconstruction of one fixed issue-time day-ahead forecast.
- **Previous Runs:** fixed lead-offset products, used here with an intentionally
  older weather forecast and a short solar horizon.
- **Single Runs:** individual initializations; coverage depends on the model.
  Current docs list most models from April 2026 and earlier ECMWF IFS coverage as
  hindcasts. Do not assume those provide an operational GFS run archive for 2024.

## 4. Historical benchmark evaluation proposal

Use local-calendar boundaries, converted to UTC once and recorded in the manifest:

| Purpose | Proposed interval |
|---|---|
| Development training | February–September 2024 |
| Validation / model selection | October–December 2024 |
| Final refit after selection | February–December 2024 |
| Held-out evaluation | **January–December 2025** |

The January 2024 gap means training is eleven months rather than a full calendar
year. Report that limitation. Data quality has been inspected in 2025, but no model
has been fitted or compared on it. Keep its forecasting scores out of model tuning.

- Baselines: latest available power/past-window persistence and previous-day
  same-hour persistence. A solar-position-adjusted persistence baseline is useful.
- Candidate estimators: a scaled linear/Ridge pipeline and a tree model such as
  Random Forest or HistGradientBoosting. Choose using chronological validation.
- Fit imputers/scalers only on training data; never interpolate using future
  values or shuffle a time-series train/test split. Apply the same availability
  mask and target-quality policy to every baseline/model.
- Report **MAE and RMSE in kW**, and energy errors in kWh when relevant; include
  all-hours, daylight, monthly/seasonal, and ramp-period results plus sample counts.
- Define daylight using solar geometry, not `actual_power > 0`, which would hide
  daylight outages. Avoid MAPE as the main metric because solar targets are often zero.
- Report whether the selected model beats persistence; no improvement percentage
  or model accuracy is promised before the experiment.

These data support a site-specific study with one held-out year, not a claim that
the model generalizes to every solar plant or climate.

## 5. Reproduce the local availability audit

With the project dependencies installed including the UI extra:

```bash
uv run --frozen --no-sync python docs/research/audit_pvdaq_sample.py
```

The helper requires re-downloading the deferred payloads first. It verifies those
payloads, reports raw-file statistics and candidate alignment counts, and does not
train a model. See [`docs/DEFERRED_DATA_SOURCES.md`](../DEFERRED_DATA_SOURCES.md)
for URLs and hashes.

The report and audit helper are under the already ignored `docs/` directory;
research downloads and generated audit output are under the ignored `data/raw/`.

## 6. Sources, attribution, and API budget

- **PVDAQ:** [official dataset / license / citation](https://data.openei.org/submissions/4568),
  DOI [10.25984/1846021](https://doi.org/10.25984/1846021),
  [data dictionary](https://github.com/openEDI/documentation/blob/main/pvdaq.md).
  Cite the dataset and site, link CC BY 4.0, and describe preprocessing changes.
- **Open-Meteo:** [Previous Runs documentation](https://open-meteo.com/en/docs/previous-runs-api),
  [variable/interval definitions](https://open-meteo.com/en/docs),
  [Historical Forecast](https://open-meteo.com/en/docs/historical-forecast-api),
  [Single Runs](https://open-meteo.com/en/docs/single-runs-api),
  [pricing/usage](https://open-meteo.com/en/pricing).
  Attribute Open-Meteo and the underlying NOAA GFS model; data are CC BY 4.0.
  The free hosted API is for noncommercial use. Current published limits include
  600 calls/minute, 5,000/hour, and 10,000/day; longer/multi-variable requests may
  count as multiple calls. Cache snapshots rather than refetching during training.

The dataset licenses concern their data, not the license for this project's code.
Source/API terms and mutable source objects should be versioned with each later
experiment. No training result, deployment, or public upload was produced here.
