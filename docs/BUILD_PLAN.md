# Build Plan

## Phase 1: Sample static site

Start with a fully static sample-data MVP that proves the publication workflow:

- sample manifest
- sample extracted text
- generated document pages
- static index page
- local build scripts

This phase validates layout, metadata, and build/deploy mechanics before touching the real corpus.

## Phase 2: Real FOIA manifest harvest

Replace the placeholder workflow with a real harvester for case `F-2017-13804`.

Status: implemented for the current MVP. Keep this phase open for endpoint drift, provenance improvements, and repeatable refresh audits.

Goals:

- collect document metadata
- capture stable source PDF URLs
- normalize document IDs
- preserve provenance fields such as posted date, document type, from/to fields, collection, raw release code, and harvest timestamp
- preserve polite request pacing and limited test runs

## Phase 3: PDF text extraction and OCR

Add a reproducible text extraction pipeline for locally cached PDFs.

Status: implemented for machine-readable extraction from the local PDF cache. OCR remains optional and should be used only when audit output shows documents that need it.

Expected work:

- machine-readable PDF extraction with `pypdf` or `pdfplumber`
- OCR status reporting for scanned pages, with optional `ocrmypdf` integration
- per-document text outputs
- page counts, text character counts, extraction reports, and manifest updates
- limited sample runs for development

## Phase 4: Pagefind keyword search

Move from Pagefind-ready pages to a fully indexed keyword search build.

Status: implemented. The search page now prefers Pagefind and falls back to manifest search if Pagefind assets are absent.

Goals:

- stable Pagefind indexing in local and GitHub Actions builds
- clean search result titles and snippets
- future metadata filters for year, document ID, and release status

## Phase 5: Semantic search with embeddings

Move from placeholder keyword-overlap scoring to local vector retrieval first, then model embeddings when needed.

Status: local hashed TF-IDF vector retrieval is implemented. Model embeddings remain a later enhancement.

Expected work:

- better chunking strategy by document and page
- deterministic local hashed TF-IDF vectors for the static prototype
- offline or precomputed embeddings
- ranking based on vector similarity
- transparent labeling of prototype versus production search behavior

## Cross-phase hardening

Compiler-facing reliability needs continuous audit checks across all phases:

- no duplicate manifest IDs
- no missing source PDF URLs
- generated document page count matches manifest count
- Pagefind assets exist after build
- cached PDF count, checksum count, extracted text count, and OCR-needed count are visible in `scripts/audit_collection.py`

## Phase 6: Optional MCP/OpenAPI integration for FRUS tools

Add optional integration points for FRUS-oriented research tools if they help historians work across the collection.

Possible directions:

- document cross-reference helpers
- research export endpoints
- historian-facing tooling that stays separate from the public static site
