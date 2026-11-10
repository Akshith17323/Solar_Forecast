"""Validate a local file without starting the HTTP server or calling a live API."""

import argparse
import json
from pathlib import Path

from project_backend.config import Settings, load_profile
from project_backend.errors import AppError
from project_backend.providers import load_csv
from project_backend.validation import validate_records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--mode", choices=["historical", "inference"], default="historical")
    args = parser.parse_args()
    settings = Settings()
    try:
        profile = load_profile(args.profile or settings.profile_path)
        records = load_csv(
            args.csv_path, max_bytes=settings.max_upload_bytes, max_records=settings.max_records
        )
        report = validate_records(
            records,
            profile,
            mode=args.mode,
            max_records=settings.max_records,
            max_issues=settings.max_issues,
        ).report
    except (AppError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(report.model_dump_json(indent=2))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
