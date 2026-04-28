"""Generate neutral 2-3 sentence descriptions for each manifest record.

For every row in `data/manifest.csv` we try to download the source PDF,
extract its first few pages of text with `pdftotext`, and synthesize a
short, neutral description grounded in that text. If the PDF cannot be
retrieved or yields no usable text (scanned image, blocked, etc.), we
fall back to a metadata-only description built from title and date.

The pipeline is resumable: per-document JSON results are cached under
`data/descriptions/cache/<id>.json` and PDFs are cached under
`data/descriptions/pdfs/<id>.pdf` so reruns skip completed work.

Outputs:
  - `data/descriptions/<id>.json` per-record cache entries (source +
    description + extracted_chars).
  - `data/manifest_enriched.csv` with the original columns plus a new
    `description` column and a `description_source` column.
  - `data/manifest_descriptions.json` — `{document_id: description}`
    map consumed by the static-site build.

Usage:
  python3 scripts/enrich_manifest.py [--limit N] [--workers N]
                                     [--no-network]
                                     [--input data/manifest.csv]
                                     [--output-dir data/descriptions]

The script is intentionally conservative: descriptions never editorialize,
never imply official endorsement, and always note when text is unavailable.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "data" / "manifest.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "descriptions"
DEFAULT_ENRICHED_CSV = PROJECT_ROOT / "data" / "manifest_enriched.csv"
DEFAULT_DESCRIPTIONS_JSON = PROJECT_ROOT / "data" / "manifest_descriptions.json"

USER_AGENT = (
    "strobe-talbott-foia-research-bot/1.0 (+https://github.com/therealjameswilson/strobe-talbott-foia)"
)
REQUEST_TIMEOUT = 60
PDF_PAGES_TO_EXTRACT = 4
MIN_TEXT_LENGTH = 80
MAX_DESCRIPTION_CHARS = 600


@dataclass
class ManifestRow:
    document_id: str
    date: str
    title: str
    pdf_url: str


@dataclass
class EnrichResult:
    document_id: str
    description: str
    source: str  # "pdf" | "metadata"
    extracted_chars: int


_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def read_manifest(path: Path) -> list[ManifestRow]:
    rows: list[ManifestRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            rows.append(
                ManifestRow(
                    document_id=(raw.get("document_id") or "").strip(),
                    date=(raw.get("date") or "").strip(),
                    title=(raw.get("title") or "").strip(),
                    pdf_url=(raw.get("pdf_url") or "").strip(),
                )
            )
    return rows


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:120]


def cache_paths(output_dir: Path, document_id: str) -> tuple[Path, Path]:
    cache_dir = output_dir / "cache"
    pdf_dir = output_dir / "pdfs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    safe = safe_filename(document_id) or "doc"
    return cache_dir / f"{safe}.json", pdf_dir / f"{safe}.pdf"


def download_pdf(url: str, dest: Path, *, retries: int = 3) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf"})
            with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                tmp = dest.with_suffix(dest.suffix + ".part")
                with tmp.open("wb") as out:
                    shutil.copyfileobj(resp, out, length=64 * 1024)
                tmp.rename(dest)
            return True
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_err = exc
            time.sleep(1.0 + attempt * 1.5)
    if last_err is not None:
        log(f"  ! download failed for {url}: {last_err}")
    return False


def extract_pdf_text(pdf_path: Path) -> str:
    """Return UTF-8 text from the first few pages, or empty string."""
    try:
        completed = subprocess.run(
            [
                "pdftotext",
                "-layout",
                "-nopgbrk",
                "-enc",
                "UTF-8",
                "-l",
                str(PDF_PAGES_TO_EXTRACT),
                str(pdf_path),
                "-",
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if completed.returncode == 0:
            return completed.stdout.decode("utf-8", errors="replace")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log(f"  ! pdftotext failed on {pdf_path.name}: {exc}")
    return ""


def normalize_text(text: str) -> str:
    text = text.replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"\(])")
WHITESPACE_RUN_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]+")
HEADING_NOISE = re.compile(
    r"^(unclassified|secret|confidential|department of state|bureau of|memorandum"
    r"|the white house|to:|from:|subject:|date:|page \d+|case no\.?|doc no\.?|fl-?\d|c\d{6,})",
    re.IGNORECASE,
)


def split_sentences(text: str) -> list[str]:
    cleaned = WHITESPACE_RUN_RE.sub(" ", text).strip()
    if not cleaned:
        return []
    parts = SENTENCE_BOUNDARY_RE.split(cleaned)
    return [p.strip() for p in parts if p.strip()]


def looks_meaningful(sentence: str) -> bool:
    words = WORD_RE.findall(sentence)
    if len(words) < 6:
        return False
    if HEADING_NOISE.match(sentence.strip()):
        return False
    letters = sum(1 for ch in sentence if ch.isalpha())
    if letters < 0.5 * len(sentence.replace(" ", "")):
        return False
    if len(sentence) > 320:
        return False
    return True


def truncate_sentence(sentence: str, limit: int = 240) -> str:
    if len(sentence) <= limit:
        return sentence
    return sentence[: limit - 1].rstrip() + "…"


def synthesize_description_from_text(
    row: ManifestRow, raw_text: str
) -> tuple[str, int]:
    """Return (description, characters_used). Empty description if unusable."""
    text = normalize_text(raw_text)
    chars = len(text)
    if chars < MIN_TEXT_LENGTH:
        return "", chars

    sentences = split_sentences(text)
    candidates = [s for s in sentences if looks_meaningful(s)]
    chosen: list[str] = []
    for sentence in candidates:
        truncated = truncate_sentence(sentence)
        if truncated not in chosen:
            chosen.append(truncated)
        if len(chosen) >= 2:
            break

    title_clause = build_title_clause(row)
    if not chosen:
        return "", chars

    excerpt = " ".join(chosen)
    description = (
        f"{title_clause} The released text begins: \"{excerpt}\""
    )
    if len(description) > MAX_DESCRIPTION_CHARS:
        description = description[: MAX_DESCRIPTION_CHARS - 1].rstrip() + "…"
    return description, chars


def build_title_clause(row: ManifestRow) -> str:
    title = (row.title or "").strip()
    date = (row.date or "").strip()
    doc_id = (row.document_id or "").strip()
    if title and date:
        head = f"State Department FOIA record {doc_id}, dated {date}, is titled \"{title}\"."
    elif title:
        head = f"State Department FOIA record {doc_id} is titled \"{title}\"."
    elif date:
        head = f"State Department FOIA record {doc_id} is dated {date}."
    else:
        head = f"State Department FOIA record {doc_id} from case F-2017-13804."
    return head


def metadata_only_description(row: ManifestRow) -> str:
    head = build_title_clause(row)
    tail = (
        "Released under FOIA case F-2017-13804 in the Strobe Talbott collection. "
        "Searchable text was not extracted; consult the source PDF for full content."
    )
    return f"{head} {tail}"


def enrich_row(
    row: ManifestRow,
    output_dir: Path,
    *,
    use_network: bool,
) -> EnrichResult:
    cache_file, pdf_file = cache_paths(output_dir, row.document_id)
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            return EnrichResult(
                document_id=row.document_id,
                description=cached.get("description", ""),
                source=cached.get("source", "metadata"),
                extracted_chars=int(cached.get("extracted_chars", 0)),
            )
        except (json.JSONDecodeError, OSError):
            pass

    description = ""
    source = "metadata"
    extracted_chars = 0

    if use_network and row.pdf_url:
        if download_pdf(row.pdf_url, pdf_file):
            text = extract_pdf_text(pdf_file)
            description, extracted_chars = synthesize_description_from_text(row, text)
            if description:
                source = "pdf"

    if not description:
        description = metadata_only_description(row)
        source = "metadata"

    payload = {
        "document_id": row.document_id,
        "description": description,
        "source": source,
        "extracted_chars": extracted_chars,
        "title": row.title,
        "date": row.date,
        "pdf_url": row.pdf_url,
    }
    cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    return EnrichResult(
        document_id=row.document_id,
        description=description,
        source=source,
        extracted_chars=extracted_chars,
    )


def write_outputs(
    rows: list[ManifestRow],
    results: dict[str, EnrichResult],
    enriched_csv: Path,
    descriptions_json: Path,
) -> None:
    enriched_csv.parent.mkdir(parents=True, exist_ok=True)
    descriptions_json.parent.mkdir(parents=True, exist_ok=True)

    with enriched_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["document_id", "date", "title", "pdf_url", "description", "description_source"])
        for row in rows:
            r = results.get(row.document_id)
            description = r.description if r else metadata_only_description(row)
            source = r.source if r else "metadata"
            writer.writerow([row.document_id, row.date, row.title, row.pdf_url, description, source])

    payload = {
        row.document_id: {
            "description": (results[row.document_id].description if row.document_id in results else metadata_only_description(row)),
            "source": (results[row.document_id].source if row.document_id in results else "metadata"),
        }
        for row in rows
        if row.document_id
    }
    descriptions_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich manifest with PDF-grounded descriptions.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Source manifest CSV.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Where caches live.")
    parser.add_argument("--enriched-csv", type=Path, default=DEFAULT_ENRICHED_CSV)
    parser.add_argument("--descriptions-json", type=Path, default=DEFAULT_DESCRIPTIONS_JSON)
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N rows (0 = all).")
    parser.add_argument("--workers", type=int, default=8, help="Parallel network workers.")
    parser.add_argument("--no-network", action="store_true", help="Skip downloads; metadata-only descriptions.")
    parser.add_argument("--rebuild-outputs-only", action="store_true", help="Only rebuild CSV and JSON from cache.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_manifest(args.input)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    log(f"Loaded {len(rows)} manifest rows from {args.input}.")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, EnrichResult] = {}

    if args.rebuild_outputs_only:
        for row in rows:
            cache_file, _ = cache_paths(args.output_dir, row.document_id)
            if cache_file.exists():
                try:
                    cached = json.loads(cache_file.read_text(encoding="utf-8"))
                    results[row.document_id] = EnrichResult(
                        document_id=row.document_id,
                        description=cached.get("description", ""),
                        source=cached.get("source", "metadata"),
                        extracted_chars=int(cached.get("extracted_chars", 0)),
                    )
                except (json.JSONDecodeError, OSError):
                    pass
            if row.document_id not in results:
                results[row.document_id] = EnrichResult(
                    document_id=row.document_id,
                    description=metadata_only_description(row),
                    source="metadata",
                    extracted_chars=0,
                )
    else:
        use_network = not args.no_network
        workers = max(1, args.workers)
        t0 = time.time()

        progress = {"done": 0, "pdf": 0, "metadata": 0}
        progress_lock = threading.Lock()

        def task(row: ManifestRow) -> EnrichResult:
            return enrich_row(row, args.output_dir, use_network=use_network)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(task, row): row for row in rows if row.document_id}
            total = len(futures)
            for fut in as_completed(futures):
                row = futures[fut]
                try:
                    result = fut.result()
                except Exception as exc:  # noqa: BLE001
                    log(f"  ! row {row.document_id} failed: {exc}")
                    result = EnrichResult(
                        document_id=row.document_id,
                        description=metadata_only_description(row),
                        source="metadata",
                        extracted_chars=0,
                    )
                results[row.document_id] = result
                with progress_lock:
                    progress["done"] += 1
                    if result.source == "pdf":
                        progress["pdf"] += 1
                    else:
                        progress["metadata"] += 1
                    if progress["done"] % 25 == 0 or progress["done"] == total:
                        elapsed = time.time() - t0
                        rate = progress["done"] / elapsed if elapsed else 0
                        log(
                            f"  progress {progress['done']}/{total} "
                            f"(pdf={progress['pdf']} meta={progress['metadata']}) "
                            f"{rate:.1f}/s"
                        )

    write_outputs(rows, results, args.enriched_csv, args.descriptions_json)

    pdf_count = sum(1 for r in results.values() if r.source == "pdf")
    meta_count = sum(1 for r in results.values() if r.source == "metadata")
    log(
        f"Done. {pdf_count} PDF-grounded descriptions, {meta_count} metadata-only. "
        f"Wrote {args.enriched_csv} and {args.descriptions_json}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
