from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_site import DEFAULT_MANIFEST, PROJECT_ROOT, load_manifest, read_document_text
DEFAULT_OUT_PATH = PROJECT_ROOT / "site" / "assets" / "search" / "chunks.json"


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", text.lower())


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_chunks(
    manifest_path: Path,
    out_path: Path,
    *,
    chunk_size: int,
    overlap: int,
    limit: int | None = None,
) -> dict[str, object]:
    manifest_path = manifest_path.resolve()
    out_path = out_path.resolve()
    records = load_manifest(manifest_path)
    if limit is not None:
        records = records[:limit]

    payload: dict[str, object] = {
        "version": "prototype-v1",
        "search_mode": "keyword-overlap-placeholder",
        "note": "Chunks are generated from sample text for a client-side semantic search prototype.",
        "chunks": [],
    }

    chunks = payload["chunks"]
    assert isinstance(chunks, list)

    for record in records:
        text = read_document_text(record, manifest_path)
        for chunk_index, chunk in enumerate(chunk_text(text, chunk_size, overlap), start=1):
            keywords = sorted(set(tokenize(chunk)))
            chunks.append(
                {
                    "chunk_id": f"{record.id}-{chunk_index}",
                    "doc_id": record.id,
                    "case_number": record.case_number,
                    "title": record.title,
                    "date": record.date,
                    "release_status": record.release_status,
                    "source_pdf_url": record.source_pdf_url,
                    "page_url": f"./docs/{record.id}.html",
                    "chunk_index": chunk_index,
                    "text": chunk,
                    "keywords": keywords,
                }
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build chunk data for the semantic search prototype.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to the JSON manifest file.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH, help="Path to the generated chunks JSON file.")
    parser.add_argument("--chunk-size", type=int, default=90, help="Maximum words per chunk.")
    parser.add_argument("--overlap", type=int, default=18, help="Word overlap between chunks.")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit for the number of records to chunk.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_chunks(
        args.manifest,
        args.out,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        limit=args.limit,
    )
    print(f"Wrote {len(payload['chunks'])} chunks to {args.out}.")


if __name__ == "__main__":
    main()
