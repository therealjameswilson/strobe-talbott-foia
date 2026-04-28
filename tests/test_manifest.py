import csv
import json
from pathlib import Path

import pytest

from scripts import build_site

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MANIFEST = PROJECT_ROOT / "data" / "sample_manifest.json"
ENRICHED_CSV = PROJECT_ROOT / "data" / "manifest_enriched.csv"
DESCRIPTIONS_JSON = PROJECT_ROOT / "data" / "manifest_descriptions.json"
RAW_MANIFEST_CSV = PROJECT_ROOT / "data" / "manifest.csv"


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


def _read_enriched_rows() -> list[dict[str, str]]:
    with ENRICHED_CSV.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.skipif(
    not ENRICHED_CSV.exists(), reason="enriched manifest not built in this checkout"
)
def test_enriched_manifest_has_one_row_per_source_row() -> None:
    raw_rows = list(csv.DictReader(RAW_MANIFEST_CSV.open(encoding="utf-8", newline="")))
    enriched_rows = _read_enriched_rows()
    assert len(enriched_rows) == len(raw_rows)


@pytest.mark.skipif(
    not ENRICHED_CSV.exists(), reason="enriched manifest not built in this checkout"
)
def test_enriched_manifest_descriptions_are_pdf_url_unique() -> None:
    rows = _read_enriched_rows()
    pdf_urls = [r["pdf_url"] for r in rows if r.get("pdf_url")]
    descriptions = [r["description"] for r in rows if r.get("pdf_url")]
    assert len(set(pdf_urls)) == len(pdf_urls), "pdf_url values must be globally unique"
    assert len(set(descriptions)) == len(descriptions), (
        "every pdf_url must carry its own description; duplicates indicate the "
        "enrichment pipeline is keying by document_id rather than pdf_url"
    )


@pytest.mark.skipif(
    not DESCRIPTIONS_JSON.exists(),
    reason="descriptions JSON not built in this checkout",
)
def test_descriptions_json_keyed_by_pdf_url() -> None:
    payload = json.loads(DESCRIPTIONS_JSON.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = list(csv.DictReader(RAW_MANIFEST_CSV.open(encoding="utf-8", newline="")))
    expected = {r["pdf_url"] for r in rows if r.get("pdf_url")}
    assert set(payload.keys()) == expected
    for entry in payload.values():
        assert entry.get("description")
        assert entry.get("source") in {"pdf", "metadata"}


@pytest.mark.skipif(
    not ENRICHED_CSV.exists(), reason="enriched manifest not built in this checkout"
)
def test_repeated_document_id_has_distinct_descriptions() -> None:
    """Same C-number across different release folders must not share text."""
    rows = _read_enriched_rows()
    by_doc: dict[str, set[str]] = {}
    for r in rows:
        doc = r.get("document_id", "")
        if not doc:
            continue
        by_doc.setdefault(doc, set()).add(r["description"])
    repeated = {doc: descs for doc, descs in by_doc.items() if len(descs) > 1 or len(descs) == 1}
    # At least one document_id must repeat across rows; for those, distinct
    # descriptions per pdf_url is the contract.
    repeats = {
        doc: descs
        for doc, descs in by_doc.items()
        if sum(1 for r in rows if r["document_id"] == doc) > 1
    }
    assert repeats, "expected at least one repeated document_id in the manifest"
    for doc, descs in repeats.items():
        row_count = sum(1 for r in rows if r["document_id"] == doc)
        assert len(descs) == row_count, (
            f"document_id {doc} appears in {row_count} rows but only {len(descs)} "
            "unique descriptions — pdf_url-level uniqueness is broken"
        )
