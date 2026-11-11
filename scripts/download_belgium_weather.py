"""Download the versioned Belgian Open-Meteo archived-forecast weather grid.

The raw responses are immutable inputs and are ignored by Git. The generated
manifest records request URLs, returned grid coordinates, units, coverage, and
SHA-256 hashes. Existing files are never overwritten unless ``--force`` is used.

Run from the repository root:
    uv run python -m scripts.download_belgium_weather
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

API_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "belgium_weather_grid.json"
DEFAULT_OUTPUT = ROOT / "data" / "raw" / "belgium_weather_archive"
EXPECTED_UNITS = {
    "time": "iso8601",
    "temperature_2m_previous_day1": "°C",
    "cloud_cover_previous_day1": "%",
    "shortwave_radiation_previous_day1": "W/m²",
}


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date: {value}") from exc


def expected_hour_count(start_date: str, end_date: str) -> int:
    start = parse_date(start_date)
    end = parse_date(end_date)
    if end < start:
        raise ValueError(f"end_date {end} precedes start_date {start}")
    return ((end - start).days + 1) * 24


def load_grid_config(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read weather-grid config {path}: {exc}") from exc

    required = {"schema_version", "timezone", "model", "hourly_variables", "periods", "points"}
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"Weather-grid config is missing keys: {missing}")
    if config["timezone"] != "GMT":
        raise ValueError("Weather archive must use GMT/UTC timestamps.")
    if config["model"] != "gfs_global":
        raise ValueError("The first experiment requires the pinned gfs_global model.")
    if config["hourly_variables"] != list(EXPECTED_UNITS)[1:]:
        raise ValueError("Configured weather variables differ from the reviewed contract.")

    point_ids = [point.get("id") for point in config["points"]]
    if not point_ids or len(point_ids) != len(set(point_ids)):
        raise ValueError("Weather-grid point IDs must be present and unique.")
    period_ids = [period.get("id") for period in config["periods"]]
    if not period_ids or len(period_ids) != len(set(period_ids)):
        raise ValueError("Weather-grid period IDs must be present and unique.")

    for point in config["points"]:
        latitude = float(point["latitude"])
        longitude = float(point["longitude"])
        if not (49.0 <= latitude <= 52.0 and 2.0 <= longitude <= 7.0):
            raise ValueError(f"Configured point {point['id']} is outside the Belgium bounds.")
    for period in config["periods"]:
        expected_hour_count(period["start_date"], period["end_date"])
    return config


def build_parameters(config: dict[str, Any], point: dict, period: dict) -> dict[str, str | float]:
    return {
        "latitude": float(point["latitude"]),
        "longitude": float(point["longitude"]),
        "start_date": period["start_date"],
        "end_date": period["end_date"],
        "hourly": ",".join(config["hourly_variables"]),
        "models": config["model"],
        "timezone": config["timezone"],
    }


def validate_payload(
    payload: dict[str, Any], *, config: dict[str, Any], point: dict, period: dict
) -> dict[str, Any]:
    if payload.get("utc_offset_seconds") != 0 or payload.get("timezone") != "GMT":
        raise ValueError(f"{point['id']} {period['id']} did not return GMT/UTC data.")

    hourly = payload.get("hourly")
    units = payload.get("hourly_units")
    if not isinstance(hourly, dict) or not isinstance(units, dict):
        raise ValueError(f"{point['id']} {period['id']} lacks hourly data or units.")
    columns = ["time", *config["hourly_variables"]]
    missing = sorted(set(columns) - set(hourly))
    if missing:
        raise ValueError(f"{point['id']} {period['id']} is missing arrays: {missing}")

    lengths = {column: len(hourly[column]) for column in columns}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"Unequal arrays for {point['id']} {period['id']}: {lengths}")
    rows = next(iter(lengths.values()))
    expected_rows = expected_hour_count(period["start_date"], period["end_date"])
    if rows != expected_rows:
        raise ValueError(
            f"{point['id']} {period['id']} returned {rows} hours; expected {expected_rows}."
        )

    wrong_units = {
        column: {"actual": units.get(column), "expected": expected}
        for column, expected in EXPECTED_UNITS.items()
        if units.get(column) != expected
    }
    if wrong_units:
        raise ValueError(f"Unexpected units for {point['id']} {period['id']}: {wrong_units}")

    expected_first = f"{period['start_date']}T00:00"
    expected_last = f"{period['end_date']}T23:00"
    if hourly["time"][0] != expected_first or hourly["time"][-1] != expected_last:
        raise ValueError(f"Unexpected time bounds for {point['id']} {period['id']}.")

    returned_latitude = float(payload["latitude"])
    returned_longitude = float(payload["longitude"])
    if not (49.0 <= returned_latitude <= 52.0 and 2.0 <= returned_longitude <= 7.0):
        raise ValueError(f"Returned grid point for {point['id']} is outside Belgium bounds.")

    null_counts = {
        column: sum(value is None for value in hourly[column])
        for column in config["hourly_variables"]
    }
    clouds = hourly["cloud_cover_previous_day1"]
    radiation = hourly["shortwave_radiation_previous_day1"]
    range_warning_counts = {
        "cloud_cover_outside_0_100": sum(
            value is not None and not 0 <= value <= 100 for value in clouds
        ),
        "negative_shortwave_radiation": sum(value is not None and value < 0 for value in radiation),
    }
    return {
        "rows": rows,
        "first_valid_time": hourly["time"][0],
        "last_valid_time": hourly["time"][-1],
        "returned_coordinates": {
            "latitude": returned_latitude,
            "longitude": returned_longitude,
            "elevation_m": payload.get("elevation"),
        },
        "units": units,
        "null_counts": null_counts,
        "range_warning_counts": range_warning_counts,
    }


def fetch_one(
    client: httpx.Client,
    *,
    config: dict[str, Any],
    point: dict,
    period: dict,
    output_dir: Path,
    force: bool,
) -> dict[str, Any]:
    filename = f"{point['id']}__{period['id']}.json"
    path = output_dir / filename
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite raw file without --force: {path}")

    parameters = build_parameters(config, point, period)
    requested_at = datetime.now(UTC)
    response = client.get(API_URL, params=parameters)
    retrieved_at = datetime.now(UTC)
    response.raise_for_status()
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise ValueError(f"Open-Meteo returned invalid JSON for {filename}.") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Open-Meteo returned a non-object payload for {filename}.")

    audit = validate_payload(payload, config=config, point=point, period=period)
    content = response.content
    temporary_path = path.with_suffix(".json.part")
    temporary_path.write_bytes(content)
    temporary_path.replace(path)

    return {
        "file": filename,
        "point_id": point["id"],
        "point_label": point["label"],
        "period_id": period["id"],
        "requested_coordinates": {
            "latitude": float(point["latitude"]),
            "longitude": float(point["longitude"]),
        },
        "request_url": str(response.request.url),
        "requested_at_utc": requested_at.isoformat(),
        "retrieved_at_utc": retrieved_at.isoformat(),
        "http_status": response.status_code,
        "content_type": response.headers.get("content-type"),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        **audit,
    }


def write_manifest(
    output_dir: Path, config_path: Path, config: dict[str, Any], files: list[dict[str, Any]]
) -> Path:
    unique_returned_points = {
        (
            entry["returned_coordinates"]["latitude"],
            entry["returned_coordinates"]["longitude"],
        )
        for entry in files
    }
    aggregate_null_counts = {
        variable: sum(entry["null_counts"][variable] for entry in files)
        for variable in config["hourly_variables"]
    }
    warning_names = sorted(
        {warning for entry in files for warning in entry["range_warning_counts"]}
    )
    aggregate_range_warning_counts = {
        warning: sum(entry["range_warning_counts"].get(warning, 0) for entry in files)
        for warning in warning_names
    }
    manifest = {
        "schema_version": "belgium-weather-archive-manifest-v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "purpose": "Forecast-time weather features for the Belgian regional solar experiment",
        "source": "Open-Meteo Previous Runs API; underlying model NOAA GFS",
        "licence": "Open-Meteo data: CC BY 4.0; hosted free API restricted to noncommercial use",
        "source_documentation": "https://open-meteo.com/en/docs/previous-runs-api",
        "grid_config": str(config_path.relative_to(ROOT)),
        "grid_schema_version": config["schema_version"],
        "model": config["model"],
        "forecast_offset": config["forecast_offset"],
        "timezone": config["timezone"],
        "requested_points": len(config["points"]),
        "unique_returned_grid_points": len(unique_returned_points),
        "summary": {
            "files": len(files),
            "payload_bytes": sum(entry["bytes"] for entry in files),
            "point_hour_rows": sum(entry["rows"] for entry in files),
            "null_counts": aggregate_null_counts,
            "range_warning_counts": aggregate_range_warning_counts,
        },
        "files": files,
    }
    manifest_path = output_dir / "download_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Replace existing raw response files.")
    args = parser.parse_args()

    config_path = args.config.resolve()
    output_dir = args.output_dir.resolve()
    config = load_grid_config(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    timeout = httpx.Timeout(120.0, connect=30.0)
    headers = {"User-Agent": "solar-forecast-research/0.1 (archived weather acquisition)"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for point in config["points"]:
            for period in config["periods"]:
                print(f"Downloading {point['id']} / {period['id']} ...")
                entry = fetch_one(
                    client,
                    config=config,
                    point=point,
                    period=period,
                    output_dir=output_dir,
                    force=args.force,
                )
                entries.append(entry)

    manifest_path = write_manifest(output_dir, config_path, config, entries)
    total_bytes = sum(entry["bytes"] for entry in entries)
    total_nulls = sum(sum(entry["null_counts"].values()) for entry in entries)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "files": len(entries),
                "bytes": total_bytes,
                "weather_null_cells": total_nulls,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
