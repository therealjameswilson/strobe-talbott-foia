from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_chunks import DEFAULT_OUT_PATH as DEFAULT_CHUNKS_PATH
from scripts.build_site import PROJECT_ROOT
DEFAULT_INDEX_PATH = PROJECT_ROOT / "site" / "assets" / "search" / "semantic_index.json"


def build_placeholder_semantic_index(chunks_path: Path, out_path: Path) -> dict[str, object]:
    chunks_data = json.loads(chunks_path.read_text(encoding="utf-8"))
    chunk_rows = chunks_data.get("chunks", [])
    if not isinstance(chunk_rows, list):
        raise ValueError("Chunk file is missing a chunks list.")

    payload = {
        "version": "placeholder-semantic-index-v1",
        "embedding_model": None,
        "note": "Replace empty vectors with real embeddings in a future build step.",
        "chunks": [
            {
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "keyword_signature": row.get("keywords", [])[:20],
                "vector": [],
            }
            for row in chunk_rows
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a placeholder semantic index file.")
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_PATH, help="Path to chunks JSON.")
    parser.add_argument("--out", type=Path, default=DEFAULT_INDEX_PATH, help="Path to semantic index JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_placeholder_semantic_index(args.chunks.resolve(), args.out.resolve())
    print(f"Wrote placeholder semantic index for {len(payload['chunks'])} chunks to {args.out}.")


if __name__ == "__main__":
    main()
