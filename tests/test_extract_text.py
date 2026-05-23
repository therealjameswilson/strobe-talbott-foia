from pathlib import Path

from scripts import extract_text


def test_target_paths_use_document_id() -> None:
    assert extract_text.target_pdf_path(Path("/tmp/pdfs"), "C00000001") == Path("/tmp/pdfs/C00000001.pdf")
    assert extract_text.target_text_path(Path("/tmp/text"), "C00000001") == Path("/tmp/text/C00000001.txt")


def test_repo_relative_prefers_repo_relative_path() -> None:
    text_path = extract_text.PROJECT_ROOT / "data" / "text" / "C00000001.txt"
    assert extract_text.repo_relative(text_path) == "data/text/C00000001.txt"
