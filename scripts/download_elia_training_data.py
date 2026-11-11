"""Download and verify the frozen Elia generation source used for training.

The tracked source manifest contains the exact export URL, byte size, SHA-256,
schema, and expected coverage. A changed upstream response is rejected rather than
silently replacing the reviewed training target.

Run from the repository root:
    uv run python -m scripts.download_elia_training_data
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from io import StringIO
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "raw" / "elia_generation" / "source_manifest.json"
EXPECTED_COLUMNS = [
    "datetime",
    "resolutioncode",
    "region",
    "measured",
    "dayaheadforecast",
    "monitoredcapacity",
]


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read Elia source manifest {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("file"), dict):
        raise ValueError("Elia source manifest must contain a file object.")
    return payload


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_content(content: bytes, manifest: dict[str, Any]) -> dict[str, Any]:
    expected = manifest["file"]
    if len(content) != expected["bytes"]:
        raise ValueError(
            f"Elia payload has {len(content)} bytes; expected the reviewed {expected['bytes']}."
        )
    actual_hash = sha256_bytes(content)
    if actual_hash != expected["sha256"]:
        raise ValueError(
            "Elia payload hash differs from the reviewed snapshot. Do not silently replace "
            "training data; audit the upstream revision first."
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Elia payload is not UTF-8 CSV.") from exc

    reader = csv.reader(StringIO(text, newline=""), delimiter=expected["delimiter"])
    header = next(reader, None)
    if header != EXPECTED_COLUMNS:
        raise ValueError(f"Unexpected Elia CSV header: {header}")
    rows = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    for row in reader:
        if len(row) != len(EXPECTED_COLUMNS):
            raise ValueError(f"Elia row {rows + 1} has an unexpected column count.")
        rows += 1
        first_timestamp = first_timestamp or row[0]
        last_timestamp = row[0]
    if rows != expected["rows"]:
        raise ValueError(f"Elia payload has {rows} rows; expected {expected['rows']}.")
    if first_timestamp != expected["first_interval_start_utc"]:
        raise ValueError("Elia payload has an unexpected first timestamp.")
    if last_timestamp != expected["last_interval_start_utc"]:
        raise ValueError("Elia payload has an unexpected last timestamp.")
    return {"bytes": len(content), "sha256": actual_hash, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--force", action="store_true", help="Replace an existing verified file.")
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    manifest = read_manifest(manifest_path)
    output_path = manifest_path.parent / manifest["file"]["name"]

    if output_path.exists() and not args.force:
        audit = validate_content(output_path.read_bytes(), manifest)
        print(
            json.dumps({"status": "already_present", "file": str(output_path), **audit}, indent=2)
        )
        return 0

    timeout = httpx.Timeout(120.0, connect=30.0)
    headers = {"User-Agent": "solar-forecast-research/0.1 (training data acquisition)"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = client.get(manifest["source_url"])
        response.raise_for_status()
    content = response.content
    audit = validate_content(content, manifest)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".part")
    temporary_path.write_bytes(content)
    temporary_path.replace(output_path)
    print(json.dumps({"status": "downloaded", "file": str(output_path), **audit}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
