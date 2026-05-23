from __future__ import annotations

import argparse
import html
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "sample_manifest.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "site"
DEFAULT_SITE_TITLE = "Strobe Talbott FOIA Case F-2017-13804"
DEFAULT_PDF_CACHE_DIR = PROJECT_ROOT / "data" / "pdfs"
EXPECTED_CASE_NUMBER = "F-2017-13804"
STATIC_ASSETS_DIR = PROJECT_ROOT / "site" / "assets"


@dataclass
class DocumentRecord:
    id: str
    case_number: str
    title: str
    date: str
    source_pdf_url: str
    release_status: str
    text_path: str
    posted_date: str = ""
    document_type: str = ""
    from_field: str = ""
    to_field: str = ""
    collection: str = ""
    raw_release_status: str = ""
    harvested_at: str = ""
    pdf_path: str = ""
    pdf_sha256: str = ""
    pdf_bytes: int | None = None
    pdf_downloaded_at: str = ""
    pdf_content_type: str = ""
    pdf_status: str = ""
    page_count: int | None = None
    text_char_count: int | None = None
    text_extraction_status: str = ""
    text_extracted_at: str = ""
    ocr_status: str = ""


def normalize_document_id(raw_id: str) -> str:
    cleaned = "".join(character for character in raw_id.upper().strip() if character.isalnum())
    if not cleaned:
        raise ValueError("Document id cannot be empty.")
    return cleaned


def string_field(item: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def int_field(item: dict[str, object], key: str) -> int | None:
    value = item.get(key)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_manifest(manifest_path: Path) -> list[DocumentRecord]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Manifest must contain a top-level JSON list.")

    records: list[DocumentRecord] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Manifest record {index} is not a JSON object.")

        doc_id = normalize_document_id(str(item.get("id", "")))
        source_pdf_url = str(item.get("source_pdf_url", "")).strip()
        if not source_pdf_url:
            raise ValueError(f"Manifest record {doc_id} is missing source_pdf_url.")

        records.append(
            DocumentRecord(
                id=doc_id,
                case_number=str(item.get("case_number", "")).strip() or "Unknown case",
                title=str(item.get("title", "")).strip() or "Untitled record",
                date=str(item.get("date", "")).strip() or "Unknown date",
                source_pdf_url=source_pdf_url,
                release_status=str(item.get("release_status", "")).strip() or "Unknown status",
                text_path=str(item.get("text_path", "")).strip(),
                posted_date=string_field(item, "posted_date"),
                document_type=string_field(item, "document_type"),
                from_field=string_field(item, "from_field", "from"),
                to_field=string_field(item, "to_field", "to"),
                collection=string_field(item, "collection"),
                raw_release_status=string_field(item, "raw_release_status", "release_status_raw"),
                harvested_at=string_field(item, "harvested_at"),
                pdf_path=string_field(item, "pdf_path"),
                pdf_sha256=string_field(item, "pdf_sha256"),
                pdf_bytes=int_field(item, "pdf_bytes"),
                pdf_downloaded_at=string_field(item, "pdf_downloaded_at"),
                pdf_content_type=string_field(item, "pdf_content_type"),
                pdf_status=string_field(item, "pdf_status"),
                page_count=int_field(item, "page_count"),
                text_char_count=int_field(item, "text_char_count"),
                text_extraction_status=string_field(item, "text_extraction_status"),
                text_extracted_at=string_field(item, "text_extracted_at"),
                ocr_status=string_field(item, "ocr_status"),
            )
        )

    return records


def resolve_text_path(text_path: str, manifest_path: Path) -> Path | None:
    if not text_path.strip():
        return None

    candidate_paths = [Path(text_path)]
    if not Path(text_path).is_absolute():
        candidate_paths.extend(
            [
                PROJECT_ROOT / text_path,
                manifest_path.parent / text_path,
                Path.cwd() / text_path,
            ]
        )

    seen: set[str] = set()
    for candidate in candidate_paths:
        candidate_key = str(candidate)
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        if candidate.exists():
            return candidate.resolve()

    return None


def validate_records(records: list[DocumentRecord], manifest_path: Path) -> None:
    errors: list[str] = []
    seen_ids: set[str] = set()

    for record in records:
        if record.id in seen_ids:
            errors.append(f"Duplicate document id {record.id}.")
        seen_ids.add(record.id)

        if not record.source_pdf_url.strip():
            errors.append(f"Record {record.id} is missing source_pdf_url.")

        if record.case_number != EXPECTED_CASE_NUMBER:
            errors.append(
                f"Record {record.id} has case number {record.case_number}; expected {EXPECTED_CASE_NUMBER}."
            )

        if record.text_path and resolve_text_path(record.text_path, manifest_path) is None:
            errors.append(f"Record {record.id} references missing text_path {record.text_path}.")

    if errors:
        formatted_errors = "\n".join(f"- {error}" for error in errors)
        raise ValueError(f"Manifest validation failed:\n{formatted_errors}")


def read_document_text(record: DocumentRecord, manifest_path: Path) -> str:
    text_file = resolve_text_path(record.text_path, manifest_path)
    if text_file is None:
        return ""
    return text_file.read_text(encoding="utf-8").strip()


def local_pdf_path(pdf_cache_dir: Path, document_id: str) -> Path:
    return pdf_cache_dir / f"{document_id}.pdf"


def discover_local_pdf_ids(records: list[DocumentRecord], pdf_cache_dir: Path) -> set[str]:
    return {
        record.id
        for record in records
        if local_pdf_path(pdf_cache_dir.resolve(), record.id).exists()
    }


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_static_assets(out_dir: Path) -> None:
    target_assets_dir = out_dir / "assets"
    if STATIC_ASSETS_DIR.resolve() == target_assets_dir.resolve():
        return
    if STATIC_ASSETS_DIR.exists():
        shutil.copytree(STATIC_ASSETS_DIR, target_assets_dir, dirs_exist_ok=True)


def write_manifest_export(
    out_dir: Path,
    records: list[DocumentRecord],
    local_pdf_ids: set[str],
    text_by_id: dict[str, str],
) -> None:
    payload = {
        "case_number": EXPECTED_CASE_NUMBER,
        "document_count": len(records),
        "record_count": len(records),
        "records": [
            {
                "id": record.id,
                "document_id": record.id,
                "case_number": record.case_number,
                "title": record.title,
                "date": record.date,
                "posted_date": record.posted_date,
                "document_type": record.document_type,
                "from_field": record.from_field,
                "to_field": record.to_field,
                "collection": record.collection,
                "source_pdf_url": record.source_pdf_url,
                "pdf_url": record.source_pdf_url,
                "release_status": record.release_status,
                "raw_release_status": record.raw_release_status,
                "text_path": record.text_path,
                "has_text": bool(text_by_id.get(record.id, "").strip()),
                "text_char_count": record.text_char_count,
                "text_extraction_status": record.text_extraction_status,
                "ocr_status": record.ocr_status,
                "page_url": f"./docs/{record.id}.html",
                "has_local_pdf": record.id in local_pdf_ids,
                "local_pdf_url": f"./pdfs/{record.id}.pdf" if record.id in local_pdf_ids else None,
                "pdf_path": record.pdf_path,
                "pdf_sha256": record.pdf_sha256,
                "pdf_bytes": record.pdf_bytes,
                "pdf_status": record.pdf_status,
                "page_count": record.page_count,
                "snippet": build_snippet(text_by_id.get(record.id, ""), limit=180),
                "description": build_snippet(text_by_id.get(record.id, ""), limit=240),
                "description_source": "extracted_text_snippet"
                if text_by_id.get(record.id, "").strip()
                else "",
            }
            for record in records
        ],
    }
    search_dir = out_dir / "assets" / "search"
    write_text(search_dir / "manifest.json", json.dumps(payload, indent=2))
    write_text(search_dir / "doc_pages.json", json.dumps(sorted(record.id for record in records), indent=2))


def build_snippet(text: str, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1].rstrip()}…"


def build_citation(record: DocumentRecord) -> str:
    return (
        "U.S. Department of State FOIA Library, "
        f"Case {record.case_number}, "
        f"Doc. {record.id}, "
        f"{record.date}, "
        f"{record.title}, "
        f"{record.source_pdf_url}"
    )


def format_document_text(text: str) -> str:
    if not text.strip():
        return (
            '<p class="empty-state">No extracted text is available for this record yet. '
            "The page is still searchable by document metadata and source URL.</p>"
        )

    paragraphs = [segment.strip() for segment in text.split("\n\n") if segment.strip()]
    return "\n".join(
        f"<p>{html.escape(paragraph).replace(chr(10), '<br>')}</p>" for paragraph in paragraphs
    )


def relative_asset(root_prefix: str, relative_path: str) -> str:
    return f"{root_prefix}/{relative_path}"


def nav_link(label: str, href: str, is_current: bool) -> str:
    current_attr = ' aria-current="page"' if is_current else ""
    return f'<a href="{html.escape(href)}"{current_attr}>{html.escape(label)}</a>'


def count_records_with_text(text_by_id: dict[str, str]) -> int:
    return sum(1 for value in text_by_id.values() if value.strip())


def is_sample_collection(records: list[DocumentRecord]) -> bool:
    if not records:
        return False
    return all("foia.state.gov/example/" in record.source_pdf_url for record in records)


def render_layout(
    *,
    page_title: str,
    site_title: str,
    root_prefix: str,
    body_class: str,
    body: str,
    page_description: str,
    current_page: str,
    script_paths: list[str] | None = None,
) -> str:
    stylesheet = relative_asset(root_prefix, "assets/css/style.css")
    home_url = relative_asset(root_prefix, "index.html")
    search_url = relative_asset(root_prefix, "search.html")
    semantic_url = relative_asset(root_prefix, "semantic.html")
    script_tags = ""
    for script_path in script_paths or []:
        script_tags += f'\n    <script src="{html.escape(script_path)}" defer></script>'

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(page_title)}</title>
    <meta name="description" content="{html.escape(page_description)}">
    <link rel="stylesheet" href="{html.escape(stylesheet)}">
  </head>
  <body class="{html.escape(body_class)}">
    <header class="masthead">
      <div class="layout">
        <p class="eyebrow">Strobe Talbott FOIA Research Desk</p>
        <div class="masthead-row">
          <div class="title-lockup">
            <h1>{html.escape(site_title)}</h1>
            <p class="masthead-note">A ruby-and-gold research interface for FRUS compilers tracking case {EXPECTED_CASE_NUMBER}.</p>
          </div>
          <nav class="site-nav" aria-label="Primary">
            {nav_link("Collection", home_url, current_page == "collection")}
            {nav_link("Keyword Search", search_url, current_page == "search")}
            {nav_link("Semantic Prototype", semantic_url, current_page == "semantic")}
          </nav>
        </div>
      </div>
    </header>
    <main class="layout">
{body}
    </main>
    <footer class="site-footer">
      <div class="layout">
        <p>Raw PDFs stay out of Git and GitHub Pages. Use the source links or a local gitignored cache for document retrieval.</p>
      </div>
    </footer>{script_tags}
  </body>
</html>
"""


def render_index_page(
    records: list[DocumentRecord],
    text_by_id: dict[str, str],
    site_title: str,
    local_pdf_ids: set[str],
) -> str:
    extracted_count = count_records_with_text(text_by_id)
    full_release_count = sum(1 for record in records if record.release_status == "RELEASE IN FULL")
    part_release_count = sum(1 for record in records if record.release_status == "RELEASE IN PART")
    local_pdf_count = sum(1 for record in records if record.id in local_pdf_ids)
    sample_mode = is_sample_collection(records)
    release_options = "\n".join(
        f'              <option value="{html.escape(status, quote=True)}">{html.escape(status.title())}</option>'
        for status in sorted({record.release_status for record in records if record.release_status})
    )

    heading_label = "Sample document register" if sample_mode else "FOIA document register"
    mode_note = (
        "This build uses synthetic placeholder records for workflow testing."
        if sample_mode
        else "This build is using live harvested FOIA metadata for case-level navigation and download control."
    )
    body = f"""      <section class="card hero-card">
        <p class="eyebrow">Research Console</p>
        <h2>{heading_label} for case {EXPECTED_CASE_NUMBER}</h2>
        <p class="lede">Built for FRUS compilers and Clinton administration researchers who need a crisp metadata register, stable citations, and fast access to Strobe Talbott-related FOIA records.</p>
        <p>{html.escape(mode_note)} Metadata pages are live now; extracted full text can be layered in as PDFs are processed locally.</p>
        <div class="action-row">
          <a class="button-link" href="./search.html">Open keyword search</a>
          <a class="button-link button-link-secondary" href="./semantic.html">Open semantic prototype</a>
        </div>
      </section>
      <section class="summary-grid">
        <article class="card stat-card">
          <p class="eyebrow">Collection Size</p>
          <h2>{len(records)}</h2>
          <p class="stat-copy">documents in the current manifest</p>
        </article>
        <article class="card stat-card">
          <p class="eyebrow">Text Extraction</p>
          <h2>{extracted_count}</h2>
          <p class="stat-copy">records with extracted searchable text</p>
        </article>
        <article class="card stat-card">
          <p class="eyebrow">Release Status</p>
          <h2>{full_release_count} / {part_release_count}</h2>
          <p class="stat-copy">full / part release records</p>
        </article>
        <article class="card stat-card">
          <p class="eyebrow">Local PDF Cache</p>
          <h2>{local_pdf_count}</h2>
          <p class="stat-copy">documents with local cached PDFs ready for in-browser download</p>
        </article>
      </section>
      <section class="card">
        <div class="section-heading">
          <h2>Collection search and batch tools</h2>
          <p id="filter-summary">Showing all {len(records)} records.</p>
        </div>
        <div class="tool-grid">
          <div class="tool-pane">
            <label for="collection-filter" class="field-label">Search titles, IDs, dates, and notes</label>
            <input id="collection-filter" type="search" placeholder="Try: NATO, Moscow, 1996, C06697823">
          </div>
          <div class="tool-pane tool-pane-compact">
            <label for="release-filter" class="field-label">Release status</label>
            <select id="release-filter">
              <option value="all">All statuses</option>
{release_options}
            </select>
          </div>
        </div>
        <div class="action-row toolbar-actions">
          <button type="button" id="select-visible" class="button-link button-link-secondary">Select filtered rows</button>
          <button type="button" id="clear-selection" class="button-link button-link-secondary">Clear selection</button>
          <button type="button" id="download-selected" class="button-link">Download selected PDFs</button>
          <button type="button" id="export-selected-urls" class="button-link button-link-secondary">Export selected URLs</button>
        </div>
        <p id="selection-summary" class="status-pill">0 documents selected for batch actions.</p>
        <div class="pagination-controls" aria-label="Document table pages">
          <button type="button" id="prev-page" class="button-link button-link-secondary">Previous</button>
          <span id="page-summary" class="status-pill">Loading records...</span>
          <button type="button" id="next-page" class="button-link button-link-secondary">Next</button>
        </div>
        <p class="helper-note">Batch downloads prefer local cached PDFs when available and fall back to the original FOIA links otherwise. For a full local mirror, use <code>python3 scripts/download_pdfs.py --manifest data/manifest.json --out data/pdfs --limit 0</code>, then serve the site with <code>python3 scripts/serve_site.py</code>.</p>
      </section>
      <section class="card">
        <div class="section-heading">
          <h2>Document register</h2>
          <p>Download one PDF at a time, or filter and batch-open selected records. Local PDFs appear automatically when they have been cached on disk.</p>
        </div>
        <div class="table-wrap">
          <table class="document-table">
            <thead>
              <tr>
                <th scope="col" class="checkbox-cell">Pick</th>
                <th scope="col">Document ID</th>
                <th scope="col">Date</th>
                <th scope="col">Title</th>
                <th scope="col">Release Status</th>
                <th scope="col">PDF</th>
                <th scope="col">Page</th>
              </tr>
            </thead>
            <tbody id="document-table-body">
              <tr>
                <td colspan="7">Loading document register...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>"""

    return render_layout(
        page_title=site_title,
        site_title=site_title,
        root_prefix=".",
        body_class="page-home",
        body=body,
        page_description="Research interface for Strobe Talbott FOIA case F-2017-13804.",
        current_page="collection",
        script_paths=["./assets/js/site.js", "./assets/js/collection.js"],
    )


def render_search_page(site_title: str) -> str:
    body = """      <section class="card hero-card">
        <p class="eyebrow">Keyword Search</p>
        <h2>Pagefind search across generated Strobe pages</h2>
        <p class="lede">This search layer indexes every generated document page. It is strongest when extracted text is present, but it already covers titles, IDs, dates, release status, and source URLs across the collection.</p>
        <p id="pagefind-status" class="status-pill">Looking for Pagefind assets...</p>
      </section>
      <section class="card">
        <div id="search-interface" class="search-shell"></div>
      </section>
      <section class="card">
        <h2>Search notes</h2>
        <p>Use the collection page for fast metadata filtering and batch download selection. Use this Pagefind view when you want result cards across every generated document page.</p>
      </section>"""

    return render_layout(
        page_title=f"Keyword Search | {site_title}",
        site_title=site_title,
        root_prefix=".",
        body_class="page-search",
        body=body,
        page_description="Keyword search across generated Strobe Talbott FOIA document pages.",
        current_page="search",
        script_paths=["./assets/js/site.js", "./assets/js/search.js"],
    )


def render_semantic_page(site_title: str) -> str:
    body = """      <section class="card hero-card">
        <p class="eyebrow">AI-enhanced Prototype</p>
        <h2>Local vector ranking over extracted text chunks</h2>
        <p class="lede">This page ranks extracted text chunks with a deterministic local TF-IDF vector index. It requires no API key and can later be replaced by model embeddings.</p>
        <div class="notice">
          <strong>Compiler note.</strong> Search quality depends on the amount and quality of extracted text. OCR status is tracked separately for scanned PDFs.
        </div>
      </section>
      <section class="card">
        <form id="semantic-search-form" class="search-form">
          <label for="semantic-query">Search extracted chunk text</label>
          <div class="search-form-row">
            <input
              id="semantic-query"
              name="query"
              type="search"
              placeholder="Try: NATO enlargement, Moscow, Balkans diplomacy"
              autocomplete="off"
            >
            <button type="submit">Search</button>
          </div>
        </form>
        <p id="semantic-status" class="status-pill">Loading semantic prototype data...</p>
      </section>
      <section class="card">
        <div class="section-heading">
          <h2>Top matching chunks</h2>
          <p id="semantic-summary">Enter a query to rank the extracted chunk index.</p>
        </div>
        <div id="semantic-results" class="results-list">
          <p class="empty-state">Enter a query to search the extracted chunk index.</p>
        </div>
      </section>"""

    return render_layout(
        page_title=f"Semantic Prototype | {site_title}",
        site_title=site_title,
        root_prefix=".",
        body_class="page-semantic",
        body=body,
        page_description="AI-enhanced semantic search prototype for Strobe Talbott FOIA documents.",
        current_page="semantic",
        script_paths=["./assets/js/site.js", "./assets/js/semantic.js"],
    )


def metadata_item(label: str, value: str | int | None, *, link: str | None = None) -> str:
    if value in (None, ""):
        return ""
    escaped_value = html.escape(str(value))
    if link:
        escaped_link = html.escape(link)
        escaped_value = f'<a class="inline-link" href="{escaped_link}" target="_blank" rel="noopener">{escaped_value}</a>'
    return f"""          <div>
            <dt>{html.escape(label)}</dt>
            <dd>{escaped_value}</dd>
          </div>"""


def render_document_page(
    record: DocumentRecord,
    text: str,
    site_title: str,
    snippet: str,
    has_local_pdf: bool,
) -> str:
    citation = build_citation(record)
    extraction_note = (
        "Extracted text is available for this record."
        if text.strip()
        else "Extracted text is not available yet. Metadata and PDF access are still live."
    )
    local_pdf_url = f"../pdfs/{record.id}.pdf" if has_local_pdf else ""
    download_actions = [
        (
            f'<a class="button-link" href="{html.escape(local_pdf_url)}" target="_blank" rel="noopener">Download local PDF</a>'
            if has_local_pdf
            else f'<a class="button-link" href="{html.escape(record.source_pdf_url)}" target="_blank" rel="noopener">Download original PDF</a>'
        )
    ]
    if has_local_pdf:
        download_actions.append(
            f'<a class="button-link button-link-secondary" href="{html.escape(record.source_pdf_url)}" target="_blank" rel="noopener">Open FOIA source</a>'
        )
    metadata_rows = "\n".join(
        row
        for row in [
            metadata_item("Document title", record.title),
            metadata_item("Date", record.date or "n/a"),
            metadata_item("Posted date", record.posted_date),
            metadata_item("FOIA case number", record.case_number),
            metadata_item("Document ID", record.id),
            metadata_item("Release status", record.release_status),
            metadata_item("Raw release code", record.raw_release_status),
            metadata_item("Document type", record.document_type),
            metadata_item("From", record.from_field),
            metadata_item("To", record.to_field),
            metadata_item("Collection", record.collection),
            metadata_item("Source PDF", "View original FOIA source link", link=record.source_pdf_url),
            metadata_item(
                "Local PDF cache",
                "Available in the local research workspace." if has_local_pdf else "Not cached locally in this build.",
            ),
            metadata_item("PDF bytes", record.pdf_bytes),
            metadata_item("PDF SHA-256", record.pdf_sha256),
            metadata_item("PDF status", record.pdf_status),
            metadata_item("Page count", record.page_count),
            metadata_item("Extraction status", record.text_extraction_status or extraction_note),
            metadata_item("Text characters", record.text_char_count),
            metadata_item("OCR status", record.ocr_status),
            metadata_item("Text path", record.text_path or "Pending extraction"),
            metadata_item("Harvested at", record.harvested_at),
            metadata_item("Text extracted at", record.text_extracted_at),
        ]
        if row
    )
    body = f"""      <article class="card document-card" data-pagefind-body>
        <p class="eyebrow">Document Record</p>
        <h2 data-pagefind-meta="title">{html.escape(record.title)}</h2>
        <p class="document-summary">{html.escape(record.date or 'n/a')} · {html.escape(record.case_number)} · Doc. {html.escape(record.id)} · {html.escape(record.release_status)}</p>
        <p class="lede">{html.escape(snippet or extraction_note)}</p>
        <div class="action-row">
          {' '.join(download_actions)}
          <button
            type="button"
            class="button-link button-link-secondary copy-button"
            data-copy-text="{html.escape(citation, quote=True)}"
            data-default-label="Copy citation"
            data-copied-label="Citation copied"
          >
            Copy citation
          </button>
        </div>
        <dl class="metadata-list">
{metadata_rows}
        </dl>
      </article>
      <section class="card">
        <h2>Suggested citation</h2>
        <p class="citation-text">{html.escape(citation)}</p>
      </section>
      <section class="card">
        <h2>Extracted text</h2>
        <div class="document-text">
{format_document_text(text)}
        </div>
      </section>"""

    return render_layout(
        page_title=f"{record.id} | {record.title}",
        site_title=site_title,
        root_prefix="..",
        body_class="page-document",
        body=body,
        page_description=f"Document page for {record.id} in FOIA case {record.case_number}.",
        current_page="collection",
        script_paths=["../assets/js/site.js"],
    )


def build_site(
    manifest_path: Path,
    out_dir: Path,
    site_title: str,
    pdf_cache_dir: Path = DEFAULT_PDF_CACHE_DIR,
) -> list[DocumentRecord]:
    manifest_path = manifest_path.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    records = load_manifest(manifest_path)
    validate_records(records, manifest_path)
    text_by_id = {record.id: read_document_text(record, manifest_path) for record in records}
    local_pdf_ids = discover_local_pdf_ids(records, pdf_cache_dir.resolve())

    copy_static_assets(out_dir)
    write_manifest_export(out_dir, records, local_pdf_ids, text_by_id)

    docs_dir = out_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for existing_page in docs_dir.glob("*.html"):
        existing_page.unlink()

    write_text(out_dir / "index.html", render_index_page(records, text_by_id, site_title, local_pdf_ids))
    write_text(out_dir / "search.html", render_search_page(site_title))
    write_text(out_dir / "semantic.html", render_semantic_page(site_title))

    for record in records:
        text = text_by_id.get(record.id, "")
        snippet = build_snippet(text) if text else ""
        write_text(
            docs_dir / f"{record.id}.html",
            render_document_page(record, text, site_title, snippet, record.id in local_pdf_ids),
        )

    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the static FOIA research site.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to the JSON manifest file.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Output directory for generated HTML.",
    )
    parser.add_argument(
        "--site-title",
        default=DEFAULT_SITE_TITLE,
        help="Title shown in generated pages.",
    )
    parser.add_argument(
        "--pdf-cache-dir",
        type=Path,
        default=DEFAULT_PDF_CACHE_DIR,
        help="Directory holding locally cached PDFs for optional local download links.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = build_site(args.manifest, args.out, args.site_title, args.pdf_cache_dir)
    print(f"Built {len(records)} document pages plus collection and search assets in {args.out}.")


if __name__ == "__main__":
    main()
