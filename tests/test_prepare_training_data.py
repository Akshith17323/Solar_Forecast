import pandas as pd
import pytest

from scripts.download_elia_training_data import sha256_bytes, validate_content
from scripts.prepare_training_data import (
    add_generation_lags,
    add_temporal_features,
    assign_splits,
)


def hourly_frame(rows: int = 8) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=rows, freq="1h", tz="UTC"),
            "power_generation_mw": [float(value) for value in range(rows)],
        }
    )


def test_generation_lags_only_use_earlier_targets():
    frame, columns = add_generation_lags(hourly_frame(), "power_generation_mw", [1, 3])

    assert columns == ["power_generation_lag_1h_mw", "power_generation_lag_3h_mw"]
    assert pd.isna(frame.loc[0, "power_generation_lag_1h_mw"])
    assert pd.isna(frame.loc[2, "power_generation_lag_3h_mw"])
    assert frame.loc[3, "power_generation_lag_1h_mw"] == 2.0
    assert frame.loc[3, "power_generation_lag_3h_mw"] == 0.0


def test_generation_lags_reject_timestamp_gaps():
    frame = hourly_frame().drop(index=2).reset_index(drop=True)

    with pytest.raises(ValueError, match="continuous hourly"):
        add_generation_lags(frame, "power_generation_mw", [1])


def test_chronological_split_boundaries_do_not_overlap():
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-09-30T23:00:00Z",
                    "2024-10-01T00:00:00Z",
                    "2024-12-31T23:00:00Z",
                    "2025-01-01T00:00:00Z",
                ],
                utc=True,
            )
        }
    )
    config = {
        "train": {"start": "2024-01-01T00:00:00Z", "end_exclusive": "2024-10-01T00:00:00Z"},
        "validation": {
            "start": "2024-10-01T00:00:00Z",
            "end_exclusive": "2025-01-01T00:00:00Z",
        },
        "test": {"start": "2025-01-01T00:00:00Z", "end_exclusive": "2026-01-01T00:00:00Z"},
    }

    assert assign_splits(frame, config).tolist() == ["train", "validation", "validation", "test"]


def test_temporal_features_are_finite_and_target_independent():
    source = hourly_frame(24)
    transformed, columns = add_temporal_features(source)

    assert len(columns) == 7
    assert transformed[columns].notna().all().all()
    assert transformed["power_generation_mw"].equals(source["power_generation_mw"])
    assert transformed["target_hour_sin"].between(-1, 1).all()
    assert transformed["target_hour_cos"].between(-1, 1).all()


def test_elia_download_validation_checks_frozen_content():
    content = (
        b"datetime;resolutioncode;region;measured;dayaheadforecast;monitoredcapacity\n"
        b"2024-01-01T00:00:00+00:00;PT15M;Belgium;0;0;100\n"
        b"2024-01-01T00:15:00+00:00;PT15M;Belgium;1;1;100\n"
    )
    manifest = {
        "file": {
            "bytes": len(content),
            "sha256": sha256_bytes(content),
            "delimiter": ";",
            "rows": 2,
            "first_interval_start_utc": "2024-01-01T00:00:00+00:00",
            "last_interval_start_utc": "2024-01-01T00:15:00+00:00",
        }
    }

    assert validate_content(content, manifest)["rows"] == 2
    with pytest.raises(ValueError, match="bytes"):
        validate_content(content + b"corrupt", manifest)
