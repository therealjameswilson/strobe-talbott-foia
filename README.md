# Strobe Talbott FOIA MVP

This repository builds a public GitHub Pages website for State Department FOIA case `F-2017-13804`, focused on supporting FRUS compilers and researchers working on Clinton administration history.

The first MVP is intentionally sample-data-first. It demonstrates the static-site workflow, per-document pages, keyword search integration, and a prototype semantic search layer without requiring the full FOIA corpus or any paid services.

## Who this is for

- FRUS compilers preparing Clinton administration volumes
- Historians and researchers tracing documentary coverage of Strobe Talbott and related diplomacy
- Maintainers who want a reproducible, low-cost, static publication pipeline

## Architecture

The project uses a static-site architecture:

- Python scripts for metadata harvesting, text extraction, manifest handling, document page generation, and semantic chunk generation
- Static HTML, CSS, and JavaScript for the website
- [Pagefind](https://pagefind.app/) for client-side keyword search
- A lightweight browser-side semantic search prototype built from precomputed chunks
- GitHub Actions for repeatable build and deployment to GitHub Pages

The MVP keeps raw PDFs out of the repository. The repo stores only metadata, extracted text, generated HTML, and search artifacts. That keeps the project lightweight, avoids duplicating the State Department source corpus, and makes GitHub Pages deployment practical.

## Sample-first workflow

The repository ships with five synthetic placeholder records in `data/sample_manifest.json`. These are not real FOIA releases. They exist only to exercise the build pipeline and user interface before a real harvester is wired in.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
npm run build
npm run serve
```

Then open `http://localhost:8000`.

## What the build does

`npm run build` runs the full MVP pipeline:

1. `python3 scripts/build_site.py`
2. `python3 scripts/build_chunks.py`
3. `python3 scripts/build_semantic_index.py`
4. `pagefind --site site`

That produces:

- `site/index.html`
- `site/search.html`
- `site/semantic.html`
- `site/docs/*.html`
- `site/assets/search/chunks.json`
- `site/assets/search/semantic_index.json`
- `site/pagefind/*`

## Running a sample build without Node

If you only want to exercise the Python portion first:

```bash
python3 scripts/build_site.py
python3 scripts/build_chunks.py
python3 scripts/build_semantic_index.py
python3 -m http.server 8000 --directory site
```

This generates the site and semantic prototype pages. Keyword search becomes active after `npm run build:search` creates the Pagefind index.

## Harvesting metadata

The repository now includes a research-mode harvester for live case discovery. It queries the official FOIA Library metadata backend with a polite user agent, retry handling, and basic rate limiting. It does not download PDFs.

Run the end-to-end metadata and site build flow like this:

```bash
python3 scripts/harvest_foia.py --case-number F-2017-13804 --limit 10 --out data/manifest.json
python3 scripts/build_site.py --manifest data/manifest.json --out site
npm run build:search
```

Useful options:

- `--dry-run` discovers records and prints a summary without writing `data/manifest.json`
- `--debug` saves raw HTML and JSON responses under `data/raw/` for troubleshooting
- `--sample` keeps the placeholder-only mode for offline development

The current live strategy is intentionally cautious:

- fetch the FOIA search page to confirm the search UI is present
- call the FOIA metadata endpoint using the same parameter shape the site’s JavaScript uses
- normalize the returned metadata into this repository’s manifest schema
- stop at metadata and source URLs rather than downloading any PDFs

If the State Department changes the live endpoint shape, the script fails gracefully and prints diagnostic guidance instead of silently writing bad output.

## Extracting text later

The text extraction script is also a placeholder:

```bash
python3 scripts/extract_text.py --manifest data/manifest.json --out data/text --limit 10
```

The future extraction pipeline should support:

- `pypdf` or `pdfplumber` for machine-readable PDFs
- OCR for scanned image PDFs when necessary
- per-document `.txt` outputs referenced from the manifest

It should never download or process the full corpus by default during normal development.

## Keyword search

Keyword search uses Pagefind. Each generated document page contains visible metadata and document text, so Pagefind can surface useful result titles and snippets directly from static HTML. The search UI lives at `site/search.html` and loads the Pagefind assets after `npm run build:search`.

Planned future enhancements include filters for:

- year
- document ID
- release status

## Semantic search prototype

The semantic search page at `site/semantic.html` is labeled as an AI-enhanced prototype. For the MVP:

- Python chunks the sample text into small passages
- chunks are written to `site/assets/search/chunks.json`
- browser-side JavaScript ranks chunks by keyword overlap
- the code is structured so real embeddings can replace the placeholder scoring later

No API keys or paid services are exposed in the frontend.

## Why raw PDFs are not committed

The project should link back to the original State Department FOIA URLs instead of storing the full PDF corpus in Git. That keeps the repository smaller, avoids duplicating source records, and helps ensure the published site remains maintainable within GitHub Pages constraints. Small test fixtures are acceptable later if a specific parsing or OCR test needs them.
