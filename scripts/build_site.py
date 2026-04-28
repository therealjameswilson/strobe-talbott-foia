from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "sample_manifest.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "site"
DEFAULT_SITE_TITLE = "Strobe Talbott FOIA Case F-2017-13804"
EXPECTED_CASE_NUMBER = "F-2017-13804"
STATIC_ASSETS_DIR = PROJECT_ROOT / "site" / "assets"
DEFAULT_CSV_MANIFEST = PROJECT_ROOT / "data" / "manifest.csv"
DEFAULT_DESCRIPTIONS_JSON = PROJECT_ROOT / "data" / "manifest_descriptions.json"


@dataclass
class ManifestEntry:
    document_id: str
    date: str
    title: str
    pdf_url: str
    description: str = ""
    description_source: str = ""


@dataclass
class DocumentRecord:
    id: str
    case_number: str
    title: str
    date: str
    source_pdf_url: str
    release_status: str
    text_path: str


def normalize_document_id(raw_id: str) -> str:
    cleaned = "".join(character for character in raw_id.upper().strip() if character.isalnum())
    if not cleaned:
        raise ValueError("Document id cannot be empty.")
    return cleaned


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


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_static_assets(out_dir: Path) -> None:
    target_assets_dir = out_dir / "assets"
    if STATIC_ASSETS_DIR.resolve() == target_assets_dir.resolve():
        return
    if STATIC_ASSETS_DIR.exists():
        shutil.copytree(STATIC_ASSETS_DIR, target_assets_dir, dirs_exist_ok=True)


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
        return '<p class="empty-state">No extracted text is available for this record yet.</p>'

    paragraphs = [segment.strip() for segment in text.split("\n\n") if segment.strip()]
    return "\n".join(
        f"<p>{html.escape(paragraph).replace(chr(10), '<br>')}</p>" for paragraph in paragraphs
    )


def relative_asset(root_prefix: str, relative_path: str) -> str:
    return f"{root_prefix}/{relative_path}"


def nav_link(label: str, href: str, is_current: bool) -> str:
    current_attr = ' aria-current="page"' if is_current else ""
    return f'<a href="{html.escape(href)}"{current_attr}>{html.escape(label)}</a>'


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
    manifest_url = relative_asset(root_prefix, "manifest.html")
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
        <p class="eyebrow">Research Portal · FOIA Case {EXPECTED_CASE_NUMBER}</p>
        <div class="masthead-row">
          <div class="title-lockup">
            <h1>{html.escape(site_title)}</h1>
            <p class="masthead-note">A research portal for FRUS compilers and historians of Clinton-era diplomacy. Document metadata harvested from the State Department FOIA Library; PDFs hosted at the source.</p>
          </div>
          <nav class="site-nav" aria-label="Primary">
            {nav_link("Collection", home_url, current_page == "collection")}
            {nav_link("Manifest", manifest_url, current_page == "manifest")}
            {nav_link("Keyword Search", search_url, current_page == "search")}
            {nav_link("Semantic Search", semantic_url, current_page == "semantic")}
          </nav>
        </div>
      </div>
    </header>
    <main class="layout">
{body}
    </main>
    <footer class="site-footer">
      <div class="layout">
        <p class="disclaimer">Unofficial research tool. Not affiliated with the U.S. Department of State.</p>
        <p>Document metadata is harvested from the State Department FOIA Library for case {EXPECTED_CASE_NUMBER}. PDFs are linked at their original source on <code>foia.state.gov</code> and are not redistributed by this site.</p>
      </div>
    </footer>{script_tags}
  </body>
</html>
"""


def render_index_page(
    records: list[DocumentRecord],
    text_by_id: dict[str, str],
    site_title: str,
    csv_entries: list[ManifestEntry] | None = None,
) -> str:
    rows = []
    for record in records:
        snippet = build_snippet(text_by_id.get(record.id, ""), limit=140)
        rows.append(
            f"""          <tr>
            <td><a class="table-link" href="./docs/{html.escape(record.id)}.html">{html.escape(record.id)}</a></td>
            <td>{html.escape(record.date)}</td>
            <td>
              <strong>{html.escape(record.title)}</strong>
              <p class="table-snippet">{html.escape(snippet or "Metadata only · extracted text not yet ingested.")}</p>
            </td>
            <td>{html.escape(record.release_status)}</td>
            <td><a class="inline-link" href="{html.escape(record.source_pdf_url)}">Source PDF</a></td>
            <td><a class="inline-link" href="./docs/{html.escape(record.id)}.html">Document page</a></td>
          </tr>"""
        )

    csv_count = len(csv_entries) if csv_entries else 0
    manifest_callout = ""
    if csv_count:
        manifest_callout = f"""
      <section class="card">
        <p class="eyebrow">Full FOIA manifest</p>
        <h2>{csv_count:,} catalogued documents</h2>
        <p>The complete document manifest harvested from the State Department FOIA Library for case {EXPECTED_CASE_NUMBER} is published on this site. Each row links directly to the original PDF on <code>foia.state.gov</code>.</p>
        <div class="action-row">
          <a class="button-link" href="./manifest.html">Browse the full manifest</a>
          <a class="button-link button-link-secondary" href="./data/manifest.csv" download>Download manifest.csv</a>
        </div>
      </section>"""

    body = f"""      <section class="card hero-card">
        <p class="eyebrow">Strobe Talbott · Clinton Administration</p>
        <h2>Document register for FOIA case {EXPECTED_CASE_NUMBER}</h2>
        <p class="lede">A research portal that organizes State Department FOIA metadata, extracted text, keyword search, and a semantic discovery layer for FRUS compilers and historians of late-twentieth-century U.S. diplomacy.</p>
        <p>Document pages cite the original FOIA release. PDFs remain hosted at <code>foia.state.gov</code> and are not redistributed by this site.</p>
        <div class="action-row">
          <a class="button-link" href="./manifest.html">Browse FOIA manifest</a>
          <a class="button-link button-link-secondary" href="./search.html">Keyword search</a>
          <a class="button-link button-link-secondary" href="./semantic.html">Semantic search</a>
        </div>
      </section>{manifest_callout}
      <section class="summary-grid">
        <article class="card stat-card">
          <p class="eyebrow">Annotated record</p>
          <h2>{len(records)}</h2>
          <p class="stat-copy">documents with full per-page metadata, extracted text, and citation block</p>
        </article>
        <article class="card">
          <p class="eyebrow">Editorial method</p>
          <h2>Search-ready static pages</h2>
          <p>Each document page carries bibliographic metadata, visible extracted text, and a direct source URL, so keyword search and future semantic tools can surface useful results without a backend.</p>
        </article>
      </section>
      <section class="card">
        <div class="section-heading">
          <h2>Document register</h2>
          <p>{len(records)} annotated records</p>
        </div>
        <div class="table-wrap">
          <table class="document-table">
            <thead>
              <tr>
                <th scope="col">Document ID</th>
                <th scope="col">Date</th>
                <th scope="col">Title</th>
                <th scope="col">Release Status</th>
                <th scope="col">Source</th>
                <th scope="col">Page</th>
              </tr>
            </thead>
            <tbody>
{chr(10).join(rows)}
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
        page_description="Sample document collection for Strobe Talbott FOIA case F-2017-13804.",
        current_page="collection",
        script_paths=["./assets/js/site.js"],
    )


def render_search_page(site_title: str) -> str:
    body = f"""      <section class="card hero-card">
        <p class="eyebrow">Keyword Search</p>
        <h2>Search the document manifest</h2>
        <p class="lede">Query the catalogued FOIA records for case {EXPECTED_CASE_NUMBER} by document identifier, date, title fragment, or source PDF URL. Each result links directly to the original State Department PDF.</p>
        <p id="pagefind-status" class="status-pill">Loading manifest…</p>
      </section>
      <section class="card">
        <div class="section-heading">
          <h2>Query the catalogue</h2>
          <p class="result-meta">Browser-based search · no server required</p>
        </div>
        <div id="search-interface" class="search-shell"></div>
        <div class="search-tips" aria-label="Search tips">
          <strong>Search tips</strong>
          <p>Combine tokens to narrow your search. Try a document identifier such as <code>C09000008</code>, a four-digit year such as <code>1994</code>, a release-status fragment, or a phrase from a title like <code>NATO</code> or <code>Talbott</code>.</p>
        </div>
      </section>
      <section class="card">
        <div class="section-heading">
          <h2>About this search</h2>
          <p class="result-meta">Static index · client-side ranking</p>
        </div>
        <p>The page loads the published manifest (<a class="inline-link" href="./assets/search/manifest.json">manifest.json</a>, with a CSV fallback to <a class="inline-link" href="./data/manifest.csv">manifest.csv</a>) and matches every query token against each record's document ID, date, title, and PDF URL. Ranking weights identifier matches above titles, dates, and URLs. The full index is shipped with the site and runs entirely in the browser.</p>
        <hr class="gold-rule">
        <p class="result-meta">For bulk analysis, download <a class="inline-link" href="./data/manifest.csv" download>manifest.csv</a>. For full-text discovery across extracted document text, see the <a class="inline-link" href="./semantic.html">semantic search</a> prototype.</p>
      </section>"""

    return render_layout(
        page_title=f"Keyword Search | {site_title}",
        site_title=site_title,
        root_prefix=".",
        body_class="page-search",
        body=body,
        page_description=f"Keyword search across the FOIA document manifest for case {EXPECTED_CASE_NUMBER}.",
        current_page="search",
        script_paths=["./assets/js/site.js", "./assets/js/search.js"],
    )


def render_semantic_page(site_title: str) -> str:
    body = """      <section class="card hero-card">
        <p class="eyebrow">Semantic Search</p>
        <h2>Top matching passages from extracted document text</h2>
        <p class="lede">Semantic search ranks candidate passages from the precomputed chunk index. The current build uses keyword-overlap scoring and is structured so vector embeddings can be substituted without changes to the page interface.</p>
        <div class="notice">
          The ranking below is a lightweight approximation suitable for browse-and-discover research; cite the source PDF rather than the snippet.
        </div>
      </section>
      <section class="card">
        <form id="semantic-search-form" class="search-form">
          <label for="semantic-query">Search the sample collection</label>
          <div class="search-form-row">
            <input
              id="semantic-query"
              name="query"
              type="search"
              placeholder="Try: Moscow visit, NATO briefing, Balkans diplomacy"
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
          <p id="semantic-summary">Enter a query to rank the sample chunk index.</p>
        </div>
        <div id="semantic-results" class="results-list">
          <p class="empty-state">Enter a query to search the sample chunk index.</p>
        </div>
      </section>"""

    return render_layout(
        page_title=f"Semantic Prototype | {site_title}",
        site_title=site_title,
        root_prefix=".",
        body_class="page-semantic",
        body=body,
        page_description="AI-enhanced semantic search prototype for the sample FOIA document collection.",
        current_page="semantic",
        script_paths=["./assets/js/site.js", "./assets/js/semantic.js"],
    )


def render_document_page(
    record: DocumentRecord, text: str, site_title: str, snippet: str
) -> str:
    citation = build_citation(record)
    body = f"""      <article class="card document-card" data-pagefind-body>
        <p class="eyebrow">Document Record</p>
        <h2 data-pagefind-meta="title">{html.escape(record.title)}</h2>
        <p class="document-summary">{html.escape(record.date)} · {html.escape(record.case_number)} · Doc. {html.escape(record.id)} · {html.escape(record.release_status)}</p>
        <p class="lede">{html.escape(snippet or 'Metadata-only entry. Extracted text has not yet been ingested for this record.')}</p>
        <div class="action-row">
          <a class="button-link" href="{html.escape(record.source_pdf_url)}">Open Source PDF</a>
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
          <div>
            <dt>Document title</dt>
            <dd>{html.escape(record.title)}</dd>
          </div>
          <div>
            <dt>Date</dt>
            <dd data-pagefind-meta="date">{html.escape(record.date)}</dd>
          </div>
          <div>
            <dt>FOIA case number</dt>
            <dd>{html.escape(record.case_number)}</dd>
          </div>
          <div>
            <dt>Document ID</dt>
            <dd data-pagefind-meta="document_id">{html.escape(record.id)}</dd>
          </div>
          <div>
            <dt>Release status</dt>
            <dd data-pagefind-meta="release_status">{html.escape(record.release_status)}</dd>
          </div>
          <div>
            <dt>Source PDF</dt>
            <dd><a class="inline-link" href="{html.escape(record.source_pdf_url)}">View original source link</a></dd>
          </div>
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


def load_csv_manifest(
    csv_path: Path,
    descriptions: dict[str, dict[str, str]] | None = None,
) -> list[ManifestEntry]:
    entries: list[ManifestEntry] = []
    descriptions = descriptions or {}
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            doc_id = (row.get("document_id") or "").strip()
            pdf_url = (row.get("pdf_url") or "").strip()
            entry_description = (row.get("description") or "").strip()
            entry_source = (row.get("description_source") or "").strip()
            if not entry_description and pdf_url in descriptions:
                entry_description = descriptions[pdf_url].get("description", "")
                entry_source = descriptions[pdf_url].get("source", entry_source)
            entries.append(
                ManifestEntry(
                    document_id=doc_id,
                    date=(row.get("date") or "").strip(),
                    title=(row.get("title") or "").strip(),
                    pdf_url=pdf_url,
                    description=entry_description,
                    description_source=entry_source,
                )
            )
    return entries


def load_descriptions(path: Path) -> dict[str, dict[str, str]]:
    """Load the pdf_url-keyed descriptions JSON.

    The map is keyed by full `pdf_url` so duplicate `document_id` values
    across different FOIA release folders each retain their own
    PDF-grounded (or metadata-fallback) description.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(k): {
            "description": str(v.get("description", "")) if isinstance(v, dict) else "",
            "source": str(v.get("source", "")) if isinstance(v, dict) else "",
        }
        for k, v in data.items()
    }


def render_manifest_page(entries: list[ManifestEntry], site_title: str) -> str:
    rows: list[str] = []
    for entry in entries:
        if not entry.document_id and not entry.pdf_url:
            continue
        description_html = ""
        if entry.description:
            description_html = (
                f'\n              <p class="manifest-description">'
                f"{html.escape(entry.description)}</p>"
            )
        rows.append(
            f"""          <tr>
            <td>{html.escape(entry.document_id)}</td>
            <td>{html.escape(entry.date)}</td>
            <td>
              <strong>{html.escape(entry.title)}</strong>{description_html}
            </td>
            <td><a class="inline-link" href="{html.escape(entry.pdf_url)}" rel="noopener" target="_blank">PDF</a></td>
          </tr>"""
        )

    body = f"""      <section class="card hero-card">
        <p class="eyebrow">Full FOIA case manifest</p>
        <h2>Document manifest for case {EXPECTED_CASE_NUMBER}</h2>
        <p class="lede">Every record catalogued in <code>data/manifest.csv</code>. Each row links directly to the original PDF on the State Department FOIA Library. Use the filter box to narrow by document identifier, date, or title fragment.</p>
        <div class="action-row">
          <a class="button-link" href="./data/manifest.csv" download>Download manifest.csv</a>
          <a class="button-link button-link-secondary" href="./index.html">Back to collection overview</a>
        </div>
      </section>
      <section class="card">
        <div class="section-heading">
          <h2>All documents</h2>
          <p>Manifest entries: <strong>{len(rows)}</strong>. Source: <a class="inline-link" href="./data/manifest.csv">data/manifest.csv</a> (with neutral 2-3 sentence descriptions, one per <code>pdf_url</code>, joined from <a class="inline-link" href="./data/manifest_enriched.csv">manifest_enriched.csv</a>).</p>
        </div>
        <form class="search-form" role="search" onsubmit="return false;">
          <label for="manifest-filter">Filter by ID, date, title, or description</label>
          <div class="search-form-row">
            <input
              id="manifest-filter"
              name="filter"
              type="search"
              placeholder="e.g. Talbott, 1994, C09000008"
              autocomplete="off"
            >
          </div>
          <p id="manifest-count" class="status-pill">Showing {len(rows)} of {len(rows)} records</p>
        </form>
        <div class="table-wrap">
          <table class="document-table" id="manifest-table">
            <thead>
              <tr>
                <th scope="col">Document ID</th>
                <th scope="col">Date</th>
                <th scope="col">Title &amp; description</th>
                <th scope="col">PDF</th>
              </tr>
            </thead>
            <tbody>
{chr(10).join(rows)}
            </tbody>
          </table>
        </div>
      </section>"""

    return render_layout(
        page_title=f"Manifest | {site_title}",
        site_title=site_title,
        root_prefix=".",
        body_class="page-manifest",
        body=body,
        page_description=(
            f"Full document manifest for FOIA case {EXPECTED_CASE_NUMBER} with State Department PDF links."
        ),
        current_page="manifest",
        script_paths=["./assets/js/site.js", "./assets/js/manifest.js"],
    )


def copy_csv_manifest(csv_path: Path, out_dir: Path) -> Path | None:
    if not csv_path.exists():
        return None
    target_dir = out_dir / "data"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "manifest.csv"
    shutil.copyfile(csv_path, target)
    enriched = csv_path.parent / "manifest_enriched.csv"
    if enriched.exists():
        shutil.copyfile(enriched, target_dir / "manifest_enriched.csv")
    return target


def write_search_manifest(
    entries: list[ManifestEntry],
    out_dir: Path,
    document_page_ids: list[str],
) -> None:
    target_dir = out_dir / "assets" / "search"
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "case_number": EXPECTED_CASE_NUMBER,
        "record_count": sum(1 for entry in entries if entry.document_id or entry.pdf_url),
        "records": [
            {
                "document_id": entry.document_id,
                "date": entry.date,
                "title": entry.title,
                "pdf_url": entry.pdf_url,
                "description": entry.description,
                "description_source": entry.description_source,
            }
            for entry in entries
            if entry.document_id or entry.pdf_url
        ],
    }
    (target_dir / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    (target_dir / "doc_pages.json").write_text(
        json.dumps(sorted(set(document_page_ids)), ensure_ascii=False),
        encoding="utf-8",
    )


def build_site(manifest_path: Path, out_dir: Path, site_title: str) -> list[DocumentRecord]:
    manifest_path = manifest_path.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    records = load_manifest(manifest_path)
    validate_records(records, manifest_path)
    text_by_id = {record.id: read_document_text(record, manifest_path) for record in records}

    copy_static_assets(out_dir)

    docs_dir = out_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for existing_page in docs_dir.glob("*.html"):
        existing_page.unlink()

    descriptions = load_descriptions(DEFAULT_DESCRIPTIONS_JSON)

    csv_entries: list[ManifestEntry] = []
    if DEFAULT_CSV_MANIFEST.exists():
        csv_entries = load_csv_manifest(DEFAULT_CSV_MANIFEST, descriptions)
        copy_csv_manifest(DEFAULT_CSV_MANIFEST, out_dir)
        write_text(
            out_dir / "manifest.html",
            render_manifest_page(csv_entries, site_title),
        )

    write_text(
        out_dir / "index.html",
        render_index_page(records, text_by_id, site_title, csv_entries),
    )
    write_text(out_dir / "search.html", render_search_page(site_title))
    write_text(out_dir / "semantic.html", render_semantic_page(site_title))

    for record in records:
        text = text_by_id.get(record.id, "")
        snippet = build_snippet(text)
        write_text(
            docs_dir / f"{record.id}.html",
            render_document_page(record, text, site_title, snippet),
        )

    write_search_manifest(
        csv_entries,
        out_dir,
        document_page_ids=[record.id for record in records],
    )

    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the static FOIA sample site.")
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = build_site(args.manifest, args.out, args.site_title)
    print(f"Built {len(records)} document pages plus index and search assets in {args.out}.")


if __name__ == "__main__":
    main()
