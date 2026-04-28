import json
from pathlib import Path

import pytest

from scripts import build_site

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MANIFEST = PROJECT_ROOT / "data" / "sample_manifest.json"


def test_manifest_loads() -> None:
    records = build_site.load_manifest(SAMPLE_MANIFEST)
    assert len(records) == 5
    assert records[0].case_number == "F-2017-13804"


def test_validate_records_accepts_sample_manifest() -> None:
    records = build_site.load_manifest(SAMPLE_MANIFEST)
    build_site.validate_records(records, SAMPLE_MANIFEST)


def test_normalize_document_id() -> None:
    assert build_site.normalize_document_id(" c 0000 0001 ") == "C00000001"


def test_every_sample_record_has_id_and_source_url() -> None:
    data = json.loads(SAMPLE_MANIFEST.read_text(encoding="utf-8"))
    assert all(record.get("id") for record in data)
    assert all(record.get("source_pdf_url") for record in data)


def test_validate_records_rejects_duplicate_ids() -> None:
    records = build_site.load_manifest(SAMPLE_MANIFEST)
    duplicate_records = [records[0], records[0]]

    with pytest.raises(ValueError, match="Duplicate document id C00000001"):
        build_site.validate_records(duplicate_records, SAMPLE_MANIFEST)


def test_validate_records_rejects_missing_text_path() -> None:
    records = build_site.load_manifest(SAMPLE_MANIFEST)
    broken_record = build_site.DocumentRecord(
        id=records[0].id,
        case_number=records[0].case_number,
        title=records[0].title,
        date=records[0].date,
        source_pdf_url=records[0].source_pdf_url,
        release_status=records[0].release_status,
        text_path="data/text/DOES_NOT_EXIST.txt",
    )

    with pytest.raises(ValueError, match="references missing text_path"):
        build_site.validate_records([broken_record], SAMPLE_MANIFEST)


def test_validate_records_rejects_unexpected_case_number() -> None:
    records = build_site.load_manifest(SAMPLE_MANIFEST)
    wrong_case_record = build_site.DocumentRecord(
        id=records[0].id,
        case_number="F-0000-00000",
        title=records[0].title,
        date=records[0].date,
        source_pdf_url=records[0].source_pdf_url,
        release_status=records[0].release_status,
        text_path=records[0].text_path,
    )

    with pytest.raises(ValueError, match="expected F-2017-13804"):
        build_site.validate_records([wrong_case_record], SAMPLE_MANIFEST)
