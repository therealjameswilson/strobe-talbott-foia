import json
from pathlib import Path

from scripts import build_site

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MANIFEST = PROJECT_ROOT / "data" / "sample_manifest.json"


def test_build_site_creates_index_page(tmp_path: Path) -> None:
    build_site.build_site(SAMPLE_MANIFEST, tmp_path, "Test Site")
    index_page = tmp_path / "index.html"
    assert index_page.exists()
    page_text = index_page.read_text(encoding="utf-8")
    assert "Sample document register for case F-2017-13804" in page_text
    assert "Collection search and batch tools" in page_text
    assert "Download selected PDFs" in page_text
    assert '<table class="document-table">' in page_text
    assert 'id="document-table-body"' in page_text
    assert (tmp_path / "semantic.html").exists()
    assert (tmp_path / "assets" / "js" / "site.js").exists()
    assert (tmp_path / "assets" / "js" / "collection.js").exists()
    manifest_export = json.loads((tmp_path / "assets" / "search" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_export["document_count"] == 5
    assert manifest_export["record_count"] == 5
    assert manifest_export["records"][0]["page_url"] == "./docs/C00000001.html"
    assert manifest_export["records"][0]["document_id"] == "C00000001"
    assert manifest_export["records"][0]["pdf_url"].endswith("C00000001.pdf")
    doc_pages = json.loads((tmp_path / "assets" / "search" / "doc_pages.json").read_text(encoding="utf-8"))
    assert "C00000001" in doc_pages


def test_build_site_creates_document_pages(tmp_path: Path) -> None:
    records = build_site.build_site(SAMPLE_MANIFEST, tmp_path, "Test Site")
    for record in records:
        document_page = tmp_path / "docs" / f"{record.id}.html"
        assert document_page.exists()
        page_text = document_page.read_text(encoding="utf-8")
        assert record.source_pdf_url in page_text
        assert record.id in page_text
        assert "Copy citation" in page_text
        assert "Download original PDF" in page_text
        assert build_site.build_citation(record) in page_text


def test_build_site_surfaces_local_pdf_links_when_cached(tmp_path: Path) -> None:
    pdf_cache_dir = tmp_path / "pdfs"
    pdf_cache_dir.mkdir()
    (pdf_cache_dir / "C00000001.pdf").write_bytes(b"%PDF-1.4\n%placeholder\n")

    build_site.build_site(SAMPLE_MANIFEST, tmp_path / "out", "Test Site", pdf_cache_dir)

    index_page = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    document_page = (tmp_path / "out" / "docs" / "C00000001.html").read_text(encoding="utf-8")
    manifest_export = json.loads(
        (tmp_path / "out" / "assets" / "search" / "manifest.json").read_text(encoding="utf-8")
    )

    assert "Local PDF Cache" in index_page
    assert "Download local PDF" in document_page
    assert manifest_export["records"][0]["has_local_pdf"] is True
    assert manifest_export["records"][0]["local_pdf_url"] == "./pdfs/C00000001.pdf"


def test_build_site_allows_manifest_without_text_files(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_payload = [
        {
            "id": "C12345678",
            "case_number": "F-2017-13804",
            "title": "Live metadata only record",
            "date": "1996-01-01",
            "source_pdf_url": "https://foia.state.gov/DOCUMENTS/example/C12345678.pdf",
            "release_status": "RELEASE IN FULL",
            "text_path": "",
        }
    ]
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    records = build_site.build_site(manifest_path, tmp_path / "out", "Test Site")

    assert len(records) == 1
    document_page = (tmp_path / "out" / "docs" / "C12345678.html").read_text(encoding="utf-8")
    assert "Extracted text is not available yet" in document_page
