# Strobe Talbott FOIA MVP

This repository builds a public GitHub Pages website for State Department FOIA case `F-2017-13804`, focused on supporting FRUS compilers and researchers working on Clinton administration history.

The project now includes the harvested case manifest and extracted text for the public records currently discovered for this case. It still keeps the full PDF corpus out of Git: PDFs can be mirrored locally into `data/pdfs/`, but the public site links back to the State Department source files.

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

The MVP keeps raw PDFs out of the repository. The repo stores metadata, extracted text, source scripts, and static assets; GitHub Actions regenerates document HTML and search artifacts during deployment. That keeps the project lightweight, avoids duplicating the State Department source corpus, and makes GitHub Pages deployment practical.

## Data modes

The repository ships with five synthetic placeholder records in `data/sample_manifest.json`. These are not real FOIA releases. They exist only to exercise the build pipeline and user interface.

The default production workflow uses `data/manifest.json`, which is the harvested manifest for case `F-2017-13804`. Extracted text lives under `data/text/`. Raw PDFs, raw debug responses, and build reports are local-only and gitignored.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
npm run build
npm run audit
npm run serve
```

Then open `http://localhost:8000`.

When `data/pdfs/` contains locally cached PDFs, the generated collection UI automatically surfaces local download links and batch-download actions. The local server maps those gitignored files under `/pdfs/` without committing them to GitHub.

To refresh the full corpus locally, run the harvest/download/extract commands in the harvesting section before `npm run build`.

## What the build does

`npm run build` runs the full MVP pipeline:

1. `python3 scripts/build_site.py --manifest data/manifest.json --out site`
2. `python3 scripts/build_chunks.py --manifest data/manifest.json`
3. `python3 scripts/build_semantic_index.py`
4. `pagefind --site site`

That produces:

- `site/index.html`
- `site/search.html`
- `site/semantic.html`
- `site/docs/*.html`
- `site/assets/search/manifest.json`
- `site/assets/search/chunks.json`
- `site/assets/search/semantic_index.json`
- `site/pagefind/*`

Those files are deployment artifacts. They are rebuilt locally and in GitHub Actions rather than committed.

## Running a sample build without Node

If you only want to exercise the Python portion first:

```bash
python3 scripts/build_site.py --manifest data/sample_manifest.json --out site
python3 scripts/build_chunks.py --manifest data/sample_manifest.json
python3 scripts/build_semantic_index.py
python3 scripts/serve_site.py
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

To harvest the full case metadata set and prepare a local PDF mirror workflow:

```bash
python3 scripts/harvest_foia.py --case-number F-2017-13804 --limit 0 --out data/manifest.json
python3 scripts/download_pdfs.py --manifest data/manifest.json --out data/pdfs --limit 0 --update-manifest
python3 scripts/extract_text.py --manifest data/manifest.json --out data/text --pdf-dir data/pdfs --limit 0 --skip-existing --update-manifest
python3 scripts/build_site.py --manifest data/manifest.json --out site
npm run build:search
npm run audit
```

Useful options:

- `--dry-run` discovers records and prints a summary without writing `data/manifest.json`
- `--debug` saves raw HTML and JSON responses under `data/raw/` for troubleshooting
- `--sample` keeps the placeholder-only mode for offline development
- `scripts/download_pdfs.py` stores PDFs in `data/pdfs/`, writes checksums and byte counts into the manifest when `--update-manifest` is used, and writes a JSON report under `data/reports/`
- `scripts/serve_site.py` exposes locally cached PDFs under `/pdfs/` so the GUI can download them one at a time or in batches
- `scripts/audit_collection.py` reports compiler-readiness metrics such as cached PDF count, extracted text count, duplicate IDs, generated pages, and search artifacts

The current live strategy is intentionally cautious:

- fetch the FOIA search page to confirm the search UI is present
- call the FOIA metadata endpoint using the same parameter shape the site’s JavaScript uses
- normalize the returned metadata into this repository’s manifest schema, including posted date, document type, from/to fields, collection, raw release code, and harvest timestamp when supplied
- stop at metadata and source URLs during harvest, then let the separate local cache step fetch PDFs deliberately

If the State Department changes the live endpoint shape, the script fails gracefully and prints diagnostic guidance instead of silently writing bad output.

## Extracting text from local PDFs

The extraction script works from a local PDF cache and does not fetch PDFs on its own:

```bash
python3 scripts/extract_text.py --manifest data/manifest.json --out data/text --pdf-dir data/pdfs --limit 10 --update-manifest
```

The current extractor can:

- read machine-readable text from locally cached PDFs with `pypdf`
- write one `.txt` file per document under `data/text/`
- update manifest `text_path`, page count, character count, extraction status, and OCR status values
- optionally attempt OCR with `--ocr` when `ocrmypdf` is installed locally

The next extraction improvement is layout-aware extraction with `pdfplumber` for documents where plain `pypdf` text is too noisy.

It still does not download the corpus by default during normal development. That remains a separate deliberate step.

## Keyword search

Keyword search uses Pagefind when `site/pagefind/` has been generated. Each generated document page contains visible metadata and document text, so Pagefind can surface useful result titles and snippets directly from static HTML. The search UI lives at `site/search.html` and loads the Pagefind assets after `npm run build:search`.

If Pagefind assets are missing in a development build, the page falls back to a manifest-based browser search so compilers can still search IDs, dates, titles, release status, source URLs, and text snippets.

If extracted text is not available yet, Pagefind still indexes metadata-rich document pages, including titles, document IDs, dates, release status, and source links.

Planned future enhancements include filters for:

- year
- document ID
- release status

## Semantic search prototype

The semantic search page at `site/semantic.html` is labeled as an AI-enhanced prototype. For the MVP:

- Python chunks extracted text into small passages when local text is available
- chunks are written to `site/assets/search/chunks.json`
- `scripts/build_semantic_index.py` builds a deterministic local hashed TF-IDF vector index
- browser-side JavaScript ranks chunks with a combined local vector and keyword score
- the code is structured so model embeddings can replace the local vector index later

No API keys or paid services are exposed in the frontend.

## Why raw PDFs are not committed

The project should link back to the original State Department FOIA URLs instead of storing the full PDF corpus in Git. That keeps the repository smaller, avoids duplicating source records, and helps ensure the published site remains maintainable within GitHub Pages constraints. Small test fixtures are acceptable later if a specific parsing or OCR test needs them.
