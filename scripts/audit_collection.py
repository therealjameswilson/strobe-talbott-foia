from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_site import DEFAULT_PDF_CACHE_DIR, EXPECTED_CASE_NUMBER, load_manifest, resolve_text_path

DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "manifest.json"
DEFAULT_SITE_DIR = PROJECT_ROOT / "site"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit collection readiness for compiler-facing use.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Manifest JSON path.")
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE_DIR, help="Generated site directory.")
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_CACHE_DIR, help="Local PDF cache directory.")
    parser.add_argument("--json", type=Path, default=None, help="Optional path to write audit JSON.")
    return parser.parse_args()


def build_audit(manifest_path: Path, site_dir: Path, pdf_dir: Path) -> dict[str, object]:
    records = load_manifest(manifest_path.resolve())
    ids = [record.id for record in records]
    pdf_files = list(pdf_dir.glob("*.pdf")) if pdf_dir.exists() else []
    docs_dir = site_dir / "docs"
    doc_pages = list(docs_dir.glob("*.html")) if docs_dir.exists() else []
    duplicate_generated_pages = list(docs_dir.glob("* 2.html")) if docs_dir.exists() else []
    text_paths = [record.text_path for record in records if record.text_path]
    resolved_text = [resolve_text_path(path, manifest_path) for path in text_paths]

    return {
        "case_number": EXPECTED_CASE_NUMBER,
        "manifest_records": len(records),
        "unique_ids": len(set(ids)),
        "duplicate_ids": len(ids) - len(set(ids)),
        "missing_source_pdf_url": sum(1 for record in records if not record.source_pdf_url),
        "unexpected_case_number": sum(1 for record in records if record.case_number != EXPECTED_CASE_NUMBER),
        "records_with_text_path": len(text_paths),
        "records_with_existing_text": sum(1 for path in resolved_text if path is not None),
        "records_needing_ocr": sum(1 for record in records if record.ocr_status in {"needed", "ocr_tool_missing"}),
        "records_with_page_count": sum(1 for record in records if record.page_count is not None),
        "records_with_pdf_checksum": sum(1 for record in records if record.pdf_sha256),
        "cached_pdf_files": len(pdf_files),
        "generated_document_pages": len(doc_pages),
        "duplicate_generated_pages": len(duplicate_generated_pages),
        "pagefind_present": (site_dir / "pagefind").exists(),
        "chunks_present": (site_dir / "assets" / "search" / "chunks.json").exists(),
        "semantic_index_present": (site_dir / "assets" / "search" / "semantic_index.json").exists(),
    }


def print_audit(audit: dict[str, object]) -> None:
    for key, value in audit.items():
        print(f"{key}: {value}")


def main() -> int:
    args = parse_args()
    audit = build_audit(args.manifest, args.site, args.pdf_dir)
    print_audit(audit)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    hard_failures = [
        audit["duplicate_ids"],
        audit["missing_source_pdf_url"],
        audit["unexpected_case_number"],
        audit["duplicate_generated_pages"],
    ]
    return 0 if all(value == 0 for value in hard_failures) else 1


if __name__ == "__main__":
    raise SystemExit(main())
