"""Build leakage-safe chronological model-training files from frozen raw data.

The script reads the reviewed Elia target and nine-point Belgian Open-Meteo
archive. It writes train, validation, and untouched test CSV files plus a schema
and checksum manifest. Raw files are never modified.

Run from the repository root after downloading the raw weather archive:
    uv run python -m scripts.prepare_training_data
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRAINING_CONFIG = ROOT / "config" / "training_dataset.json"
DEFAULT_GRID_CONFIG = ROOT / "config" / "belgium_weather_grid.json"
DEFAULT_ELIA_PATH = ROOT / "data" / "raw" / "elia_generation" / "belgium_2024_2025.csv"
DEFAULT_WEATHER_ROOT = ROOT / "data" / "raw" / "belgium_weather_archive"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "model_training"

ELIA_COLUMNS = [
    "datetime",
    "resolutioncode",
    "region",
    "measured",
    "dayaheadforecast",
    "monitoredcapacity",
]
WEATHER_SOURCE_TO_CANONICAL = {
    "temperature_2m_previous_day1": "temperature_2m_c",
    "cloud_cover_previous_day1": "cloud_cover_pct",
    "shortwave_radiation_previous_day1": "shortwave_radiation_w_m2",
}
EXPECTED_WEATHER_UNITS = {
    "time": "iso8601",
    "temperature_2m_previous_day1": "°C",
    "cloud_cover_previous_day1": "%",
    "shortwave_radiation_previous_day1": "W/m²",
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return payload


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_elia_hourly(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    try:
        raw = pd.read_csv(
            path,
            sep=";",
            encoding="utf-8",
            dtype={"datetime": "string", "resolutioncode": "string", "region": "string"},
            low_memory=False,
        )
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise ValueError(f"Cannot read Elia history {path}: {exc}") from exc

    missing = sorted(set(ELIA_COLUMNS) - set(raw.columns))
    if missing:
        raise ValueError(f"Elia history is missing columns: {missing}")
    raw = raw.loc[:, ELIA_COLUMNS].copy()
    raw["timestamp"] = pd.to_datetime(raw["datetime"], format="ISO8601", errors="raise", utc=True)
    for column in ["measured", "dayaheadforecast", "monitoredcapacity"]:
        raw[column] = pd.to_numeric(raw[column], errors="raise")
    raw = raw.sort_values("timestamp", kind="stable").reset_index(drop=True)

    if set(raw["region"].dropna().unique()) != {"Belgium"}:
        raise ValueError("Elia history must contain only the Belgium aggregate.")
    if set(raw["resolutioncode"].dropna().unique()) != {"PT15M"}:
        raise ValueError("Elia history must contain only PT15M intervals.")
    if raw["timestamp"].duplicated().any():
        raise ValueError("Elia history contains duplicate timestamps.")
    expected_index = pd.date_range(raw["timestamp"].min(), raw["timestamp"].max(), freq="15min")
    if not pd.DatetimeIndex(raw["timestamp"]).equals(expected_index):
        raise ValueError("Elia history has missing, unexpected, or unordered timestamps.")
    if raw["measured"].dropna().lt(0).any():
        raise ValueError("Elia history contains negative generation values.")
    if raw["measured"].gt(raw["monitoredcapacity"]).any():
        raise ValueError("Elia generation exceeds reported monitored capacity.")

    hourly = (
        raw.set_index("timestamp")
        .resample("1h", closed="left", label="left")
        .agg(
            power_generation_mw=("measured", "mean"),
            target_quarters=("measured", "count"),
            source_quarters=("resolutioncode", "count"),
            monitored_capacity_mw=("monitoredcapacity", "mean"),
        )
        .reset_index()
    )
    hourly["complete_target_hour"] = (hourly["target_quarters"] == 4) & (
        hourly["source_quarters"] == 4
    )
    hourly.loc[~hourly["complete_target_hour"], "power_generation_mw"] = np.nan

    if not hourly["timestamp"].diff().dropna().eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Hourly Elia target is not continuous.")

    audit = {
        "raw_quarter_hour_rows": len(raw),
        "raw_missing_targets": int(raw["measured"].isna().sum()),
        "hourly_rows": len(hourly),
        "complete_target_hours": int(hourly["complete_target_hour"].sum()),
        "first_target_hour_utc": hourly["timestamp"].min().isoformat(),
        "last_target_hour_utc": hourly["timestamp"].max().isoformat(),
        "sha256": sha256_file(path),
    }
    return hourly, audit


def verify_weather_file(path: Path, entry: dict[str, Any]) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Weather response is missing: {path}")
    if path.stat().st_size != entry["bytes"]:
        raise ValueError(f"Weather response size differs from its manifest: {path.name}")
    if sha256_file(path) != entry["sha256"]:
        raise ValueError(f"Weather response hash differs from its manifest: {path.name}")


def load_weather_wide(
    weather_root: Path, manifest_path: Path, grid_config_path: Path
) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    manifest = read_json(manifest_path)
    grid = read_json(grid_config_path)
    if manifest.get("grid_schema_version") != grid.get("schema_version"):
        raise ValueError("Weather manifest does not match the configured Belgian grid.")

    point_order = [point["id"] for point in grid["points"]]
    if manifest.get("unique_returned_grid_points") != len(point_order):
        raise ValueError("Weather requests did not return one unique grid cell per point.")
    expected_source_columns = ["time", *WEATHER_SOURCE_TO_CANONICAL]
    frames: list[pd.DataFrame] = []

    for entry in manifest["files"]:
        path = weather_root / entry["file"]
        verify_weather_file(path, entry)
        payload = read_json(path)
        hourly = payload.get("hourly")
        units = payload.get("hourly_units")
        if not isinstance(hourly, dict) or not isinstance(units, dict):
            raise ValueError(f"Weather response lacks hourly data or units: {path.name}")
        missing = sorted(set(expected_source_columns) - set(hourly))
        if missing:
            raise ValueError(f"{path.name} is missing weather arrays: {missing}")
        lengths = {column: len(hourly[column]) for column in expected_source_columns}
        if len(set(lengths.values())) != 1 or next(iter(lengths.values())) != entry["rows"]:
            raise ValueError(f"Unexpected weather array lengths in {path.name}: {lengths}")
        wrong_units = {
            column: {"actual": units.get(column), "expected": expected}
            for column, expected in EXPECTED_WEATHER_UNITS.items()
            if units.get(column) != expected
        }
        if wrong_units:
            raise ValueError(f"Unexpected weather units in {path.name}: {wrong_units}")
        if payload.get("utc_offset_seconds") != 0:
            raise ValueError(f"Weather response is not GMT/UTC: {path.name}")

        frame = pd.DataFrame({column: hourly[column] for column in expected_source_columns})
        frame["weather_valid_time"] = pd.to_datetime(
            frame.pop("time"), format="%Y-%m-%dT%H:%M", errors="raise", utc=True
        )
        for source_column, canonical_column in WEATHER_SOURCE_TO_CANONICAL.items():
            frame[canonical_column] = pd.to_numeric(frame.pop(source_column), errors="raise")
        frame["point_id"] = entry["point_id"]
        frames.append(frame)

    weather = pd.concat(frames, ignore_index=True).sort_values(
        ["point_id", "weather_valid_time"], kind="stable"
    )
    if set(weather["point_id"].unique()) != set(point_order):
        raise ValueError("Loaded weather points differ from the configured Belgian grid.")
    if weather.duplicated(["point_id", "weather_valid_time"]).any():
        raise ValueError("Weather archive contains duplicate point/time rows.")
    deltas = weather.groupby("point_id")["weather_valid_time"].diff().dropna()
    if not deltas.eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Weather archive has an hourly timestamp gap.")

    cloud_raw = weather["cloud_cover_pct"]
    if not cloud_raw.dropna().between(-1, 101).all():
        raise ValueError("Cloud cover is outside the reviewed -1% to 101% source range.")
    weather["cloud_cover_was_clipped"] = cloud_raw.notna() & ~cloud_raw.between(0, 100)
    weather["cloud_cover_pct"] = cloud_raw.clip(0, 100)
    if weather["shortwave_radiation_w_m2"].dropna().lt(0).any():
        raise ValueError("Weather archive contains negative shortwave radiation.")

    # Radiation at valid time T+1 is the preceding-hour mean for target [T, T+1).
    weather["timestamp"] = weather["weather_valid_time"] - pd.Timedelta(hours=1)
    canonical_weather = list(WEATHER_SOURCE_TO_CANONICAL.values())
    pivot = weather.pivot(index="timestamp", columns="point_id", values=canonical_weather)
    expected_columns = pd.MultiIndex.from_tuples(
        [(variable, point_id) for variable in canonical_weather for point_id in point_order]
    )
    pivot = pivot.reindex(columns=expected_columns).sort_index()
    pivot.columns = [f"{variable}__{point_id}" for variable, point_id in pivot.columns]

    spatial_columns = list(pivot.columns)
    for variable in canonical_weather:
        point_columns = [f"{variable}__{point_id}" for point_id in point_order]
        pivot[f"{variable}__grid_mean"] = pivot[point_columns].mean(axis=1)
        pivot[f"{variable}__grid_std"] = pivot[point_columns].std(axis=1, ddof=0)
    weather_feature_columns = list(pivot.columns)
    wide = pivot.reset_index()

    audit = {
        "point_hour_rows": len(weather),
        "grid_points": weather["point_id"].nunique(),
        "unique_valid_times": weather["weather_valid_time"].nunique(),
        "spatial_weather_features": len(spatial_columns),
        "aggregate_weather_features": len(weather_feature_columns) - len(spatial_columns),
        "cloud_values_clipped": int(weather["cloud_cover_was_clipped"].sum()),
        "weather_manifest_sha256": sha256_file(manifest_path),
        "weather_grid_config_sha256": sha256_file(grid_config_path),
    }
    return wide, weather_feature_columns, audit


def add_temporal_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    result = frame.copy()
    midpoint = result["timestamp"] + pd.Timedelta(minutes=30)
    hour_fraction = midpoint.dt.hour + midpoint.dt.minute / 60
    day_fraction = midpoint.dt.day_of_year - 1 + hour_fraction / 24
    result["target_hour_utc"] = result["timestamp"].dt.hour.astype("int16")
    result["target_month"] = result["timestamp"].dt.month.astype("int8")
    result["target_day_of_year"] = result["timestamp"].dt.day_of_year.astype("int16")
    result["target_hour_sin"] = np.sin(2 * np.pi * hour_fraction / 24)
    result["target_hour_cos"] = np.cos(2 * np.pi * hour_fraction / 24)
    result["target_day_of_year_sin"] = np.sin(2 * np.pi * day_fraction / 365.2425)
    result["target_day_of_year_cos"] = np.cos(2 * np.pi * day_fraction / 365.2425)
    columns = [
        "target_hour_utc",
        "target_month",
        "target_day_of_year",
        "target_hour_sin",
        "target_hour_cos",
        "target_day_of_year_sin",
        "target_day_of_year_cos",
    ]
    return result, columns


def add_generation_lags(
    frame: pd.DataFrame, target_column: str, lags_hours: list[int]
) -> tuple[pd.DataFrame, list[str]]:
    if not lags_hours or any(not isinstance(lag, int) or lag <= 0 for lag in lags_hours):
        raise ValueError("Generation lags must be positive integer hours.")
    result = frame.sort_values("timestamp", kind="stable").reset_index(drop=True).copy()
    if not result["timestamp"].diff().dropna().eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Generation lags require a continuous hourly table.")
    columns: list[str] = []
    for lag in lags_hours:
        column = f"power_generation_lag_{lag}h_mw"
        result[column] = result[target_column].shift(lag)
        columns.append(column)
    return result, columns


def assign_splits(frame: pd.DataFrame, split_config: dict[str, Any]) -> pd.Series:
    split = pd.Series(pd.NA, index=frame.index, dtype="string", name="split")
    for name in ["train", "validation", "test"]:
        if name not in split_config:
            raise ValueError(f"Training config is missing the {name!r} split.")
        start = pd.Timestamp(split_config[name]["start"])
        end = pd.Timestamp(split_config[name]["end_exclusive"])
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError(f"Invalid UTC boundaries for split {name!r}.")
        mask = frame["timestamp"].ge(start) & frame["timestamp"].lt(end)
        if split.loc[mask].notna().any():
            raise ValueError(f"Split {name!r} overlaps another configured split.")
        split.loc[mask] = name
    return split


def build_training_dataset(
    *,
    training_config_path: Path,
    grid_config_path: Path,
    elia_path: Path,
    weather_root: Path,
) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    config = read_json(training_config_path)
    target_column = config["target_column"]
    hourly, elia_audit = load_elia_hourly(elia_path)
    hourly, lag_columns = add_generation_lags(
        hourly, target_column, config["generation_lags_hours"]
    )
    weather_wide, weather_columns, weather_audit = load_weather_wide(
        weather_root, weather_root / "download_manifest.json", grid_config_path
    )
    table = hourly.merge(weather_wide, on="timestamp", how="left", validate="one_to_one")
    table, temporal_columns = add_temporal_features(table)
    table["split"] = assign_splits(table, config["splits"])

    feature_columns = [
        "monitored_capacity_mw",
        *weather_columns,
        *temporal_columns,
        *lag_columns,
    ]
    if target_column in feature_columns:
        raise ValueError("Target leakage: target column appears in the feature list.")
    eligible = (
        table["split"].notna()
        & table["complete_target_hour"]
        & table[target_column].notna()
        & table[feature_columns].notna().all(axis=1)
    )
    dataset = table.loc[eligible, ["timestamp", "split", target_column, *feature_columns]].copy()
    dataset = dataset.sort_values("timestamp", kind="stable").reset_index(drop=True)

    numeric = dataset[[target_column, *feature_columns]].to_numpy(dtype="float64")
    if not np.isfinite(numeric).all():
        raise ValueError("Prepared training data contains missing or non-finite numeric values.")
    if dataset["timestamp"].duplicated().any():
        raise ValueError("Prepared training data contains duplicate timestamps.")
    if dataset[target_column].lt(0).any():
        raise ValueError("Prepared training target contains negative generation.")

    split_summary = {}
    for name in ["train", "validation", "test"]:
        part = dataset.loc[dataset["split"].eq(name)]
        if part.empty:
            raise ValueError(f"Prepared {name!r} split is empty.")
        split_summary[name] = {
            "rows": len(part),
            "first_timestamp_utc": part["timestamp"].min().isoformat(),
            "last_timestamp_utc": part["timestamp"].max().isoformat(),
        }

    audit = {
        "elia": elia_audit,
        "weather": weather_audit,
        "rows_before_complete_case_filter": len(table),
        "rows_after_complete_case_filter": len(dataset),
        "rows_excluded": len(table.loc[table["split"].notna()]) - len(dataset),
        "features": len(feature_columns),
        "splits": split_summary,
        "training_config_sha256": sha256_file(training_config_path),
    }
    return dataset, feature_columns, audit


def write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    frame.to_csv(
        temporary,
        index=False,
        date_format="%Y-%m-%dT%H:%M:%SZ",
        float_format="%.8f",
        lineterminator="\n",
    )
    temporary.replace(path)


def write_training_outputs(
    *,
    dataset: pd.DataFrame,
    feature_columns: list[str],
    audit: dict[str, Any],
    config: dict[str, Any],
    output_dir: Path,
    force: bool,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_paths = [output_dir / f"{name}.csv" for name in ["train", "validation", "test"]]
    expected_paths.append(output_dir / "dataset_manifest.json")
    existing = [path for path in expected_paths if path.exists()]
    if existing and not force:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"Refusing to replace generated files without --force: {names}")

    output_entries: list[dict[str, Any]] = []
    for name in ["train", "validation", "test"]:
        path = output_dir / f"{name}.csv"
        part = dataset.loc[dataset["split"].eq(name)].copy()
        write_csv_atomic(part, path)
        output_entries.append(
            {
                "split": name,
                "file": path.name,
                "rows": len(part),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    manifest = {
        "schema_version": config["schema_version"],
        "created_at_utc": datetime.now(UTC).isoformat(),
        "purpose": "Frozen chronological files for model training, selection, and final testing",
        "problem_statement": config["problem_statement"],
        "target": {
            "column": config["target_column"],
            "unit": config["target_unit"],
            "interval_minutes": config["target_interval_minutes"],
        },
        "weather_alignment": {
            "policy": "Weather valid time T+1 is aligned to target interval [T, T+1).",
            "forecast_product": "Open-Meteo gfs_global previous_day1",
            "valid_time_offset_hours": config["weather_valid_time_offset_hours"],
        },
        "generation_lags_hours": config["generation_lags_hours"],
        "evaluation_protocol": (
            "One-step-ahead rolling evaluation. A row may use observed generation from earlier "
            "hours in the same chronological split, but never its current or future target."
        ),
        "lag_availability_assumption": (
            "Lag values use final historical estimates. Before deployment, verify that the same "
            "lags are available from the live API by issue time and measure revisions."
        ),
        "excluded_from_features": [
            config["target_column"],
            "Elia dayaheadforecast (exact historical issue-time value unavailable)",
            "split",
            "timestamp",
        ],
        "feature_columns": feature_columns,
        "audit": audit,
        "files": output_entries,
        "reproduce": "uv run python -m scripts.prepare_training_data --force",
    }
    manifest_path = output_dir / "dataset_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-config", type=Path, default=DEFAULT_TRAINING_CONFIG)
    parser.add_argument("--grid-config", type=Path, default=DEFAULT_GRID_CONFIG)
    parser.add_argument("--elia-path", type=Path, default=DEFAULT_ELIA_PATH)
    parser.add_argument("--weather-root", type=Path, default=DEFAULT_WEATHER_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Replace generated output files.")
    args = parser.parse_args()

    training_config_path = args.training_config.resolve()
    grid_config_path = args.grid_config.resolve()
    elia_path = args.elia_path.resolve()
    weather_root = args.weather_root.resolve()
    output_dir = args.output_dir.resolve()
    config = read_json(training_config_path)
    dataset, feature_columns, audit = build_training_dataset(
        training_config_path=training_config_path,
        grid_config_path=grid_config_path,
        elia_path=elia_path,
        weather_root=weather_root,
    )
    manifest_path = write_training_outputs(
        dataset=dataset,
        feature_columns=feature_columns,
        audit=audit,
        config=config,
        output_dir=output_dir,
        force=args.force,
    )
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "rows": len(dataset),
                "features": len(feature_columns),
                "splits": audit["splits"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
