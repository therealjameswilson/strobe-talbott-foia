from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_site import load_manifest


def extract_text_from_pdf(pdf_source: str) -> str:
    """
    Placeholder for future PDF text extraction.

    A real implementation may use:
    - pypdf for machine-readable PDFs
    - pdfplumber for layout-aware extraction
    - OCR for scanned documents when text is unavailable
    """
    raise NotImplementedError(f"Text extraction is not implemented for {pdf_source}.")


def build_sample_text(record_id: str, title: str) -> str:
    return (
        "Sample placeholder extraction output for development only.\n\n"
        f"Document {record_id} uses synthetic text because the PDF extraction pipeline "
        f"for '{title}' has not been connected yet."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Placeholder PDF text extraction script.")
    parser.add_argument("--manifest", type=Path, required=True, help="Path to a JSON manifest file.")
    parser.add_argument("--out", type=Path, required=True, help="Directory for extracted text files.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of records to process.")
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Write placeholder text files instead of attempting PDF extraction.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_manifest(args.manifest.resolve())[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)

    for record in records:
        output_path = args.out / f"{record.id}.txt"
        if args.sample:
            output_path.write_text(build_sample_text(record.id, record.title), encoding="utf-8")
            continue

        # The MVP intentionally avoids downloading or processing the full corpus by default.
        # When the real extractor is added, it should work from a curated local PDF cache
        # or a narrowly limited fetch routine rather than attempting the entire corpus.
        print(f"Skipping {record.id}; real PDF extraction is not implemented yet.")

    print(f"Prepared text outputs in {args.out}.")


if __name__ == "__main__":
    main()
