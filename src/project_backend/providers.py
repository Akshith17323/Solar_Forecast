"""Local CSV adapter plus a contract for a future, explicitly chosen API."""

import csv
from collections import Counter
from io import StringIO
from pathlib import Path
from typing import Any, Protocol

from project_backend.errors import AppError


class ExternalDataProvider(Protocol):
    """Implement URL selection, auth, timeouts, normalization and limits in the adapter.

    Never allow an arbitrary user-supplied URL to become the configured endpoint.
    Return canonical field names and units; do not return API keys in metadata.
    """

    def fetch_records(self, parameters: dict[str, Any]) -> list[dict[str, Any]]: ...


def parse_csv_bytes(
    content: bytes, *, max_bytes: int = 2 * 1024 * 1024, max_records: int = 10_000
) -> list[dict[str, Any]]:
    if len(content) > max_bytes:
        raise AppError("upload_too_large", f"CSV must be at most {max_bytes} bytes.", 413)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("invalid_encoding", "Save the CSV using UTF-8 encoding.") from exc

    reader = csv.DictReader(StringIO(text, newline=""), strict=True)
    records: list[dict[str, Any]] = []
    try:
        headers = reader.fieldnames
        if not headers or any(not header.strip() for header in headers):
            raise AppError("invalid_csv_header", "CSV needs a header with non-empty column names.")
        if any(count > 1 for count in Counter(headers).values()):
            raise AppError("duplicate_csv_header", "CSV column names must be unique.")
        for index, row in enumerate(reader, start=1):
            if index > max_records:
                raise AppError("too_many_records", f"Limit the file to {max_records} rows.", 413)
            if None in row or any(value is None for value in row.values()):
                raise AppError(
                    "invalid_csv_row",
                    f"Data row {index} has a different column count than the header.",
                )
            records.append(dict(row))
    except csv.Error as exc:
        raise AppError(
            "malformed_csv", "CSV cannot be parsed. Check quoting and delimiters."
        ) from exc
    return records


def load_csv(
    path: Path, *, max_bytes: int = 2 * 1024 * 1024, max_records: int = 10_000
) -> list[dict[str, Any]]:
    try:
        with path.open("rb") as source:
            content = source.read(max_bytes + 1)
    except OSError as exc:
        raise AppError(
            "unreadable_file", "Cannot read the CSV. Check the path and permissions."
        ) from exc
    return parse_csv_bytes(content, max_bytes=max_bytes, max_records=max_records)
