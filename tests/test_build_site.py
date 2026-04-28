from pathlib import Path

from scripts import build_site

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MANIFEST = PROJECT_ROOT / "data" / "sample_manifest.json"


def test_build_site_creates_index_page(tmp_path: Path) -> None:
    build_site.build_site(SAMPLE_MANIFEST, tmp_path, "Test Site")
    index_page = tmp_path / "index.html"
    assert index_page.exists()
    page_text = index_page.read_text(encoding="utf-8")
    assert "Document register for FOIA case F-2017-13804" in page_text
    assert "5 annotated records" in page_text
    assert '<table class="document-table">' in page_text
    assert "./docs/C00000001.html" in page_text
    assert (tmp_path / "semantic.html").exists()
    assert (tmp_path / "assets" / "js" / "site.js").exists()


def test_build_site_creates_document_pages(tmp_path: Path) -> None:
    records = build_site.build_site(SAMPLE_MANIFEST, tmp_path, "Test Site")
    for record in records:
        document_page = tmp_path / "docs" / f"{record.id}.html"
        assert document_page.exists()
        page_text = document_page.read_text(encoding="utf-8")
        assert record.source_pdf_url in page_text
        assert record.id in page_text
        assert "Copy citation" in page_text
        assert "Open Source PDF" in page_text
        assert build_site.build_citation(record) in page_text
