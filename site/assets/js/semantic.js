const CHUNKS_URL = "./assets/search/chunks.json";

function tokenize(text) {
  return (text.toLowerCase().match(/[a-z0-9']+/g) || []);
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function uniqueTokens(tokens) {
  return [...new Set(tokens)];
}

function keywordOverlapScore(queryTokens, chunkKeywords) {
  const querySet = uniqueTokens(queryTokens);
  if (!querySet.length) {
    return 0;
  }

  const keywordSet = new Set(chunkKeywords);
  let matches = 0;
  for (const token of querySet) {
    if (keywordSet.has(token)) {
      matches += 1;
    }
  }
  return matches / querySet.length;
}

function embeddingPlaceholderScore() {
  // Future work: replace this with a real vector similarity score.
  return 0;
}

function combinedScore(queryTokens, chunk) {
  const keywordScore = keywordOverlapScore(queryTokens, chunk.keywords || []);
  const embeddingScore = embeddingPlaceholderScore(queryTokens, chunk);
  return {
    total: keywordScore * 0.9 + embeddingScore * 0.1,
    keywordScore,
    embeddingScore
  };
}

function formatScore(score) {
  return score.toFixed(2);
}

function buildSnippet(text, limit = 220) {
  const compact = text.replace(/\s+/g, " ").trim();
  if (compact.length <= limit) {
    return compact;
  }
  return `${compact.slice(0, limit - 1).trimEnd()}…`;
}

function renderResult(result) {
  const score = result.score;
  return `
    <article class="result-card">
      <p class="result-label">Document ID ${escapeHtml(result.doc_id)} · chunk ${escapeHtml(String(result.chunk_index))}</p>
      <h3><a href="${escapeHtml(result.page_url)}">${escapeHtml(result.title)}</a></h3>
      <p class="result-meta">${escapeHtml(result.date)} · ${escapeHtml(result.release_status)}</p>
      <p class="result-snippet">${escapeHtml(buildSnippet(result.text))}</p>
      <p><a class="inline-link" href="${escapeHtml(result.page_url)}">Open document page</a> · <a class="inline-link" href="${escapeHtml(result.source_pdf_url)}">Source PDF link</a></p>
      <p class="score-badge">Prototype score ${formatScore(score.total)} · keyword ${formatScore(score.keywordScore)} · embedding placeholder ${formatScore(score.embeddingScore)}</p>
    </article>
  `;
}

document.addEventListener("DOMContentLoaded", async () => {
  const form = document.getElementById("semantic-search-form");
  const input = document.getElementById("semantic-query");
  const status = document.getElementById("semantic-status");
  const results = document.getElementById("semantic-results");
  const summary = document.getElementById("semantic-summary");

  if (!form || !input || !status || !results || !summary) {
    return;
  }

  let chunks = [];

  try {
    const response = await fetch(CHUNKS_URL);
    if (!response.ok) {
      throw new Error(`Failed to load ${CHUNKS_URL}`);
    }

    const payload = await response.json();
    chunks = Array.isArray(payload.chunks) ? payload.chunks : [];
    status.textContent = `Loaded ${chunks.length} prototype chunks.`;
    status.dataset.state = "ready";
  } catch (error) {
    status.textContent = "Chunk data is missing. Run the chunk build step to enable semantic search.";
    status.dataset.state = "error";
    summary.textContent = "Chunk data is unavailable.";
    results.innerHTML =
      "<p class=\"empty-state\">The semantic prototype needs `site/assets/search/chunks.json` before it can run.</p>";
    console.error(error);
    return;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    const query = input.value.trim();
    if (!query) {
      summary.textContent = "Enter a query to rank the sample chunk index.";
      results.innerHTML =
        "<p class=\"empty-state\">Enter a query to search the sample chunk index.</p>";
      return;
    }

    const queryTokens = tokenize(query);
    const ranked = chunks
      .map((chunk) => ({
        ...chunk,
        score: combinedScore(queryTokens, chunk)
      }))
      .filter((chunk) => chunk.score.total > 0)
      .sort((left, right) => right.score.total - left.score.total)
      .slice(0, 10);

    if (!ranked.length) {
      summary.textContent = `No matching chunks found for "${query}".`;
      results.innerHTML =
        "<p class=\"empty-state\">No prototype matches were found. Try broader historical terms or a different subject phrase.</p>";
      return;
    }

    summary.textContent = `Showing the top ${ranked.length} matching chunks for "${query}".`;
    results.innerHTML = ranked.map(renderResult).join("");
  });
});
