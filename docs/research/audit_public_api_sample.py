"""Reproduce the public-API source-selection audit from frozen local responses.

Run from the project root:
    uv run --frozen --no-sync python docs/research/audit_public_api_sample.py

Uses pandas from the UI extra. No network calls, training, or production ingestion.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2] / "data/raw/dataset_review/operational_public_apis"


def read_json(name: str) -> dict:
    return json.loads((ROOT / name).read_text())


def verify_downloads() -> dict:
    manifest = read_json("download_manifest.json")
    for entry in manifest["files"]:
        path = ROOT / entry["file"]
        payload = path.read_bytes()
        if len(payload) != entry["bytes"]:
            raise ValueError(f"Size differs from recorded download: {path}")
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError(f"Checksum differs from recorded download: {path}")
    return {entry["file"]: entry for entry in manifest["files"]}


def indexed_generation(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.pop("datetime"), utc=True)
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("Generation timestamps require duplicate/order reconciliation")
    if not (frame.index == frame.index.floor("15min")).all():
        raise ValueError("Unexpected off-grid generation timestamps")
    if not frame["region"].eq("Belgium").all():
        raise ValueError("Expected only the Belgium aggregate")
    if "gridconnectiontype" in frame and not frame["gridconnectiontype"].eq("Total").all():
        raise ValueError("Expected only the Total grid-connection category")
    if "resolutioncode" in frame and not frame["resolutioncode"].eq("PT15M").all():
        raise ValueError("Unexpected source interval duration")
    return frame


def describe_history() -> dict:
    frame = indexed_generation(pd.read_csv(ROOT / "belgium_2024_2025.csv", sep=";"))
    expected = pd.date_range("2024-01-01", "2026-01-01", freq="15min", inclusive="left", tz="UTC")
    power = frame["measured"]
    null_times = frame.index[power.isna()]
    hourly_count = power.resample("h", closed="left", label="left").count()
    complete = hourly_count[hourly_count.eq(4)]
    return {
        "source": "ods032, region=Belgium",
        "target_meaning": "Operator-published measured/upscaled PV power estimate, MW",
        "rows": len(frame),
        "expected_quarter_hours": len(expected),
        "missing_timestamps": len(expected.difference(frame.index)),
        "unexpected_timestamps": len(frame.index.difference(expected)),
        "duplicate_timestamp_rows": int(frame.index.duplicated().sum()),
        "first_interval_start_utc": frame.index.min().isoformat(),
        "last_interval_start_utc": frame.index.max().isoformat(),
        "missing_cells": frame.isna().sum().to_dict(),
        "nonnull_target_rows": int(power.notna().sum()),
        "target_min_mw": float(power.min()),
        "target_max_mw": float(power.max()),
        "negative_target_rows": int(power.lt(0).sum()),
        "target_above_reported_capacity_rows": int(power.gt(frame["monitoredcapacity"]).sum()),
        "reported_capacity_min_mw": float(frame["monitoredcapacity"].min()),
        "reported_capacity_max_mw": float(frame["monitoredcapacity"].max()),
        "null_target_first_utc": null_times.min().isoformat() if len(null_times) else None,
        "null_target_last_utc": null_times.max().isoformat() if len(null_times) else None,
        "null_target_utc_clock_counts": null_times.strftime("%H:%M").value_counts().to_dict(),
        "null_target_brussels_clock_counts": (
            null_times.tz_convert("Europe/Brussels").strftime("%H:%M").value_counts().to_dict()
        ),
        "complete_four_quarter_hours": len(complete),
        "complete_hours_by_utc_year": {
            str(year): int((complete.index.year == year).sum())
            for year in sorted(set(complete.index.year))
        },
        "count_scope": "Before weather joins, lag availability, revisions, and model evaluation",
    }


def describe_generation_page(name: str, target: str, entry: dict) -> dict:
    payload = read_json(name)
    frame = indexed_generation(pd.DataFrame(payload["results"]))
    available = frame[target].notna()
    retrieved = pd.Timestamp(entry["retrieved_at_utc"])
    # A non-null live running average can still belong to an unfinished interval.
    # Even a closed interval can subsequently be revised by the operator.
    closed = frame.index + pd.Timedelta(minutes=15) <= retrieved
    latest = frame.index[available].max() if available.any() else None
    latest_closed = frame.index[available & closed].max() if (available & closed).any() else None
    return {
        "file": name,
        "target_field": target,
        "retrieved_at_utc": retrieved.isoformat(),
        "total_query_records": payload["total_count"],
        "saved_records": len(frame),
        "query_has_more_records_than_saved_page": payload["total_count"] > len(frame),
        "first_interval_start_utc": frame.index.min().isoformat(),
        "last_interval_start_utc": frame.index.max().isoformat(),
        "nonnull_target_rows": int(available.sum()),
        "null_target_rows": int((~available).sum()),
        "closed_nonnull_intervals_at_retrieval": int((available & closed).sum()),
        "unfinished_nonnull_intervals_at_retrieval": int((available & ~closed).sum()),
        "latest_nonnull_interval_start_utc": latest.isoformat() if latest is not None else None,
        "latest_closed_nonnull_interval_start_utc": (
            latest_closed.isoformat() if latest_closed is not None else None
        ),
        "target_max_mw": float(frame[target].max()) if available.any() else None,
        "interpretation": "Closure is not a finality or publication-latency guarantee",
    }


def describe_weather(name: str) -> dict:
    payload = read_json(name)
    if payload["utc_offset_seconds"] != 0:
        raise ValueError("Expected UTC weather timestamps")
    frame = pd.DataFrame(payload["hourly"])
    times = pd.to_datetime(frame.pop("time"), utc=True)
    if not times.is_unique or not times.is_monotonic_increasing:
        raise ValueError("Unexpected weather timestamp order or duplicates")
    return {
        "file": name,
        "scope": "Single Brussels grid-point access probe, not a national weather audit",
        "requested_coordinates": {"latitude": 50.85, "longitude": 4.35},
        "returned_coordinates": {
            "latitude": payload["latitude"],
            "longitude": payload["longitude"],
        },
        "hours": len(frame),
        "first_valid_time_utc": times.min().isoformat(),
        "last_valid_time_utc": times.max().isoformat(),
        "units": payload["hourly_units"],
        "null_counts": frame.isna().sum().to_dict(),
    }


def main() -> None:
    entries = verify_downloads()
    metadata = {}
    for source, target in (
        ("ods032", "measured"),
        ("ods209", "measured_upscaled"),
        ("ods210", "measured"),
    ):
        payload = read_json(f"{source}_metadata.json")
        if target not in {field["name"] for field in payload["fields"]}:
            raise ValueError(f"Expected target field absent from {source} metadata")
        metadata[source] = {
            "target_field": target,
            "data_processed": payload["metas"]["default"].get("data_processed"),
            "refresh_frequency": payload["metas"]["dcat"].get("accrualperiodicity"),
            "granularity": payload["metas"]["dcat"].get("granularity"),
            "license": payload["metas"]["default"].get("license"),
        }
    legacy = read_json("legacy_coverage.json")["results"][0]
    recent = read_json("recent_coverage.json")["results"][0]
    summary = {
        "purpose": "Offline source-selection audit; no forecast accuracy result",
        "downloads_verified": {
            "files": len(entries),
            "total_payload_bytes": sum(entry["bytes"] for entry in entries.values()),
        },
        "metadata": metadata,
        "legacy_nonnull_coverage_query": legacy,
        "recent_nonnull_coverage_query": recent,
        "migration_boundary_spacing_minutes": (
            pd.Timestamp(recent["first"]) - pd.Timestamp(legacy["last"])
        ).total_seconds()
        / 60,
        "legacy_2024_2025_audit": describe_history(),
        "recent_historical_sample": describe_generation_page(
            "belgium_recent_day.json", "measured_upscaled", entries["belgium_recent_day.json"]
        ),
        "live_sample": describe_generation_page(
            "belgium_live_page.json", "measured", entries["belgium_live_page.json"]
        ),
        "live_region_connection_combinations": read_json("live_dimensions.json")["results"],
        "weather_samples": [
            describe_weather(name) for name in sorted(entries) if name.startswith("brussels_")
        ],
        "limitations": [
            "API reachability and one live snapshot do not establish continuous availability.",
            "Live running averages and historical upscaled estimates may be revised.",
            "Adjacent schema boundaries do not prove equivalent estimation methodology.",
            "National weather/history matching and forecast-time availability remain unaudited.",
            "Elia full licence terms and service quotas were not retrieved successfully.",
        ],
    }
    text = json.dumps(summary, indent=2, allow_nan=False) + "\n"
    output = ROOT / "audit_summary.json"
    output.write_text(text)
    print(
        json.dumps(
            {
                "audit_file": str(output),
                "downloads_verified": summary["downloads_verified"],
                "legacy_2024_2025_audit": summary["legacy_2024_2025_audit"],
                "live_sample": summary["live_sample"],
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
