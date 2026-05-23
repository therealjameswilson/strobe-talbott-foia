const CHUNKS_URL = "./assets/search/chunks.json";
const INDEX_URL = "./assets/search/semantic_index.json";

function tokenize(text) {
  return (text.toLowerCase().match(/[a-z0-9']+/g) || []);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function uniqueTokens(tokens) {
  return [...new Set(tokens)];
}

function stableHash(token) {
  let value = 0;
  for (const character of token) {
    value = ((value << 5) - value + character.charCodeAt(0)) >>> 0;
  }
  return value;
}

function vectorToMap(vector) {
  const map = new Map();
  for (const [index, weight] of vector || []) {
    map.set(index, weight);
  }
  return map;
}

function queryVector(tokens, tokenIdf, dimensions) {
  const counts = new Map();
  tokens.forEach((token) => {
    counts.set(token, (counts.get(token) || 0) + 1);
  });

  const weights = new Map();
  counts.forEach((count, token) => {
    const index = stableHash(token) % dimensions;
    const idf = tokenIdf[token] || 1;
    weights.set(index, (weights.get(index) || 0) + (1 + Math.log(count)) * idf);
  });

  let norm = 0;
  weights.forEach((weight) => {
    norm += weight * weight;
  });
  norm = Math.sqrt(norm);
  if (!norm) {
    return new Map();
  }

  weights.forEach((weight, index) => {
    weights.set(index, weight / norm);
  });
  return weights;
}

function cosineScore(left, right) {
  let score = 0;
  left.forEach((weight, index) => {
    score += weight * (right.get(index) || 0);
  });
  return score;
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

function combinedScore(queryTokens, queryVectorMap, chunk, vectorMap) {
  const keywordScore = keywordOverlapScore(queryTokens, chunk.keywords || []);
  const vectorScore = cosineScore(queryVectorMap, vectorMap || new Map());
  return {
    total: keywordScore * 0.35 + vectorScore * 0.65,
    keywordScore,
    vectorScore
  };
}

function formatScore(score) {
  return score.toFixed(2);
}

function buildSnippet(text, limit = 220) {
  const compact = String(text || "").replace(/\s+/g, " ").trim();
  if (compact.length <= limit) {
    return compact;
  }
  return `${compact.slice(0, limit - 1).trimEnd()}...`;
}

function renderResult(result) {
  const score = result.score;
  return `
    <article class="result-card">
      <p class="result-label">Document ID ${escapeHtml(result.doc_id)} | chunk ${escapeHtml(String(result.chunk_index))}</p>
      <h3><a href="${escapeHtml(result.page_url)}">${escapeHtml(result.title)}</a></h3>
      <p class="result-meta">${escapeHtml(result.date)} | ${escapeHtml(result.release_status)}</p>
      <p class="result-snippet">${escapeHtml(buildSnippet(result.text))}</p>
      <p><a class="inline-link" href="${escapeHtml(result.page_url)}">Open document page</a> | <a class="inline-link" href="${escapeHtml(result.source_pdf_url)}">Source PDF link</a></p>
      <p class="score-badge">Score ${formatScore(score.total)} | vector ${formatScore(score.vectorScore)} | keyword ${formatScore(score.keywordScore)}</p>
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
  let tokenIdf = {};
  let dimensions = 512;
  const vectorsByChunk = new Map();

  try {
    const [chunksResponse, indexResponse] = await Promise.all([
      fetch(CHUNKS_URL),
      fetch(INDEX_URL)
    ]);
    if (!chunksResponse.ok) {
      throw new Error(`Failed to load ${CHUNKS_URL}`);
    }
    if (!indexResponse.ok) {
      throw new Error(`Failed to load ${INDEX_URL}`);
    }

    const chunksPayload = await chunksResponse.json();
    const indexPayload = await indexResponse.json();
    chunks = Array.isArray(chunksPayload.chunks) ? chunksPayload.chunks : [];
    tokenIdf = indexPayload.token_idf || {};
    dimensions = indexPayload.dimensions || dimensions;
    (indexPayload.chunks || []).forEach((row) => {
      vectorsByChunk.set(row.chunk_id, vectorToMap(row.vector));
    });

    status.textContent = `Loaded ${chunks.length} chunks with local vector scoring.`;
    status.dataset.state = "ready";
  } catch (error) {
    status.textContent = "Semantic index data is missing. Run the chunk and semantic index build steps.";
    status.dataset.state = "error";
    summary.textContent = "Semantic index data is unavailable.";
    results.innerHTML =
      "<p class=\"empty-state\">The semantic prototype needs chunks.json and semantic_index.json before it can run.</p>";
    console.error(error);
    return;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    const query = input.value.trim();
    if (!query) {
      summary.textContent = "Enter a query to rank the extracted chunk index.";
      results.innerHTML =
        "<p class=\"empty-state\">Enter a query to search the extracted chunk index.</p>";
      return;
    }

    const queryTokens = tokenize(query);
    const queryVectorMap = queryVector(queryTokens, tokenIdf, dimensions);
    const ranked = chunks
      .map((chunk) => ({
        ...chunk,
        score: combinedScore(queryTokens, queryVectorMap, chunk, vectorsByChunk.get(chunk.chunk_id))
      }))
      .filter((chunk) => chunk.score.total > 0)
      .sort((left, right) => right.score.total - left.score.total)
      .slice(0, 10);

    if (!ranked.length) {
      summary.textContent = `No matching chunks found for "${query}".`;
      results.innerHTML =
        "<p class=\"empty-state\">No matches were found. Try broader historical terms or a different subject phrase.</p>";
      return;
    }

    summary.textContent = `Showing the top ${ranked.length} matching chunks for "${query}".`;
    results.innerHTML = ranked.map(renderResult).join("");
  });
});
