"""Offline dataset-selection audit, not a production cleaning/training pipeline.

Run from the project root after obtaining the files in the download manifests:
    uv run --frozen --no-sync python docs/research/audit_pvdaq_sample.py

Uses pandas already installed with the scaffold's UI extra. Makes no network calls.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2] / "data/raw/dataset_review"
POWER = "meter_revenue_grade_ac_output_meter_149578"
TEMPERATURE = "ambient_temperature_o_149575"
WEATHER = [
    "temperature_2m_previous_day1",
    "cloud_cover_previous_day1",
    "shortwave_radiation_previous_day1",
]


def verify_downloads() -> dict:
    verified = []
    for folder in ("pvdaq_2107", "open_meteo"):
        manifest = json.loads((ROOT / folder / "download_manifest.json").read_text())
        for entry in manifest["files"]:
            path = ROOT / folder / entry["file"]
            payload = path.read_bytes()
            if len(payload) != entry["bytes"]:
                raise ValueError(f"Size differs from recorded download: {path}")
            if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise ValueError(f"Checksum differs from recorded download: {path}")
            verified.append({"file": str(path.relative_to(ROOT)), "bytes": len(payload)})
    return {"files": verified, "total_payload_bytes": sum(item["bytes"] for item in verified)}


def describe_csv(path: Path) -> dict:
    frame = pd.read_csv(path)
    times = pd.to_datetime(frame.iloc[:, 0])
    deltas = times.diff().dropna()
    gaps = deltas.nlargest(3)
    return {
        "file": path.name,
        "rows": len(frame),
        "columns": list(frame.columns),
        "raw_timestamp_first": str(times.min()),
        "raw_timestamp_last": str(times.max()),
        "duplicate_timestamp_rows": int(times.duplicated().sum()),
        "missing_cells": frame.isna().sum().to_dict(),
        "numeric_min": frame.iloc[:, 1:].min().to_dict(),
        "numeric_max": frame.iloc[:, 1:].max().to_dict(),
        "common_timestamp_deltas": {
            str(k): int(v) for k, v in deltas.value_counts().head(5).items()
        },
        "largest_raw_timestamp_gaps": [
            {"before": str(times[i - 1]), "after": str(times[i]), "delta": str(delta)}
            for i, delta in gaps.items()
        ],
        "rows_by_month": {
            str(k): int(v) for k, v in times.dt.to_period("M").value_counts().sort_index().items()
        },
    }


def main() -> None:
    downloads = verify_downloads()
    folder = ROOT / "pvdaq_2107"
    meter = pd.read_csv(folder / "2107_meter_15m_data_2025.csv")
    local = pd.to_datetime(meter["measured_on"])
    utc = local.dt.tz_localize(
        "America/Los_Angeles", ambiguous="NaT", nonexistent="NaT"
    ).dt.tz_convert("UTC")
    usable = utc.notna()
    power = pd.Series(meter.loc[usable, POWER].to_numpy(), index=pd.DatetimeIndex(utc[usable]))
    if not power.index.is_unique or not power.index.is_monotonic_increasing:
        raise ValueError("Unexpected duplicate or unordered UTC meter timestamps")
    if not (power.index == power.index.floor("15min")).all():
        raise ValueError("Unexpected off-grid meter timestamps")
    hourly = power.resample("h", closed="left", label="left").agg(["count", "mean"])
    complete = hourly.loc[hourly["count"].eq(4)]
    daily_max = (
        pd.Series(meter[POWER].to_numpy(), index=pd.DatetimeIndex(local)).resample("D").max()
    )

    weather_frames = []
    for path in sorted((ROOT / "open_meteo").glob("gfs_global_previous_day1_*.json")):
        data = json.loads(path.read_text())
        if data["utc_offset_seconds"] != 0:
            raise ValueError("Expected weather timestamps in UTC")
        frame = pd.DataFrame(data["hourly"])
        frame.index = pd.to_datetime(frame.pop("time"), utc=True)
        weather_frames.append(frame)
    weather = pd.concat(weather_frames).sort_index()
    if not weather.index.is_unique:
        raise ValueError("Overlapping weather snapshots require explicit reconciliation")
    # Meter metadata says left-aligned; radiation is averaged over the preceding hour.
    # Thus power [T,T+1h) uses forecast radiation at T+1h. Temperature/cloud are
    # instantaneous forecasts at that endpoint, not measured hourly averages.
    aligned = weather.reindex(complete.index + pd.Timedelta(hours=1))[WEATHER]

    environment = pd.read_csv(folder / "2107_environment_15m_data_2025.csv")
    env_time = pd.to_datetime(environment["utc_measured_on"])
    peak_hours = {}
    for year in sorted(env_time.dt.year.unique()):
        subset = environment.loc[env_time.dt.year.eq(year), TEMPERATURE]
        means = subset.groupby(env_time.loc[subset.index].dt.hour).mean()
        peak_hours[str(year)] = int(means.idxmax())

    local_hours = complete.index.tz_convert("America/Los_Angeles")
    summary = {
        "purpose": "Selection audit; counts depend on the documented interval/time policy",
        "downloads_verified": downloads,
        "pvdaq_files": [describe_csv(path) for path in sorted(folder.glob("*.csv"))],
        "candidate_hourly_target": {
            "source_clock": "America/Los_Angeles, based on system metadata and DST jumps",
            "interval_policy": "Left-aligned quarter-hour averages, per meter time_interval=L",
            "dst_ambiguous_or_nonexistent_rows_excluded": int((~usable).sum()),
            "complete_four_quarter_hours": len(complete),
            "first_interval_start_utc": complete.index.min().isoformat(),
            "last_interval_start_utc": complete.index.max().isoformat(),
            "complete_hours_by_local_year": {
                str(year): int((local_hours.year == year).sum())
                for year in sorted(set(local_hours.year))
            },
            "all_zero_local_days_to_investigate": [
                str(day.date()) for day in daily_max.loc[daily_max.eq(0)].index
            ],
        },
        "weather_archive": {
            "product": "Open-Meteo Previous Runs, gfs_global, previous_day1",
            "rows": len(weather),
            "first_valid_time_utc": weather.index.min().isoformat(),
            "last_valid_time_utc": weather.index.max().isoformat(),
            "null_counts": weather[WEATHER].isna().sum().to_dict(),
            "complete_target_hours_with_all_weather_features": int(
                aligned.notna().all(axis=1).sum()
            ),
        },
        "ambient_temperature_diagnostic": {
            "peak_mean_temperature_raw_clock_hour_by_year": peak_hours,
            "interpretation": "Suspected clock discontinuity; not a confirmed timezone correction",
        },
        "limitations": [
            "Counts precede lag construction, telemetry delay, outage review and model evaluation.",
            "Weather archive offsets do not contain exact historical publication timestamps.",
            "No production preprocessing, target cleaning, fitted model or accuracy claim is made.",
        ],
    }
    output = ROOT / "audit_summary.json"
    output.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
