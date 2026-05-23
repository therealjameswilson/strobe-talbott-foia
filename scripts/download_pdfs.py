from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_site import load_manifest
from scripts.harvest_foia import DebugRecorder, HarvestClient, create_session

DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "manifest.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "pdfs"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "reports" / "download_pdfs.json"
DEFAULT_LIMIT = 25


@dataclass
class DownloadResult:
    document_id: str
    source_pdf_url: str
    target_path: str
    status: str
    bytes: int = 0
    sha256: str = ""
    content_type: str = ""
    downloaded_at: str = ""
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download FOIA PDFs into a local gitignored cache without committing them to the repository."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to the JSON manifest file.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR, help="Directory for cached PDF files.")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Maximum number of PDFs to download. Use 0 to process the entire manifest.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would be downloaded without writing files.")
    parser.add_argument("--force", action="store_true", help="Re-download files even when they already exist locally.")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore any existing .part file and restart incomplete downloads from byte 0.",
    )
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="Write PDF cache metadata such as checksum and byte count back into the manifest.",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Path to a JSON download report.")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def target_pdf_path(out_dir: Path, document_id: str) -> Path:
    return out_dir / f"{document_id}.pdf"


def manifest_path_for_pdf(pdf_path: Path) -> str:
    resolved = pdf_path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def iter_records(manifest_path: Path, limit: int) -> list[tuple[str, str]]:
    records = load_manifest(manifest_path.resolve())
    if limit > 0:
        records = records[:limit]
    return [(record.id, record.source_pdf_url) for record in records]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_pdf(path: Path) -> None:
    with path.open("rb") as handle:
        header = handle.read(5)
    if header != b"%PDF-":
        raise ValueError(f"{path.name} does not look like a PDF.")


def write_report(report_path: Path, results: list[DownloadResult]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": utc_now(),
        "result_count": len(results),
        "results": [asdict(result) for result in results],
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def download_pdf(
    client: HarvestClient,
    document_id: str,
    source_url: str,
    target_path: Path,
    *,
    resume: bool,
) -> DownloadResult:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(".pdf.part")
    headers: dict[str, str] = {}
    mode = "wb"

    if resume and temp_path.exists() and temp_path.stat().st_size > 0:
        headers["Range"] = f"bytes={temp_path.stat().st_size}-"

    response = client.get(source_url, headers=headers or None, stream=True)
    content_type = response.headers.get("Content-Type", "")
    try:
        if headers.get("Range") and response.status_code == 206:
            mode = "ab"
        elif mode == "wb" and temp_path.exists():
            temp_path.unlink()

        with temp_path.open(mode) as handle:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    handle.write(chunk)
    finally:
        response.close()

    validate_pdf(temp_path)
    temp_path.replace(target_path)

    return DownloadResult(
        document_id=document_id,
        source_pdf_url=source_url,
        target_path=manifest_path_for_pdf(target_path),
        status="downloaded",
        bytes=target_path.stat().st_size,
        sha256=sha256_file(target_path),
        content_type=content_type,
        downloaded_at=utc_now(),
    )


def cached_result(document_id: str, source_url: str, target_path: Path) -> DownloadResult:
    validate_pdf(target_path)
    return DownloadResult(
        document_id=document_id,
        source_pdf_url=source_url,
        target_path=manifest_path_for_pdf(target_path),
        status="cached",
        bytes=target_path.stat().st_size,
        sha256=sha256_file(target_path),
        downloaded_at=utc_now(),
    )


def update_manifest(manifest_path: Path, results: list[DownloadResult]) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_id = {result.document_id: result for result in results if result.status in {"cached", "downloaded"}}
    for item in payload:
        result = by_id.get(str(item.get("id", "")).strip())
        if result is None:
            continue
        item["pdf_path"] = result.target_path
        item["pdf_sha256"] = result.sha256
        item["pdf_bytes"] = result.bytes
        item["pdf_downloaded_at"] = result.downloaded_at
        item["pdf_content_type"] = result.content_type
        item["pdf_status"] = result.status

    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    out_dir = args.out.resolve()
    items = iter_records(manifest_path, args.limit)
    client = HarvestClient(
        session=create_session(),
        debug=DebugRecorder(enabled=False, base_dir=out_dir),
    )

    results: list[DownloadResult] = []
    for document_id, source_url in items:
        target_path = target_pdf_path(out_dir, document_id)
        if target_path.exists() and not args.force:
            print(f"Using cached {target_path.name}")
            try:
                result = cached_result(document_id, source_url, target_path)
            except Exception as error:
                result = DownloadResult(
                    document_id=document_id,
                    source_pdf_url=source_url,
                    target_path=manifest_path_for_pdf(target_path),
                    status="failed",
                    error=str(error),
                )
            results.append(result)
            write_report(args.report.resolve(), results)
            continue

        if args.dry_run:
            print(f"Would download {document_id} -> {target_path}")
            results.append(
                DownloadResult(
                    document_id=document_id,
                    source_pdf_url=source_url,
                    target_path=manifest_path_for_pdf(target_path),
                    status="dry_run",
                )
            )
            write_report(args.report.resolve(), results)
            continue

        print(f"Downloading {document_id} -> {target_path}")
        try:
            result = download_pdf(
                client,
                document_id,
                source_url,
                target_path,
                resume=not args.no_resume,
            )
        except Exception as error:
            result = DownloadResult(
                document_id=document_id,
                source_pdf_url=source_url,
                target_path=manifest_path_for_pdf(target_path),
                status="failed",
                error=str(error),
            )
            print(f"Failed {document_id}: {error}", file=sys.stderr)
        results.append(result)
        write_report(args.report.resolve(), results)

    if args.update_manifest:
        update_manifest(manifest_path, results)
        print(f"Updated PDF metadata in {manifest_path}")

    totals: dict[str, int] = {}
    for result in results:
        totals[result.status] = totals.get(result.status, 0) + 1
    print(f"Download summary: {totals}")
    return 0 if totals.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
