from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_site import DocumentRecord, load_manifest

DEFAULT_PDF_DIR = PROJECT_ROOT / "data" / "pdfs"
DEFAULT_TEXT_DIR = PROJECT_ROOT / "data" / "text"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "reports" / "extract_text.json"
DEFAULT_OCR_DIR = PROJECT_ROOT / "data" / "pdfs_ocr"

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - exercised only when dependency is missing.
    PdfReader = None


@dataclass
class ExtractionResult:
    document_id: str
    pdf_path: str
    text_path: str = ""
    status: str = ""
    page_count: int | None = None
    text_char_count: int = 0
    ocr_status: str = ""
    extracted_at: str = ""
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract text from locally cached FOIA PDFs without downloading the corpus."
    )
    parser.add_argument("--manifest", type=Path, required=True, help="Path to a JSON manifest file.")
    parser.add_argument("--out", type=Path, default=DEFAULT_TEXT_DIR, help="Directory for extracted text files.")
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Directory containing cached PDFs.")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of records to process. Use 0 to process the full manifest.",
    )
    parser.add_argument("--skip-existing", action="store_true", help="Leave existing text files in place.")
    parser.add_argument("--update-manifest", action="store_true", help="Write extraction metadata to the manifest.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Path to a JSON extraction report.")
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="When embedded text is empty, try `ocrmypdf` if it is installed locally.",
    )
    parser.add_argument(
        "--ocr-dir",
        type=Path,
        default=DEFAULT_OCR_DIR,
        help="Directory for OCR-processed PDFs when --ocr is used.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def target_pdf_path(pdf_dir: Path, document_id: str) -> Path:
    return pdf_dir / f"{document_id}.pdf"


def target_text_path(out_dir: Path, document_id: str) -> Path:
    return out_dir / f"{document_id}.txt"


def repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def extract_text_from_pdf(pdf_source: Path) -> tuple[str, int]:
    """
    Extract machine-readable text from a local PDF.

    OCR is intentionally optional because it requires external system tools and
    can be slow across a multi-thousand-document corpus.
    """
    if PdfReader is None:
        raise RuntimeError(
            "pypdf is not installed. Run `pip install -r requirements.txt` before extracting text."
        )

    reader = PdfReader(str(pdf_source))
    extracted_pages: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            continue
        extracted_pages.append(f"[Page {page_number}]\n{page_text}")

    return "\n\n".join(extracted_pages).strip(), len(reader.pages)


def run_ocr(input_pdf: Path, output_pdf: Path) -> tuple[bool, str]:
    ocrmypdf = shutil.which("ocrmypdf")
    if not ocrmypdf:
        return False, "ocr_tool_missing"

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ocrmypdf,
        "--skip-text",
        "--quiet",
        str(input_pdf),
        str(output_pdf),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit_{completed.returncode}"
        return False, f"ocr_failed: {detail}"
    return True, "ocr_applied"


def iter_records(records: list[DocumentRecord], limit: int) -> list[DocumentRecord]:
    if limit > 0:
        return records[:limit]
    return records


def write_report(report_path: Path, results: list[ExtractionResult]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": utc_now(),
        "result_count": len(results),
        "results": [asdict(result) for result in results],
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def update_manifest(manifest_path: Path, results: list[ExtractionResult]) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_id = {result.document_id: result for result in results}
    for item in payload:
        result = by_id.get(str(item.get("id", "")).strip())
        if result is None:
            continue
        if result.text_path:
            item["text_path"] = result.text_path
        item["text_extraction_status"] = result.status
        item["text_char_count"] = result.text_char_count
        item["text_extracted_at"] = result.extracted_at
        item["ocr_status"] = result.ocr_status
        if result.page_count is not None:
            item["page_count"] = result.page_count

    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def extract_record(
    record: DocumentRecord,
    *,
    out_dir: Path,
    pdf_dir: Path,
    ocr: bool,
    ocr_dir: Path,
    skip_existing: bool,
) -> ExtractionResult:
    pdf_path = target_pdf_path(pdf_dir, record.id)
    output_path = target_text_path(out_dir, record.id)

    if skip_existing and output_path.exists():
        return ExtractionResult(
            document_id=record.id,
            pdf_path=repo_relative(pdf_path),
            text_path=repo_relative(output_path),
            status="cached_text",
            text_char_count=len(output_path.read_text(encoding="utf-8")),
            extracted_at=utc_now(),
        )

    if not pdf_path.exists():
        return ExtractionResult(
            document_id=record.id,
            pdf_path=repo_relative(pdf_path),
            status="missing_pdf",
            ocr_status="not_attempted",
            extracted_at=utc_now(),
        )

    text, page_count = extract_text_from_pdf(pdf_path)
    ocr_status = "not_needed" if text.strip() else "needed"

    if not text.strip() and ocr:
        ocr_pdf = ocr_dir / f"{record.id}.pdf"
        ok, ocr_status = run_ocr(pdf_path, ocr_pdf)
        if ok:
            text, page_count = extract_text_from_pdf(ocr_pdf)
            if text.strip():
                pdf_path = ocr_pdf

    if not text.strip():
        return ExtractionResult(
            document_id=record.id,
            pdf_path=repo_relative(pdf_path),
            status="needs_ocr",
            page_count=page_count,
            ocr_status=ocr_status,
            extracted_at=utc_now(),
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return ExtractionResult(
        document_id=record.id,
        pdf_path=repo_relative(pdf_path),
        text_path=repo_relative(output_path),
        status="extracted",
        page_count=page_count,
        text_char_count=len(text),
        ocr_status=ocr_status,
        extracted_at=utc_now(),
    )


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    out_dir = args.out.resolve()
    pdf_dir = args.pdf_dir.resolve()
    ocr_dir = args.ocr_dir.resolve()

    records = iter_records(load_manifest(manifest_path), args.limit)
    results: list[ExtractionResult] = []

    for record in records:
        try:
            result = extract_record(
                record,
                out_dir=out_dir,
                pdf_dir=pdf_dir,
                ocr=args.ocr,
                ocr_dir=ocr_dir,
                skip_existing=args.skip_existing,
            )
        except Exception as error:
            result = ExtractionResult(
                document_id=record.id,
                pdf_path=repo_relative(target_pdf_path(pdf_dir, record.id)),
                status="failed",
                error=str(error),
                extracted_at=utc_now(),
            )
        results.append(result)
        print(f"{result.document_id}: {result.status}")
        write_report(args.report.resolve(), results)

    if args.update_manifest:
        update_manifest(manifest_path, results)
        print(f"Updated extraction metadata in {manifest_path}")

    totals: dict[str, int] = {}
    for result in results:
        totals[result.status] = totals.get(result.status, 0) + 1
    print(f"Extraction summary: {totals}")
    return 0 if totals.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
