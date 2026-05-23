from pathlib import Path

from scripts import download_pdfs

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MANIFEST = PROJECT_ROOT / "data" / "sample_manifest.json"


def test_target_pdf_path_uses_document_id() -> None:
    target = download_pdfs.target_pdf_path(Path("/tmp/pdfs"), "C00000001")
    assert str(target) == "/tmp/pdfs/C00000001.pdf"


def test_iter_records_reads_manifest_limit() -> None:
    rows = download_pdfs.iter_records(SAMPLE_MANIFEST, 2)
    assert len(rows) == 2
    assert rows[0][0] == "C00000001"
    assert rows[0][1].startswith("https://foia.state.gov/example/")
