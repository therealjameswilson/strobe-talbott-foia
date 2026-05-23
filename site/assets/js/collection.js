const MANIFEST_URL = "./assets/search/manifest.json";
const PAGE_SIZE = 100;

function createTextDownload(filename, content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function preferredDownloadUrl(record) {
  return record.local_pdf_url || record.source_pdf_url || "";
}

function buildSearchText(record) {
  return [
    record.id,
    record.title,
    record.date,
    record.posted_date,
    record.release_status,
    record.raw_release_status,
    record.case_number,
    record.document_type,
    record.from_field,
    record.to_field,
    record.collection,
    record.snippet,
    record.has_local_pdf ? "local pdf available" : "source url only",
    record.has_text ? "extracted text available" : "metadata only"
  ].join(" ").toLowerCase();
}

function renderPdfLinks(record) {
  const links = [];
  if (record.local_pdf_url) {
    links.push(`<a class="inline-link" href="${escapeHtml(record.local_pdf_url)}" target="_blank" rel="noopener">Local PDF</a>`);
  }
  if (record.source_pdf_url) {
    links.push(`<a class="inline-link" href="${escapeHtml(record.source_pdf_url)}" target="_blank" rel="noopener">FOIA source</a>`);
  }
  return links.join('<span class="link-divider"> | </span>');
}

function renderRow(record, selected) {
  const summary = record.snippet || "Metadata harvested. Extracted text is not available in this build yet.";
  return `<tr class="document-row">
    <td class="checkbox-cell">
      <input
        class="doc-select"
        type="checkbox"
        aria-label="Select ${escapeHtml(record.id)}"
        data-doc-id="${escapeHtml(record.id)}"
        ${selected ? "checked" : ""}
      >
    </td>
    <td><a class="table-link" href="${escapeHtml(record.page_url)}">${escapeHtml(record.id)}</a></td>
    <td>${escapeHtml(record.date || "n/a")}</td>
    <td>
      <strong>${escapeHtml(record.title)}</strong>
      <p class="table-snippet">${escapeHtml(summary)}</p>
    </td>
    <td>${escapeHtml(record.release_status || "Unknown")}</td>
    <td>${renderPdfLinks(record)}</td>
    <td><a class="inline-link" href="${escapeHtml(record.page_url)}">Document page</a></td>
  </tr>`;
}

document.addEventListener("DOMContentLoaded", async () => {
  const filterInput = document.getElementById("collection-filter");
  const releaseFilter = document.getElementById("release-filter");
  const filterSummary = document.getElementById("filter-summary");
  const selectionSummary = document.getElementById("selection-summary");
  const selectVisibleButton = document.getElementById("select-visible");
  const clearSelectionButton = document.getElementById("clear-selection");
  const downloadSelectedButton = document.getElementById("download-selected");
  const exportSelectedUrlsButton = document.getElementById("export-selected-urls");
  const tableBody = document.getElementById("document-table-body");
  const prevPageButton = document.getElementById("prev-page");
  const nextPageButton = document.getElementById("next-page");
  const pageSummary = document.getElementById("page-summary");

  if (
    !filterInput ||
    !releaseFilter ||
    !filterSummary ||
    !selectionSummary ||
    !selectVisibleButton ||
    !clearSelectionButton ||
    !downloadSelectedButton ||
    !exportSelectedUrlsButton ||
    !tableBody ||
    !prevPageButton ||
    !nextPageButton ||
    !pageSummary
  ) {
    return;
  }

  let records = [];
  let filteredRecords = [];
  let currentPage = 1;
  const selectedById = new Map();

  function selectedRecords() {
    return [...selectedById.values()];
  }

  function updateSelectionSummary(message) {
    if (message) {
      selectionSummary.textContent = message;
      return;
    }
    const selectedCount = selectedById.size;
    selectionSummary.textContent = `${selectedCount} document${selectedCount === 1 ? "" : "s"} selected for batch actions.`;
  }

  function applyFilters() {
    const query = filterInput.value.trim().toLowerCase();
    const selectedStatus = releaseFilter.value;

    filteredRecords = records.filter((record) => {
      const matchesQuery = !query || record.searchText.includes(query);
      const matchesStatus = selectedStatus === "all" || record.release_status === selectedStatus;
      return matchesQuery && matchesStatus;
    });

    currentPage = 1;
    renderTable();
  }

  function renderTable() {
    const totalPages = Math.max(1, Math.ceil(filteredRecords.length / PAGE_SIZE));
    currentPage = Math.min(currentPage, totalPages);
    const startIndex = (currentPage - 1) * PAGE_SIZE;
    const pageRecords = filteredRecords.slice(startIndex, startIndex + PAGE_SIZE);

    if (!pageRecords.length) {
      tableBody.innerHTML = '<tr><td colspan="7">No records match the current filters.</td></tr>';
    } else {
      tableBody.innerHTML = pageRecords
        .map((record) => renderRow(record, selectedById.has(record.id)))
        .join("");
    }

    const shownStart = filteredRecords.length ? startIndex + 1 : 0;
    const shownEnd = Math.min(startIndex + PAGE_SIZE, filteredRecords.length);
    filterSummary.textContent = `Showing ${filteredRecords.length} of ${records.length} records.`;
    pageSummary.textContent = `Rows ${shownStart}-${shownEnd} of ${filteredRecords.length}`;
    prevPageButton.disabled = currentPage <= 1;
    nextPageButton.disabled = currentPage >= totalPages;
  }

  try {
    const response = await fetch(MANIFEST_URL);
    if (!response.ok) {
      throw new Error(`Unable to load ${MANIFEST_URL}`);
    }
    const payload = await response.json();
    records = (payload.records || []).map((record) => ({
      ...record,
      searchText: buildSearchText(record)
    }));
    filteredRecords = records;
    renderTable();
    updateSelectionSummary();
  } catch (error) {
    tableBody.innerHTML = '<tr><td colspan="7">The manifest export could not be loaded.</td></tr>';
    filterSummary.textContent = "Collection manifest unavailable.";
    pageSummary.textContent = "No records loaded.";
    console.error(error);
    return;
  }

  filterInput.addEventListener("input", applyFilters);
  releaseFilter.addEventListener("change", applyFilters);

  prevPageButton.addEventListener("click", () => {
    currentPage -= 1;
    renderTable();
  });

  nextPageButton.addEventListener("click", () => {
    currentPage += 1;
    renderTable();
  });

  tableBody.addEventListener("change", (event) => {
    const checkbox = event.target;
    if (!checkbox.classList || !checkbox.classList.contains("doc-select")) {
      return;
    }
    const record = records.find((item) => item.id === checkbox.dataset.docId);
    if (!record) {
      return;
    }
    if (checkbox.checked) {
      selectedById.set(record.id, record);
    } else {
      selectedById.delete(record.id);
    }
    updateSelectionSummary();
  });

  selectVisibleButton.addEventListener("click", () => {
    filteredRecords.forEach((record) => {
      selectedById.set(record.id, record);
    });
    renderTable();
    updateSelectionSummary();
  });

  clearSelectionButton.addEventListener("click", () => {
    selectedById.clear();
    renderTable();
    updateSelectionSummary();
  });

  downloadSelectedButton.addEventListener("click", () => {
    const selected = selectedRecords();
    if (!selected.length) {
      updateSelectionSummary("Select at least one document before starting a batch download.");
      return;
    }

    if (selected.length > 25) {
      const proceed = window.confirm(`Open ${selected.length} PDF links in separate tabs?`);
      if (!proceed) {
        return;
      }
    }

    selected.forEach((record, index) => {
      const url = preferredDownloadUrl(record);
      if (!url) {
        return;
      }
      window.setTimeout(() => {
        window.open(url, "_blank", "noopener");
      }, index * 120);
    });
    updateSelectionSummary(`Opened ${selected.length} PDF link${selected.length === 1 ? "" : "s"} in new tabs.`);
  });

  exportSelectedUrlsButton.addEventListener("click", () => {
    const selected = selectedRecords();
    if (!selected.length) {
      updateSelectionSummary("Select at least one document before exporting URLs.");
      return;
    }

    const lines = ["document_id\ttitle\tpreferred_download_url\tlocal_pdf_url\tsource_pdf_url\tsha256"];
    selected.forEach((record) => {
      lines.push([
        record.id || "",
        record.title || "",
        preferredDownloadUrl(record),
        record.local_pdf_url || "",
        record.source_pdf_url || "",
        record.pdf_sha256 || ""
      ].join("\t"));
    });

    createTextDownload("strobe-talbott-selected-pdfs.tsv", lines.join("\n"));
    updateSelectionSummary(`Exported ${selected.length} selected PDF URL${selected.length === 1 ? "" : "s"}.`);
  });
});
