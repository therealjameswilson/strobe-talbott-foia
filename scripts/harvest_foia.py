from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://foia.state.gov"
SEARCH_PAGE_URL = f"{BASE_URL}/FOIALIBRARY/SearchResults.aspx"
SEARCH_API_URL = f"{BASE_URL}/api/Search2/SubmitSimpleQuery"
DEFAULT_OUT_PATH = PROJECT_ROOT / "data" / "manifest.json"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
USER_AGENT = (
    "strobe-talbott-foia-research/0.1 "
    "(+https://github.com/therealjameswilson/strobe-talbott-foia)"
)
REQUEST_TIMEOUT_SECONDS = 30
RATE_LIMIT_SECONDS = 1.0
API_PAGE_SIZE = 20


@dataclass
class HarvestRecord:
    id: str
    case_number: str
    title: str
    date: str
    source_pdf_url: str
    release_status: str
    text_path: str


class HarvestError(RuntimeError):
    pass


@dataclass
class DebugRecorder:
    enabled: bool
    base_dir: Path

    def write_text(self, filename: str, content: str) -> None:
        if not self.enabled:
            return
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / filename).write_text(content, encoding="utf-8")

    def write_json(self, filename: str, payload: Any) -> None:
        if not self.enabled:
            return
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataclass
class HarvestClient:
    session: Session
    debug: DebugRecorder
    last_request_started_at: float | None = None

    def get(self, url: str, *, params: dict[str, Any] | None = None) -> Response:
        if self.last_request_started_at is not None:
            elapsed = time.monotonic() - self.last_request_started_at
            if elapsed < RATE_LIMIT_SECONDS:
                time.sleep(RATE_LIMIT_SECONDS - elapsed)

        self.last_request_started_at = time.monotonic()
        response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response


def normalize_document_id(raw_id: str) -> str:
    cleaned = "".join(character for character in raw_id.upper().strip() if character.isalnum())
    if not cleaned:
        raise ValueError("Document id cannot be empty.")
    return cleaned


def build_placeholder_records(case_number: str, limit: int) -> list[HarvestRecord]:
    records: list[HarvestRecord] = []
    for index in range(1, limit + 1):
        record_id = f"C{index:08d}"
        records.append(
            HarvestRecord(
                id=record_id,
                case_number=case_number,
                title=f"Placeholder harvested record {index} for case {case_number}",
                date="1996-01-01",
                source_pdf_url=f"https://foia.state.gov/example/{record_id}.pdf",
                release_status="PLACEHOLDER SAMPLE",
                text_path=f"data/text/{record_id}.txt",
            )
        )
    return records


def create_session() -> Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        }
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def build_search_params(case_number: str, page_number: int, start: int, limit: int) -> dict[str, Any]:
    return {
        "searchText": "*",
        "collectionMatch": "false",
        "page": page_number,
        "start": start,
        "limit": limit,
        "beginDate": "false",
        "endDate": "false",
        "postedBeginDate": "false",
        "postedEndDate": "false",
        "caseNumber": case_number,
        "docFrom": "false",
        "docTo": "false",
        "email": "false",
        "telegram": "false",
        "misc": "false",
        "me": "false",
        "gc": "false",
        "cc": "false",
        "md": "false",
        "pr": "false",
        "sc": "false",
        "rp": "false",
        "tn": "false",
        "dd": "false",
        "cd": "false",
        "mf": "false",
        "exclude": "false",
        "sort": "",
    }


def normalize_date(raw_value: Any) -> str:
    if not raw_value:
        return ""
    text = str(raw_value).strip()
    if not text:
        return ""
    normalized = text.split("T", 1)[0]
    if normalized == "0001-01-01":
        return ""
    return normalized


def map_release_status(raw_code: Any) -> str:
    code = str(raw_code or "").strip().upper()
    exact_map = {
        "RIFPUB": "RELEASE IN FULL",
        "RIPPUB": "RELEASE IN PART",
    }
    if code in exact_map:
        return exact_map[code]
    if code.startswith("RIF"):
        return "RELEASE IN FULL"
    if code.startswith("RIP"):
        return "RELEASE IN PART"
    if not code:
        return "UNKNOWN"
    return code


def normalize_pdf_url(pdf_link: Any) -> str:
    pdf_path = str(pdf_link or "").strip()
    if not pdf_path:
        raise ValueError("Search result is missing pdfLink.")
    return urljoin(f"{BASE_URL}/", pdf_path.lstrip("/"))


def normalize_record(api_record: dict[str, Any], case_number: str) -> HarvestRecord:
    source_pdf_url = normalize_pdf_url(api_record.get("pdfLink"))
    record_id = normalize_document_id(Path(source_pdf_url).stem)
    title = str(api_record.get("subject") or api_record.get("casesubject") or record_id).strip()
    date = normalize_date(api_record.get("docdate")) or normalize_date(api_record.get("posteddate"))

    return HarvestRecord(
        id=record_id,
        case_number=str(api_record.get("casenumber") or case_number).strip() or case_number,
        title=title or record_id,
        date=date,
        source_pdf_url=source_pdf_url,
        release_status=map_release_status(api_record.get("releasedecision")),
        text_path=f"data/text/{record_id}.txt",
    )


def probe_search_page(client: HarvestClient, case_number: str) -> None:
    response = client.get(SEARCH_PAGE_URL, params={"caseNumber": case_number})
    client.debug.write_text("search_results_page.html", response.text)

    if "Results5.js" not in response.text or "Search Results" not in response.text:
        raise HarvestError(
            "The FOIA search page loaded, but the expected search UI markers were missing.\n"
            f"Checked URL: {SEARCH_PAGE_URL}?caseNumber={case_number}\n"
            "Run again with --debug to save the raw HTML for inspection."
        )


def fetch_search_page(
    client: HarvestClient,
    case_number: str,
    page_number: int,
    start: int,
    page_size: int,
) -> dict[str, Any]:
    params = build_search_params(case_number, page_number, start, page_size)
    try:
        response = client.get(SEARCH_API_URL, params=params)
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else "unknown"
        body = error.response.text if error.response is not None else ""
        if error.response is not None:
            client.debug.write_text(f"submit_simple_query_page_{page_number}.txt", body)
        raise HarvestError(
            "The FOIA metadata endpoint did not return a usable response.\n"
            f"Endpoint: {SEARCH_API_URL}\n"
            f"Status: {status}\n"
            "The live FOIA search backend may have changed. Run with --debug to save the raw response,\n"
            "then compare the current SearchResults page and Results5.js request pattern."
        ) from error

    try:
        payload = response.json()
    except json.JSONDecodeError as error:
        client.debug.write_text(f"submit_simple_query_page_{page_number}.txt", response.text)
        raise HarvestError(
            "The FOIA metadata endpoint responded, but not with valid JSON.\n"
            f"Endpoint: {SEARCH_API_URL}\n"
            "Run with --debug to save the raw response for inspection."
        ) from error

    client.debug.write_json(f"submit_simple_query_page_{page_number}.json", payload)
    return payload


def extract_records_from_payload(
    payload: dict[str, Any],
    *,
    case_number: str,
    remaining: int,
    seen_ids: set[str],
) -> list[HarvestRecord]:
    raw_results = payload.get("Results", [])
    if not isinstance(raw_results, list):
        raise HarvestError("The FOIA metadata response did not include a Results list.")

    records: list[HarvestRecord] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        record = normalize_record(item, case_number)
        if record.id in seen_ids:
            continue
        seen_ids.add(record.id)
        records.append(record)
        if len(records) >= remaining:
            break
    return records


def harvest_live_manifest(
    case_number: str,
    *,
    limit: int,
    debug: bool,
) -> list[HarvestRecord]:
    session = create_session()
    client = HarvestClient(
        session=session,
        debug=DebugRecorder(enabled=debug, base_dir=RAW_DIR / case_number),
    )

    probe_search_page(client, case_number)

    collected: list[HarvestRecord] = []
    seen_ids: set[str] = set()
    page_number = 1
    start = 0
    total_hits: int | None = None

    while len(collected) < limit:
        payload = fetch_search_page(
            client,
            case_number=case_number,
            page_number=page_number,
            start=start,
            page_size=API_PAGE_SIZE,
        )

        page_total_hits = payload.get("totalHits")
        if isinstance(page_total_hits, int):
            total_hits = page_total_hits

        page_records = extract_records_from_payload(
            payload,
            case_number=case_number,
            remaining=limit - len(collected),
            seen_ids=seen_ids,
        )
        if not page_records:
            break

        collected.extend(page_records)

        returned_rows = payload.get("Results", [])
        if not isinstance(returned_rows, list):
            break
        if len(returned_rows) < API_PAGE_SIZE:
            break
        if total_hits is not None and start + len(returned_rows) >= total_hits:
            break

        start += len(returned_rows)
        page_number += 1

    if not collected and total_hits not in (0, None):
        raise HarvestError(
            "The FOIA metadata endpoint reported hits, but no records could be normalized.\n"
            "Run with --debug and inspect the saved JSON under data/raw/."
        )

    return collected[:limit]


def harvest_manifest(case_number: str, *, limit: int, sample: bool, debug: bool) -> list[HarvestRecord]:
    if sample:
        return build_placeholder_records(case_number, limit)
    return harvest_live_manifest(case_number, limit=limit, debug=debug)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest FOIA Library metadata into the local manifest schema.")
    parser.add_argument("--case-number", required=True, help="FOIA case number to harvest.")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_PATH,
        help="Output JSON manifest path.",
    )
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of records to include.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover records and print a summary without writing the manifest file.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save raw HTML and JSON responses under data/raw/ for troubleshooting.",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Write synthetic placeholder records instead of querying the live FOIA site.",
    )
    return parser.parse_args()


def print_summary(records: list[HarvestRecord], case_number: str, *, dry_run: bool) -> None:
    mode_label = "Dry run discovered" if dry_run else "Discovered"
    print(f"{mode_label} {len(records)} records for case {case_number}.")
    for record in records[:5]:
        print(f"- {record.id} | {record.date or 'n/a'} | {record.title}")


def main() -> int:
    args = parse_args()

    try:
        manifest_records = harvest_manifest(
            args.case_number,
            limit=args.limit,
            sample=args.sample,
            debug=args.debug,
        )
    except HarvestError as error:
        print(error, file=sys.stderr)
        print(
            "Diagnostic guidance:\n"
            f"- Search page: {SEARCH_PAGE_URL}?caseNumber={args.case_number}\n"
            f"- Expected metadata endpoint: {SEARCH_API_URL}\n"
            "- Re-run with --debug to save raw responses under data/raw/.\n"
            "- If the site changed, inspect the live SearchResults page and Results5.js request pattern.",
            file=sys.stderr,
        )
        return 2
    except requests.RequestException as error:
        print(
            "Network request failed while harvesting FOIA metadata.\n"
            f"{error}\n"
            "Re-run with --debug after confirming network access to foia.state.gov.",
            file=sys.stderr,
        )
        return 2

    print_summary(manifest_records, args.case_number, dry_run=args.dry_run)

    if args.dry_run:
        print(f"Skipping manifest write because --dry-run was passed. Target would have been {args.out}.")
        return 0

    manifest = [asdict(record) for record in manifest_records]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(manifest)} records to {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
