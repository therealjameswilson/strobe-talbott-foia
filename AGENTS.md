# AGENTS.md

## Project mission

Build a public GitHub Pages website for the Strobe Talbott FOIA case F-2017-13804.

The site is intended to help FRUS compilers and historians working on Clinton administration volumes. The main goals are:

1. Harvest metadata and PDF links from the State Department FOIA Library.
2. Build a document manifest for all records in case F-2017-13804.
3. Extract searchable text from PDFs.
4. Generate a static website with one page per document.
5. Provide full-text keyword search across the whole collection.
6. Add an AI-enhanced semantic search layer.
7. Keep raw PDFs out of the GitHub repository unless they are small test fixtures.

## Core architecture

Use a static-site architecture:

- Python for scraping, manifest generation, PDF text extraction, and chunk generation.
- Static HTML/CSS/JS for the site.
- Pagefind for keyword search.
- A lightweight client-side semantic search prototype using precomputed chunks and embeddings or placeholder vectors for the first version.
- GitHub Actions for build and deployment to GitHub Pages.

## Important constraints

Do not commit the full PDF corpus to the repository. Store only:

- metadata
- extracted text
- generated HTML
- search index
- small sample PDFs for testing, if needed

The site should link to original State Department PDF URLs from the manifest.

## Desired repository structure

Use this structure unless there is a strong reason to change it:

```text
strobe-talbott-foia/
  AGENTS.md
  README.md
  requirements.txt
  package.json
  data/
    manifest.csv
    manifest.json
    sample_manifest.json
  scripts/
    harvest_foia.py
    extract_text.py
    build_site.py
    build_chunks.py
    build_semantic_index.py
  site/
    index.html
    search.html
    semantic.html
    assets/
      css/
        style.css
      js/
        search.js
        semantic.js
    docs/
  tests/
    test_manifest.py
    test_build_site.py
  .github/
    workflows/
      deploy.yml
```

## Coding standards

- Prefer clear, boring, maintainable Python.
- Use type hints where useful.
- Use dataclasses for document records.
- Keep scraping, extraction, and site generation as separate scripts.
- Add `--limit` and `--sample` options to long-running scripts.
- Never require downloading thousands of PDFs just to test the site.
- Make every generated document page include metadata and the source PDF link.
- Make results useful to historians: show document ID, date, subject/title, source URL, and text snippet.

## Search requirements

Keyword search:

- Use Pagefind if possible.
- Generate one HTML page per FOIA document.
- Include document metadata in the HTML so Pagefind can surface useful result titles and snippets.
- Add filters later for year, document ID, and release status.

Semantic search:

- Create a first-pass static semantic search prototype.
- Chunk extracted text by document and page if available.
- Store chunks in `site/assets/search/chunks.json`.
- If real embeddings are not yet configured, create the interface and code path with a documented placeholder.
- Do not expose API keys in frontend code.

## GitHub Pages

Use a custom GitHub Actions workflow to build and deploy the static site.

## Testing

Add lightweight tests for:

- manifest parsing
- document ID normalization
- generated document page creation
- no missing source URLs in generated pages

## Documentation

README.md should explain:

- what the project is
- how to run a sample build
- how to harvest metadata
- how to build the site
- how keyword search works
- how semantic search will work
- why full PDFs are not committed to the repo

## Do not do

- Do not build a Flask/Django backend.
- Do not require Elasticsearch.
- Do not require a paid API for the MVP.
- Do not put secrets in the repo.
- Do not assume the full corpus fits inside GitHub Pages.
