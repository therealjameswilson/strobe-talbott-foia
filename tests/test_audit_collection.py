from pathlib import Path

from scripts import audit_collection, build_site

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MANIFEST = PROJECT_ROOT / "data" / "sample_manifest.json"


def test_audit_reports_generated_pages(tmp_path: Path) -> None:
    site_dir = tmp_path / "site"
    build_site.build_site(SAMPLE_MANIFEST, site_dir, "Test Site")

    audit = audit_collection.build_audit(SAMPLE_MANIFEST, site_dir, tmp_path / "pdfs")

    assert audit["manifest_records"] == 5
    assert audit["unique_ids"] == 5
    assert audit["generated_document_pages"] == 5
    assert audit["duplicate_generated_pages"] == 0
