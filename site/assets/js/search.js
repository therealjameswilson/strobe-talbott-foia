const MANIFEST_JSON_URL = "./assets/search/manifest.json";
const MANIFEST_CSV_URL = "./data/manifest.csv";
const MAX_RESULTS = 50;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function parseCsv(text) {
  const rows = [];
  let field = "";
  let row = [];
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (ch === "\r") {
      // ignore; \n will close the row
    } else {
      field += ch;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

function recordsFromCsvText(text) {
  const rows = parseCsv(text).filter((r) => r.length && r.some((cell) => cell !== ""));
  if (!rows.length) return [];
  const header = rows.shift().map((h) => h.trim().toLowerCase());
  const idxId = header.indexOf("document_id");
  const idxDate = header.indexOf("date");
  const idxTitle = header.indexOf("title");
  const idxUrl = header.indexOf("pdf_url");
  return rows
    .map((cells) => ({
      document_id: (cells[idxId] || "").trim(),
      date: (cells[idxDate] || "").trim(),
      title: (cells[idxTitle] || "").trim(),
      pdf_url: (cells[idxUrl] || "").trim(),
    }))
    .filter((r) => r.document_id || r.pdf_url);
}

async function loadRecords() {
  try {
    const response = await fetch(MANIFEST_JSON_URL, { cache: "no-store" });
    if (response.ok) {
      const payload = await response.json();
      if (Array.isArray(payload)) return payload;
      if (Array.isArray(payload.records)) return payload.records;
    }
  } catch (error) {
    console.warn("Falling back to CSV manifest:", error);
  }
  const csvResponse = await fetch(MANIFEST_CSV_URL, { cache: "no-store" });
  if (!csvResponse.ok) {
    throw new Error(`Unable to load manifest at ${MANIFEST_CSV_URL}`);
  }
  const text = await csvResponse.text();
  return recordsFromCsvText(text);
}

function tokenize(query) {
  return query
    .toLowerCase()
    .split(/\s+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

function highlight(text, tokens) {
  if (!text) return "";
  let safe = escapeHtml(text);
  if (!tokens.length) return safe;
  const escapedTokens = tokens
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .filter(Boolean);
  if (!escapedTokens.length) return safe;
  const re = new RegExp(`(${escapedTokens.join("|")})`, "gi");
  return safe.replace(re, "<mark>$1</mark>");
}

function scoreRecord(record, tokens) {
  if (!tokens.length) return 0;
  const id = (record.document_id || "").toLowerCase();
  const date = (record.date || "").toLowerCase();
  const title = (record.title || "").toLowerCase();
  const url = (record.pdf_url || "").toLowerCase();
  let score = 0;
  for (const token of tokens) {
    let tokenScore = 0;
    if (id.includes(token)) tokenScore += 5;
    if (title.includes(token)) tokenScore += 3;
    if (date.includes(token)) tokenScore += 2;
    if (url.includes(token)) tokenScore += 1;
    if (tokenScore === 0) return 0;
    score += tokenScore;
  }
  return score;
}

function pageUrlForRecord(record) {
  const id = (record.document_id || "").trim();
  if (!id) return "";
  return `./docs/${encodeURIComponent(id)}.html`;
}

function renderResult(record, tokens, hasDocPage) {
  const docPageUrl = hasDocPage ? pageUrlForRecord(record) : "";
  const titleHtml = highlight(record.title || "Untitled record", tokens);
  const idHtml = highlight(record.document_id || "—", tokens);
  const dateHtml = highlight(record.date || "Unknown date", tokens);
  const urlHtml = highlight(record.pdf_url || "", tokens);
  const docPageLink = docPageUrl
    ? `<a class="inline-link" href="${escapeHtml(docPageUrl)}">Open document page</a> · `
    : "";
  return `
    <article class="result-card">
      <p class="result-label">Document ID ${idHtml}</p>
      <h3>${titleHtml}</h3>
      <p class="result-meta">${dateHtml}</p>
      <p class="result-snippet"><a class="inline-link" href="${escapeHtml(record.pdf_url)}" rel="noopener" target="_blank">${urlHtml || "Source PDF"}</a></p>
      <p>${docPageLink}<a class="inline-link" href="${escapeHtml(record.pdf_url)}" rel="noopener" target="_blank">Direct PDF link</a></p>
    </article>
  `;
}

document.addEventListener("DOMContentLoaded", async () => {
  const status = document.getElementById("pagefind-status");
  const container = document.getElementById("search-interface");

  if (!status || !container) {
    return;
  }

  container.innerHTML = `
    <form id="keyword-search-form" class="search-form" role="search" onsubmit="return false;">
      <label for="keyword-query">Search by document ID, date, title, or PDF URL</label>
      <div class="search-form-row">
        <input
          id="keyword-query"
          name="query"
          type="search"
          placeholder="e.g. Talbott, 1994, C09000008, NATO"
          autocomplete="off"
          autofocus
        >
        <button type="submit">Search</button>
      </div>
      <p id="search-summary" class="result-meta">Loading manifest…</p>
      <div id="keyword-results" class="results-list">
        <p class="empty-state">Loading manifest records…</p>
      </div>
    </form>
  `;

  const form = document.getElementById("keyword-search-form");
  const input = document.getElementById("keyword-query");
  const summary = document.getElementById("search-summary");
  const results = document.getElementById("keyword-results");

  let records = [];
  let docPageIds = new Set();

  try {
    records = await loadRecords();
  } catch (error) {
    status.textContent = "Unable to load the FOIA manifest for keyword search.";
    status.dataset.state = "error";
    summary.textContent = "Manifest data unavailable.";
    results.innerHTML =
      '<p class="empty-state">Could not load <code>data/manifest.csv</code>. Check the deployment and try again.</p>';
    console.error(error);
    return;
  }

  // Best-effort: try to detect which document IDs have generated doc pages.
  // We do not actually probe the network; instead we rely on a side index
  // emitted by the build, if present. Otherwise we just always show the PDF link.
  try {
    const indexResponse = await fetch("./assets/search/doc_pages.json", { cache: "no-store" });
    if (indexResponse.ok) {
      const ids = await indexResponse.json();
      if (Array.isArray(ids)) {
        docPageIds = new Set(ids);
      }
    }
  } catch (_error) {
    // No doc-page index available; that is fine.
  }

  status.textContent = `Keyword search ready · ${records.length} manifest records loaded.`;
  status.dataset.state = "ready";

  const total = records.length;
  summary.textContent = `Enter a keyword to search ${total} catalogued FOIA records.`;
  results.innerHTML =
    '<p class="empty-state">Try a document ID (e.g. <code>C09000008</code>), a year (e.g. <code>1994</code>), or a title keyword (e.g. <code>Talbott</code>, <code>NATO</code>).</p>';

  const runSearch = () => {
    const query = input.value.trim();
    if (!query) {
      summary.textContent = `Enter a keyword to search ${total} catalogued FOIA records.`;
      results.innerHTML =
        '<p class="empty-state">Try a document ID, a year, or a title keyword.</p>';
      return;
    }

    const tokens = tokenize(query);
    const scored = [];
    for (const record of records) {
      const score = scoreRecord(record, tokens);
      if (score > 0) {
        scored.push({ record, score });
      }
    }
    scored.sort((a, b) => b.score - a.score);

    if (!scored.length) {
      summary.textContent = `No matches for "${query}" in ${total} records.`;
      results.innerHTML =
        '<p class="empty-state">No matches. Try a broader term, a different year, or part of a title.</p>';
      return;
    }

    const visible = scored.slice(0, MAX_RESULTS);
    const more = scored.length - visible.length;
    const moreText = more > 0 ? ` (${more} additional matches not shown — refine your query)` : "";
    summary.textContent = `Showing ${visible.length} of ${scored.length} matches for "${query}"${moreText}.`;
    results.innerHTML = visible
      .map(({ record }) => renderResult(record, tokens, docPageIds.has(record.document_id)))
      .join("");
  };

  let pending = 0;
  const debouncedSearch = () => {
    window.cancelAnimationFrame(pending);
    pending = window.requestAnimationFrame(runSearch);
  };

  input.addEventListener("input", debouncedSearch);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    runSearch();
  });
});
