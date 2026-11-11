# Planning Review: Microgrid and Solar-Plant Scope

**Review date:** 2026-11-05
**Status:** Revised planning direction
**Interpretation:** “Solar planning” is treated here as solar-plant planning and analysis.

## 1. Scope decision

The initial product will target **microgrid and solar-plant forecasting and planning**. Individual household/rooftop forecasting is deferred.

Reason for deferring households:

- Rooftops have different directions, tilt angles, capacities, inverter limits, shading, and installation quality.
- A household-first model would need reliable installation metadata or a more complex multi-site model.
- Household generation and consumption data create additional privacy and ingestion requirements.
- The initial project can be validated more clearly using one aggregated generation signal from a microgrid or solar plant.

Individual homes remain a possible later expansion after the site-level forecasting, agent workflow, and MLOps pipeline are stable.

## 2. Initial users

Primary users:

1. **Microgrid operators or facility energy managers** planning generation, storage, and loads.
2. **Solar-plant operators and analysts** monitoring and forecasting site production.

Secondary users:

- Renewable-energy analysts.
- Campus or industrial-facility energy teams.
- Researchers evaluating solar variability.

Deferred users:

- Individual households with rooftop solar.
- Prospective residential solar customers.
- Installers comparing many roof orientations.

## 3. MVP system boundary

The first model should use:

- One solar site or one microgrid's aggregated PV source.
- One aggregated generation meter/target series.
- One geographic location and timezone.
- Hourly observations.
- A next-24-hour forecast.
- Weather and radiation values aligned with each forecast timestamp.
- Site-level capacity and operational metadata where available.

Initial physical-layout assumption:

- Prefer a fixed-tilt solar plant with one dominant/representative orientation.
- If tilt and azimuth are unavailable or heterogeneous, begin with site-level weather, irradiance, time, and measured-generation features.
- Do not model separate household roofs, sub-arrays, tracker rows, or orientation groups in the MVP.
- Add block-level or multi-orientation modeling only after the aggregate baseline is complete.

## 4. MVP outputs

### Forecast

- Next 24 hourly generation values.
- Expected daily energy.
- Peak generation and expected peak time.
- Low-output periods.
- Rapid upward/downward ramps.
- Forecast uncertainty when a validated method is available.
- Model and data-source versions.

### Optimization report

- Forecast summary.
- Variability and risk periods.
- Grid-balancing actions.
- Storage recommendations when battery constraints are known.
- Load-shifting or energy-utilization strategies.
- Curtailment considerations where relevant.
- Assumptions and limitations.
- Supporting references.

The first release is advisory. It will not control inverters, batteries, switches, or plant equipment.

## 5. Site metadata

Required or strongly preferred:

```text
site_id
site_type
latitude_deg
longitude_deg
site_elevation_m
timezone
rated_dc_capacity_mw
rated_ac_capacity_mw
commissioned_at
```

Optional physical metadata:

```text
mounting_type
representative_tilt_deg
representative_azimuth_deg
tracking_type
module_type
inverter_type
estimated_system_losses_pct
```

Microgrid metadata for optimization, when available:

```text
battery_capacity_mwh
battery_power_mw
battery_state_of_charge_pct
minimum_reserve_pct
round_trip_efficiency_pct
critical_load_mw
flexible_load_mw
grid_import_limit_mw
grid_export_limit_mw
```

Use visibly marked unknown values rather than inventing plant specifications.

## 6. Location, solar, and seasonal features

Calculate deterministic solar features locally with `pvlib`:

- Solar zenith and apparent zenith.
- Solar elevation and apparent elevation.
- Solar azimuth.
- Solar declination and hour angle.
- Equation of time.
- Earth–sun distance/extraterrestrial irradiance.
- Sunrise, solar noon, sunset, and daylight state.
- Relative and absolute air mass.
- Clear-sky GHI, DNI, and DHI.
- Clear-sky index.
- Plane-of-array irradiance only when a valid representative tilt/azimuth exists.

Time features:

- Hour sine/cosine.
- Day-of-year sine/cosine.
- Month or season for analysis and only for model use when validated.
- Calendar year retained for lineage and chronological splitting.
- `days_since_commissioning` when enough history exists to study degradation.

Terminology:

- `site_elevation_m`: plant elevation above sea level.
- `solar_elevation_deg`: sun angle above the horizon.
- `representative_tilt_deg`: array/module tilt from horizontal.

## 7. Weather and environmental inputs

Initial predictors:

- GHI or shortwave radiation.
- DNI.
- DHI.
- Total cloud cover and, if available, low/mid/high cloud cover.
- Air temperature.
- Relative humidity.
- Wind speed.
- Surface pressure.
- Precipitation and snow where relevant.

Potential later predictors:

- Panel/module temperature.
- Soiling and cleaning events.
- Snow cover.
- Aerosols/visibility.
- Curtailment and outage flags.
- On-site pyranometer and weather-station measurements.

## 8. API and Parquet decision

Use both:

1. Fetch historical, archived-forecast, and live weather from an API.
2. Preserve original API responses and request metadata.
3. Normalize them into canonical Parquet tables.
4. Join weather with measured plant/microgrid generation.
5. Train from versioned Parquet snapshots.
6. Use the live weather API only during production inference.
7. Cache responses and retain an offline demo/fallback dataset.

Do not train directly against a changing live endpoint.

## 9. Proposed data sources

### Generation target

Preferred order:

1. Open solar-plant or microgrid dataset with measured power/energy.
2. Plant SCADA export with permission.
3. Microgrid meter/EMS export with permission.
4. Public utility-scale solar benchmark dataset.
5. Simulated generation only for pipeline testing and a physical baseline.

Required target metadata:

- Timestamp and timezone.
- Average power or interval energy with units.
- Interval duration.
- Rated capacity.
- Curtailment/outage/status flags when available.

### Weather and solar resource

Initial candidate: **Open-Meteo**, after final license, quota, and regional-quality review.

Use:

- Historical/reanalysis weather for exploration and long-term context.
- Archived forecast or previous-run data for realistic day-ahead training/evaluation.
- Live forecast data for deployed inference.
- PVGIS as a physical/reference estimate.
- NASA POWER as a reviewed reference or backup source.

Store the provider, source model/dataset, issue time, valid time, lead time, retrieval time, units, and request parameters.

## 10. Evaluation boundary

- Split all observations chronologically.
- Keep the newest period untouched for final testing.
- Use rolling or expanding validation windows.
- Compare with persistence, seasonal/hour, and physical baselines.
- Report overall and daylight-only MAE/RMSE.
- Report normalized errors using rated capacity.
- Report daily-energy bias.
- Break down performance by season, hour, cloud regime, ramp size, and forecast lead.
- Separate outages and curtailment from normal generation when flags are available.
- Use archived forecasts at the intended day-ahead lead time to avoid optimistic weather inputs.

## 11. Canonical data model

### Site table

```text
site_id
site_type
latitude_deg
longitude_deg
site_elevation_m
timezone
rated_dc_capacity_mw
rated_ac_capacity_mw
mounting_type
representative_tilt_deg
representative_azimuth_deg
tracking_type
commissioned_at
```

### Time-series table

```text
site_id
valid_at_utc
interval_minutes
power_generation_mw
energy_generation_mwh
ghi_w_m2
dni_w_m2
dhi_w_m2
temperature_c
cloud_cover_pct
relative_humidity_pct
wind_speed_m_s
surface_pressure_hpa
precipitation_mm
forecast_issued_at_utc
forecast_lead_hours
weather_source
plant_status
curtailment_flag
```

### Derived features

```text
solar_zenith_deg
solar_elevation_deg
solar_azimuth_deg
airmass_relative
clear_sky_ghi_w_m2
clear_sky_index
poa_global_w_m2
is_daylight
hour_sin
hour_cos
day_of_year_sin
day_of_year_cos
days_since_commissioning
```

Keep MW and MWh separate and retain interval semantics.

## 12. Agent scope

The LangGraph assistant should consume the validated site-level forecast and deterministic risk calculations.

Initial risk types:

- Sustained low generation.
- Rapid ramps.
- Forecast uncertainty.
- Expected generation above export/storage acceptance limits.
- Storage reserve risk when battery state is supplied.
- Critical-load coverage risk when load data is supplied.

Do not generate precise storage schedules without capacity, power, state of charge, efficiency, and reserve constraints.

## 13. Deferred expansion

### Multi-array and multi-site plants

- Separate array blocks by tilt, azimuth, technology, and tracker mode.
- Aggregate block forecasts to site level.
- Add spatial weather features.
- Model clipping, curtailment, outages, and maintenance states.

### Multiple microgrid assets

- Add load forecasting.
- Add storage optimization with explicit constraints.
- Add grid import/export limits.
- Add controllable generation and demand-response assets.

### Individual households

- Support roof-specific tilt, azimuth, shading, inverter, and capacity.
- Add privacy-preserving inverter/consumption ingestion.
- Create a global residential model and site calibration strategy.
- Add household-oriented load and battery recommendations.
- Keep residential models separate from utility-scale models unless evidence supports transfer.

## 14. Planning decisions still required

- [ ] Select microgrid operator or solar-plant analyst as the first UI persona.
- [ ] Select the initial country/region.
- [ ] Select a measured plant or microgrid generation dataset.
- [ ] Choose average power (MW), interval energy (MWh), or both as targets.
- [ ] Confirm hourly day-ahead forecasting and the exact lead time.
- [ ] Confirm one aggregate site/meter for the MVP.
- [ ] Decide whether to require one fixed representative orientation or omit plane-of-array features initially.
- [ ] Decide how to identify/remove outages and curtailment.
- [ ] Select the weather provider/model and archived-forecast product.
- [ ] Decide whether microgrid load and battery data are included in the MVP.
- [ ] Review API and dataset licenses for public deployment.

## 15. Recommended next planning actions

1. Choose the first persona: microgrid operator or solar-plant analyst.
2. Select the initial region and measured generation dataset.
3. Audit whether the dataset represents one aggregate site and contains capacity/status metadata.
4. Align a small generation sample with archived forecast weather.
5. Verify units, timestamps, timezone, issue time, valid time, and lead time.
6. Build persistence and physical baselines.
7. Decide whether representative orientation data improves the baseline enough to keep it.
8. Freeze the first target, horizon, schema, and evaluation boundary.
9. Update implementation tasks only after these decisions are accepted.

## 16. Reviewed references

- [Open-Meteo Weather Forecast API](https://open-meteo.com/en/docs)
- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
- [Open-Meteo Historical Forecast API](https://open-meteo.com/en/docs/historical-forecast-api)
- [pvlib solar-position documentation](https://pvlib-python.readthedocs.io/en/stable/reference/solarposition.html)
- [pvlib clear-sky documentation](https://pvlib-python.readthedocs.io/en/stable/user_guide/modeling_topics/clearsky.html)
- [pvlib plane-of-array documentation](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.irradiance.get_total_irradiance.html)
- [European Commission PVGIS API documentation](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/getting-started-pvgis/api-non-interactive-service_en)
- [NASA POWER API documentation](https://power.larc.nasa.gov/docs/services/api/)
