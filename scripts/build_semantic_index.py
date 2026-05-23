from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_chunks import DEFAULT_OUT_PATH as DEFAULT_CHUNKS_PATH
from scripts.build_site import PROJECT_ROOT

DEFAULT_INDEX_PATH = PROJECT_ROOT / "site" / "assets" / "search" / "semantic_index.json"
DEFAULT_DIMENSIONS = 192


def stable_hash(token: str) -> int:
    value = 0
    for character in token:
        value = ((value << 5) - value + ord(character)) & 0xFFFFFFFF
    return value


def vectorize_tokens(
    tokens: list[str],
    *,
    token_idf: dict[str, float],
    dimensions: int,
    max_vector_terms: int,
) -> list[list[float]]:
    if not tokens:
        return []

    counts = Counter(tokens)
    weights: dict[int, float] = {}
    for token, count in counts.items():
        index = stable_hash(token) % dimensions
        weights[index] = weights.get(index, 0.0) + (1.0 + math.log(count)) * token_idf.get(token, 1.0)

    if len(weights) > max_vector_terms:
        weights = dict(
            sorted(weights.items(), key=lambda item: item[1], reverse=True)[:max_vector_terms]
        )

    norm = math.sqrt(sum(value * value for value in weights.values()))
    if not norm:
        return []
    return [[index, round(value / norm, 6)] for index, value in sorted(weights.items())]


def build_semantic_index(
    chunks_path: Path,
    out_path: Path,
    *,
    dimensions: int,
    max_vector_terms: int,
) -> dict[str, object]:
    chunks_data = json.loads(chunks_path.read_text(encoding="utf-8"))
    chunk_rows = chunks_data.get("chunks", [])
    if not isinstance(chunk_rows, list):
        raise ValueError("Chunk file is missing a chunks list.")

    document_frequency: Counter[str] = Counter()
    token_rows: list[list[str]] = []
    for row in chunk_rows:
        tokens = list(dict.fromkeys(row.get("keywords", [])))
        token_rows.append(tokens)
        document_frequency.update(tokens)

    chunk_count = max(1, len(chunk_rows))
    token_idf = {
        token: round(math.log((1 + chunk_count) / (1 + frequency)) + 1.0, 6)
        for token, frequency in sorted(document_frequency.items())
    }

    payload = {
        "version": "local-hashed-tfidf-v1",
        "embedding_model": "local-hashed-tfidf",
        "dimensions": dimensions,
        "note": "Local deterministic lexical vectors. Replace with model embeddings when an embedding provider is configured.",
        "token_idf": token_idf,
        "chunks": [
            {
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "vector": vectorize_tokens(
                    token_rows[index],
                    token_idf=token_idf,
                    dimensions=dimensions,
                    max_vector_terms=max_vector_terms,
                ),
            }
            for index, row in enumerate(chunk_rows)
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local semantic-style vector index file.")
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_PATH, help="Path to chunks JSON.")
    parser.add_argument("--out", type=Path, default=DEFAULT_INDEX_PATH, help="Path to semantic index JSON.")
    parser.add_argument("--dimensions", type=int, default=DEFAULT_DIMENSIONS, help="Hashed vector dimensions.")
    parser.add_argument("--max-vector-terms", type=int, default=24, help="Maximum sparse vector weights per chunk.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_semantic_index(
        args.chunks.resolve(),
        args.out.resolve(),
        dimensions=args.dimensions,
        max_vector_terms=args.max_vector_terms,
    )
    print(f"Wrote local semantic index for {len(payload['chunks'])} chunks to {args.out}.")


if __name__ == "__main__":
    main()
