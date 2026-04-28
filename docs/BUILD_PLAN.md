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

Goals:

- collect document metadata
- capture stable source PDF URLs
- normalize document IDs
- preserve polite request pacing and limited test runs

## Phase 3: PDF text extraction and OCR

Add a reproducible text extraction pipeline for locally cached PDFs.

Expected work:

- machine-readable PDF extraction with `pypdf` or `pdfplumber`
- OCR for scanned pages
- per-document text outputs
- limited sample runs for development

## Phase 4: Pagefind keyword search

Move from Pagefind-ready pages to a fully indexed keyword search build.

Goals:

- stable Pagefind indexing in local and GitHub Actions builds
- clean search result titles and snippets
- future metadata filters for year, document ID, and release status

## Phase 5: Semantic search with embeddings

Replace placeholder keyword-overlap scoring with real embedding-based retrieval.

Expected work:

- better chunking strategy by document and page
- offline or precomputed embeddings
- ranking based on vector similarity
- transparent labeling of prototype versus production search behavior

## Phase 6: Optional MCP/OpenAPI integration for FRUS tools

Add optional integration points for FRUS-oriented research tools if they help historians work across the collection.

Possible directions:

- document cross-reference helpers
- research export endpoints
- historian-facing tooling that stays separate from the public static site
