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
        <p class="eyebrow">Strobe Talbott FOIA MVP</p>
        <div class="masthead-row">
          <div class="title-lockup">
            <h1>{html.escape(site_title)}</h1>
            <p class="masthead-note">Sample-first static publication workflow for FRUS compilers and Clinton administration researchers.</p>
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
        <p>This MVP uses synthetic sample records for workflow testing. It does not publish the full PDF corpus.</p>
      </div>
    </footer>{script_tags}
  </body>
</html>
"""


def render_index_page(
    records: list[DocumentRecord], text_by_id: dict[str, str], site_title: str
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
              <p class="table-snippet">{html.escape(snippet or "Placeholder record ready for generated text.")}</p>
            </td>
            <td>{html.escape(record.release_status)}</td>
            <td><a class="inline-link" href="{html.escape(record.source_pdf_url)}">Source PDF</a></td>
            <td><a class="inline-link" href="./docs/{html.escape(record.id)}.html">Document page</a></td>
          </tr>"""
        )

    body = f"""      <section class="card hero-card">
        <p class="eyebrow">Public history workflow</p>
        <h2>Sample document register for case {EXPECTED_CASE_NUMBER}</h2>
        <p class="lede">This sample site shows how a static GitHub Pages publication can organize FOIA metadata, extracted text, keyword search, and a future semantic discovery layer for FRUS compilers and historians.</p>
        <p>The current build uses placeholder records only. It is designed to prove the workflow before a real State Department FOIA manifest harvest is connected.</p>
        <div class="action-row">
          <a class="button-link" href="./search.html">Keyword search</a>
          <a class="button-link button-link-secondary" href="./semantic.html">Semantic prototype</a>
        </div>
      </section>
      <section class="summary-grid">
        <article class="card stat-card">
          <p class="eyebrow">Project Scope</p>
          <h2>{len(records)}</h2>
          <p class="stat-copy">sample documents in the current manifest</p>
        </article>
        <article class="card">
          <p class="eyebrow">Collection Notes</p>
          <h2>Search-ready static pages</h2>
          <p>Each document page includes bibliographic metadata, visible extracted text, and a direct source URL so Pagefind and future semantic tools can surface meaningful results.</p>
        </article>
      </section>
      <section class="card">
        <div class="section-heading">
          <h2>Sample documents</h2>
          <p>Document count: {len(records)} sample placeholder records</p>
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
    body = """      <section class="card hero-card">
        <p class="eyebrow">Keyword Search</p>
        <h2>Static full-text search with Pagefind</h2>
        <p class="lede">The keyword search experience is fully client-side. After the generated HTML is indexed, researchers can search document titles, visible metadata, and extracted text without a backend.</p>
        <p id="pagefind-status" class="status-pill">Looking for Pagefind assets...</p>
      </section>
      <section class="card">
        <div id="search-interface" class="search-shell"></div>
      </section>
      <section class="card">
        <h2>How it works</h2>
        <p>Each generated document page includes document ID, date, release status, source URL, and extracted text. Pagefind indexes the `site/` directory after `npm run build:search` runs.</p>
      </section>"""

    return render_layout(
        page_title=f"Keyword Search | {site_title}",
        site_title=site_title,
        root_prefix=".",
        body_class="page-search",
        body=body,
        page_description="Keyword search across the sample FOIA document collection.",
        current_page="search",
        script_paths=["./assets/js/site.js", "./assets/js/search.js"],
    )


def render_semantic_page(site_title: str) -> str:
    body = """      <section class="card hero-card">
        <p class="eyebrow">AI-enhanced / semantic search prototype</p>
        <h2>Top matching chunks from precomputed sample text</h2>
        <p class="lede">This MVP does not use real embeddings yet. It loads chunk data generated at build time and ranks candidate passages by keyword overlap while preserving a clean upgrade path to vectors later.</p>
        <div class="notice">
          <strong>Prototype notice.</strong> The ranking below is an intentionally lightweight approximation for interface and workflow testing.
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
        <p class="lede">{html.escape(snippet or 'Sample placeholder record for MVP testing.')}</p>
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

    write_text(out_dir / "index.html", render_index_page(records, text_by_id, site_title))
    write_text(out_dir / "search.html", render_search_page(site_title))
    write_text(out_dir / "semantic.html", render_semantic_page(site_title))

    for record in records:
        text = text_by_id.get(record.id, "")
        snippet = build_snippet(text)
        write_text(
            docs_dir / f"{record.id}.html",
            render_document_page(record, text, site_title, snippet),
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
