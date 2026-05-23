const PAGEFIND_UI_SCRIPT = "./pagefind/pagefind-ui.js";
const PAGEFIND_UI_STYLE = "./pagefind/pagefind-ui.css";
const MANIFEST_JSON_URL = "./assets/search/manifest.json";
const MANIFEST_CSV_URL = "./data/manifest.csv";
const MAX_RESULTS = 50;

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

function loadStylesheet(href) {
  const existing = document.querySelector(`link[href="${href}"]`);
  if (existing) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

async function tryPagefind(status) {
  loadStylesheet(PAGEFIND_UI_STYLE);
  await loadScript(PAGEFIND_UI_SCRIPT);
  if (!window.PagefindUI) {
    throw new Error("Pagefind UI loaded without exposing PagefindUI.");
  }

  new window.PagefindUI({
    element: "#search-interface",
    showSubResults: true,
    showImages: false,
    excerptLength: 40,
    pageSize: 10
  });
  status.textContent = "Pagefind full-text search ready.";
  status.dataset.state = "ready";
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
    } else if (ch !== "\r") {
      field += ch;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

function normalizeRecord(record) {
  const id = record.id || record.document_id || "";
  const sourcePdfUrl = record.source_pdf_url || record.pdf_url || "";
  return {
    id,
    document_id: id,
    date: record.date || "",
    title: record.title || "Untitled record",
    source_pdf_url: sourcePdfUrl,
    pdf_url: sourcePdfUrl,
    release_status: record.release_status || "",
    description: record.description || record.snippet || "",
    page_url: record.page_url || (id ? `./docs/${encodeURIComponent(id)}.html` : "")
  };
}

function recordsFromCsvText(text) {
  const rows = parseCsv(text).filter((r) => r.length && r.some((cell) => cell !== ""));
  if (!rows.length) {
    return [];
  }
  const header = rows.shift().map((h) => h.trim().toLowerCase());
  const idx = (name) => header.indexOf(name);
  return rows
    .map((cells) =>
      normalizeRecord({
        document_id: cells[idx("document_id")] || cells[idx("id")] || "",
        date: cells[idx("date")] || "",
        title: cells[idx("title")] || "",
        pdf_url: cells[idx("pdf_url")] || cells[idx("source_pdf_url")] || "",
        release_status: cells[idx("release_status")] || "",
        description: idx("description") >= 0 ? cells[idx("description")] || "" : ""
      })
    )
    .filter((r) => r.document_id || r.pdf_url);
}

async function loadRecords() {
  try {
    const response = await fetch(MANIFEST_JSON_URL, { cache: "no-store" });
    if (response.ok) {
      const payload = await response.json();
      const records = Array.isArray(payload) ? payload : payload.records || [];
      return records.map(normalizeRecord);
    }
  } catch (error) {
    console.warn("Falling back to CSV manifest:", error);
  }

  const csvResponse = await fetch(MANIFEST_CSV_URL, { cache: "no-store" });
  if (!csvResponse.ok) {
    throw new Error(`Unable to load manifest at ${MANIFEST_CSV_URL}`);
  }
  return recordsFromCsvText(await csvResponse.text());
}

function tokenize(query) {
  return query
    .toLowerCase()
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean);
}

function highlight(text, tokens) {
  if (!text) {
    return "";
  }
  let safe = escapeHtml(text);
  if (!tokens.length) {
    return safe;
  }
  const escapedTokens = tokens
    .map((token) => token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .filter(Boolean);
  if (!escapedTokens.length) {
    return safe;
  }
  const re = new RegExp(`(${escapedTokens.join("|")})`, "gi");
  return safe.replace(re, "<mark>$1</mark>");
}

function scoreRecord(record, tokens) {
  if (!tokens.length) {
    return 0;
  }
  const fields = {
    id: record.document_id.toLowerCase(),
    date: record.date.toLowerCase(),
    title: record.title.toLowerCase(),
    url: record.pdf_url.toLowerCase(),
    status: record.release_status.toLowerCase(),
    description: record.description.toLowerCase()
  };

  let score = 0;
  for (const token of tokens) {
    let tokenScore = 0;
    if (fields.id.includes(token)) tokenScore += 6;
    if (fields.title.includes(token)) tokenScore += 4;
    if (fields.description.includes(token)) tokenScore += 3;
    if (fields.date.includes(token)) tokenScore += 2;
    if (fields.status.includes(token)) tokenScore += 2;
    if (fields.url.includes(token)) tokenScore += 1;
    if (tokenScore === 0) {
      return 0;
    }
    score += tokenScore;
  }
  return score;
}

function renderResult(record, tokens) {
  const titleHtml = highlight(record.title, tokens);
  const idHtml = highlight(record.document_id || "-", tokens);
  const dateHtml = highlight(record.date || "Unknown date", tokens);
  const statusHtml = highlight(record.release_status || "Unknown status", tokens);
  const descriptionHtml = record.description
    ? `<p class="result-description">${highlight(record.description, tokens)}</p>`
    : "";
  return `
    <article class="result-card">
      <p class="result-label">Document ID ${idHtml}</p>
      <h3><a href="${escapeHtml(record.page_url)}">${titleHtml}</a></h3>
      <p class="result-meta">${dateHtml} | ${statusHtml}</p>
      ${descriptionHtml}
      <p><a class="inline-link" href="${escapeHtml(record.page_url)}">Open document page</a> | <a class="inline-link" href="${escapeHtml(record.pdf_url)}" rel="noopener" target="_blank">Direct PDF link</a></p>
    </article>
  `;
}

async function renderManifestFallback(status, container) {
  container.innerHTML = `
    <form id="keyword-search-form" class="search-form" role="search" onsubmit="return false;">
      <label for="keyword-query">Search by document ID, date, title, status, source URL, or extracted-text snippet</label>
      <div class="search-form-row">
        <input id="keyword-query" name="query" type="search" placeholder="e.g. Talbott, NATO, Moscow, 1996, C06697823" autocomplete="off" autofocus>
        <button type="submit">Search</button>
      </div>
      <p id="search-summary" class="result-meta">Loading manifest...</p>
      <div id="keyword-results" class="results-list">
        <p class="empty-state">Loading manifest records...</p>
      </div>
    </form>
  `;

  const form = document.getElementById("keyword-search-form");
  const input = document.getElementById("keyword-query");
  const summary = document.getElementById("search-summary");
  const results = document.getElementById("keyword-results");

  let records = [];
  try {
    records = await loadRecords();
  } catch (error) {
    status.textContent = "Unable to load the FOIA manifest for keyword search.";
    status.dataset.state = "error";
    summary.textContent = "Manifest data unavailable.";
    results.innerHTML = '<p class="empty-state">Could not load the generated manifest export.</p>';
    console.error(error);
    return;
  }

  status.textContent = `Manifest fallback search ready | ${records.length} records loaded.`;
  status.dataset.state = "ready";
  summary.textContent = `Enter a keyword to search ${records.length} catalogued FOIA records.`;
  results.innerHTML = '<p class="empty-state">Try a document ID, year, title keyword, release status, or diplomatic subject.</p>';

  const runSearch = () => {
    const query = input.value.trim();
    if (!query) {
      summary.textContent = `Enter a keyword to search ${records.length} catalogued FOIA records.`;
      results.innerHTML = '<p class="empty-state">Try a document ID, year, title keyword, release status, or diplomatic subject.</p>';
      return;
    }

    const tokens = tokenize(query);
    const scored = records
      .map((record) => ({ record, score: scoreRecord(record, tokens) }))
      .filter((item) => item.score > 0)
      .sort((left, right) => right.score - left.score);

    if (!scored.length) {
      summary.textContent = `No matches for "${query}" in ${records.length} records.`;
      results.innerHTML = '<p class="empty-state">No matches. Try a broader term, a different year, or part of a title.</p>';
      return;
    }

    const visible = scored.slice(0, MAX_RESULTS);
    const more = scored.length - visible.length;
    const moreText = more > 0 ? ` (${more} additional matches not shown; refine your query)` : "";
    summary.textContent = `Showing ${visible.length} of ${scored.length} matches for "${query}"${moreText}.`;
    results.innerHTML = visible.map(({ record }) => renderResult(record, tokens)).join("");
  };

  let pending = 0;
  input.addEventListener("input", () => {
    window.cancelAnimationFrame(pending);
    pending = window.requestAnimationFrame(runSearch);
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    runSearch();
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  const status = document.getElementById("pagefind-status");
  const container = document.getElementById("search-interface");
  if (!status || !container) {
    return;
  }

  try {
    await tryPagefind(status);
  } catch (error) {
    console.warn("Pagefind unavailable; using manifest fallback search.", error);
    await renderManifestFallback(status, container);
  }
});
