# Project decisions — public-API solar forecasting

**Updated: 2026-11-11**
**Current state:** backend scaffold + frozen model-training dataset. The user
selected **public APIs, any country**. Elia/Belgium is the recommended application
scope. Model training and evaluation are the immediate priority; production API
collection and agentic/advisory work are deferred until model weights and parameters
have been selected.

## Latest research recommendation

Use **Elia's Belgian generation APIs** plus **Open-Meteo forecast weather** for a
live regional solar-forecasting application. Recommend predicting Belgium/Total's
next-hour mean estimated PV power in **MW**, with derived hourly **MWh**.

The target is an operator-published **measured/upscaled regional estimate**. The
live response and historical queries were verified without credentials. The
downloaded 2024–2025 export contains **70,176** quarter-hour rows, **69,888** non-null
targets, and **17,256** complete target hours before weather/lag matching. A same-day
live snapshot and a nine-point Belgian archived-forecast weather grid were also saved.
The aligned table has **16,831** complete target/weather hours: 8,071 in 2024 and
all 8,760 hours in 2025.

Elia's **2026-10-26 schema migration** needs explicit handling: historical
`ods032.measured` → `ods209.measured_upscaled`; current values are in
`ods210.measured`. The new schema adds `gridconnectiontype`. Its full licence terms
and exact service quotas still need confirmation because the linked terms page
was temporarily unavailable.

See [operational source evidence and proposed problem statement](DATASET_RESEARCH_AND_PROBLEM_STATEMENT.md).
Only model-training inputs are retained under `data/raw/elia_generation/` and
`data/raw/belgium_weather_archive/`. The old API probes and PVDAQ/California
candidate files were removed and recorded in [deferred data sources](DEFERRED_DATA_SOURCES.md).
Kaggle-sourced datasets remain excluded from source selection.

The older planning files recommend aggregate site-level solar forecasting, an
hourly/day-ahead direction, and later advisory/RAG features. These are useful
proposals, not irreversible decisions. The current scaffold deliberately does
not require an hourly cadence, 24-row horizon, specific weather provider, geography,
physical unit, or model library.

## 1. Questions to answer next

| Decision | What must be known | Current answer |
|---|---|---|
| First user | Who uses the forecast? | Proposed: energy analyst monitoring Belgian solar supply |
| Problem | What decision becomes better because of the output? | Anticipate next-hour changes in regional solar supply |
| Target | Direct meter reading, upscaled estimate, or simulated generation? | Elia's measured/upscaled regional estimate; proposed hourly mean |
| Access | Private plant connection or public APIs? | **User confirmed public APIs, any country** |
| Source | Matching historical and ongoing operational data? | Recommend Elia `ods032`/`ods209` + `ods210`, with Open-Meteo GFS |
| Units | Target/weather units and interval semantics? | MW, derived MWh; quarter-hour starts in UTC; temperature °C, clouds %, GHI W/m² |
| Geography | Site or aggregate, local timezone, coverage? | Proposed Belgium/Total; UTC storage and Europe/Brussels local interpretation |
| Forecast task | Horizon, cadence, issue time, acceptable latency? | Upcoming one-hour interval; hourly issue; measure actual feed freshness/revisions |
| Future inputs | Forecast weather available at issue time? | Verified live and archived GFS; nine-point previous-day1 archive acquired and aligned for the first experiment |
| Evaluation | Chronological boundaries, baseline, errors and segments? | Proposed 2024 development / 2025 holdout, followed by current-schema shadow evaluation |
| Advisor | Is there enough trusted guidance and operational context? | Deferred |
| Hosting | A platform that supports the final API/UI and secrets? | Open |
| Licensing | Code licence, API/data terms, document redistribution? | Elia full terms/quota confirmation pending; Open-Meteo free hosting is noncommercial; code licence open |

Source selection requires a clearly defined target, matching historical/live
populations, location/timezone, sampling frequency, forecast-time availability,
and permitted usage. A static archive is useful for development but does not by
itself establish a continuously updating application.

## 2. Recommended problem statement

“Forecast Belgium's next-hour average photovoltaic generation estimate using
recent Elia generation estimates and weather forecasts available at issue time;
track errors against subsequently published estimates and help energy analysts
anticipate near-term changes in solar supply.”

This recommendation follows the user's public-access requirement. Model choice,
spatial weather features, availability policy, and ingestion contracts still need
implementation and evaluation. Simulated fixtures can test the backend contract;
forecast accuracy must be assessed against the real operator-published target.

## 3. Candidate-source comparison worksheet

For each candidate, record:

```text
Candidate name:
Publisher and original URL:
Dataset version / API endpoint product:
License, attribution, and redistribution permission:
Target column and measured vs simulated status:
Regional upscaling/estimation method and revisions, if applicable:
Target unit and interval semantics:
Site/location/timezone and capacity metadata:
Observation period, frequency, row count, gaps:
Live update cadence, observed arrival times, history/live schema compatibility:
Weather fields, units, and location/time alignment:
Forecast issue time / valid time / lead time available:
API quotas, price, authentication, and deployment restrictions:
Known privacy or quality concerns:
Reason to select/reject:
```

For day-ahead evaluation, observed/reanalysis weather alone can produce optimistic
results. Prefer archived forecasts at the intended issue time/lead, or clearly
label an observed-weather experiment as non-operational.

## 4. Smallest useful next implementation

1. Confirm the remaining Elia terms/quota details and define the versioned source
   mapping and national weather grid.
2. Add a persistent public-feed collector; save responses, arrival times, and
   revisions through day boundaries.
3. Freeze the reviewed weather/archive alignment and audit historical/live generation
   semantics; update `config/project.yaml` with the final inference contract.
4. Extend forecast requests with issue time and validated generation history.
5. Freeze splits, evaluate persistence and one candidate model, and register the
   selected versioned predictor.
6. Return genuine forecasts with source freshness and later measured-estimate
   comparisons, then implement advisory and hosting deliverables.

The target export, bounded live probes, nine-point weather archive, provenance
manifests, and offline alignment audit are complete. A collector, trained model,
current-schema shadow evaluation, and deployed application are the next work.

## 5. Decision log

| Date | Decision/default | Reason | Consequence |
|---|---|---|---|
| 2026-11-10 | One reusable Python backend with YAML profiles | Data/API and problem are still undecided | New sources change adapters/config, not duplicated backends |
| 2026-11-10 | FastAPI + optional Streamlit shell | Clear HTTP contract with the UI direction in the brief | UI/API run separately; hosting must support that layout |
| 2026-11-10 | No production predictor/provider/advisor enabled | Avoid invented predictions or premature provider choices | Explicit 503 responses until real adapters are implemented |
| 2026-11-10 | GitHub + hosted app + demo video | Deliverables requested in the original brief | The application needs genuine operational inputs and model outputs |
| 2026-11-10 | Earlier PVDAQ 2107 recommendation superseded for deployment | Its downloaded archive did not establish an ongoing telemetry connection | Preserve the historical audit as research evidence |
| 2026-11-10 | **User requirement:** no Kaggle-sourced datasets | Goal is a real operational application | Prioritize direct providers with historical and ongoing feeds |
| 2026-11-10 | **User selected:** public APIs, any country | No private plant connection is needed for the chosen direction | Research and recommend a regional operator feed |
| 2026-11-10 | **Recommendation:** Elia Belgium/Total + Open-Meteo, next-hour estimated MW | Verified historical and same-day public access; forecast weather available | Account for schema migration, provisional targets, spatial weather, API terms and freshness |
| 2026-11-11 | Nine-point Belgian GFS `previous_day1` grid for the first offline experiment | Replaces the insufficient single-point 48-hour probe while preserving forecast-time inputs | 16,831 complete aligned hours; spatial weighting and current-schema shadow evaluation remain future validation |
| 2026-11-11 | Prioritize frozen data and model training before live APIs or agentic work | User clarified that current requirements are for model training | Train/validate/test files are prepared now; implement live acquisition after selecting model weights and parameters |
| TBD | Final problem statement | After source review | Update the profile, README, and this log |

Engineering defaults above do not finalize the scientific/modeling decisions.
