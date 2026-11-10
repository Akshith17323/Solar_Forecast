from pathlib import Path

import pytest

from project_backend.errors import AppError
from project_backend.providers import load_csv, parse_csv_bytes


def test_utf8_bom_csv_supported():
    assert parse_csv_bytes(b"\xef\xbb\xbfvalue\n12\n") == [{"value": "12"}]


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"", "invalid_csv_header"),
        (b",value\n1,2\n", "invalid_csv_header"),
        (b"value,value\n1,2\n", "duplicate_csv_header"),
        (b"a,b\n1\n", "invalid_csv_row"),
        (b"a\n1,2\n", "invalid_csv_row"),
        (b'a\n"unterminated\n', "malformed_csv"),
        (b"\xff", "invalid_encoding"),
    ],
)
def test_bad_csv_has_actionable_errors(content, code):
    with pytest.raises(AppError) as error:
        parse_csv_bytes(content)
    assert error.value.code == code


def test_header_only_csv_is_empty():
    assert parse_csv_bytes(b"value\n") == []


def test_upload_byte_limit():
    with pytest.raises(AppError) as error:
        parse_csv_bytes(b"value\n12\n", max_bytes=4)
    assert error.value.status_code == 413


def test_csv_record_limit():
    with pytest.raises(AppError) as error:
        parse_csv_bytes(b"value\n1\n2\n", max_records=1)
    assert error.value.status_code == 413


def test_missing_file_is_actionable(tmp_path):
    with pytest.raises(AppError) as error:
        load_csv(Path(tmp_path / "missing.csv"))
    assert error.value.code == "unreadable_file"
