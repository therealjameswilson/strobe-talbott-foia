document.addEventListener("DOMContentLoaded", () => {
  const filterInput = document.getElementById("manifest-filter");
  const table = document.getElementById("manifest-table");
  const countEl = document.getElementById("manifest-count");

  if (!filterInput || !table) {
    return;
  }

  const rows = Array.from(table.tBodies[0].rows);
  const total = rows.length;

  const updateCount = (visible) => {
    if (!countEl) return;
    countEl.textContent = `Showing ${visible} of ${total} records`;
  };

  let pending = 0;

  const applyFilter = () => {
    const query = filterInput.value.trim().toLowerCase();
    let visible = 0;

    if (!query) {
      rows.forEach((row) => {
        row.hidden = false;
      });
      updateCount(total);
      return;
    }

    const tokens = query.split(/\s+/).filter(Boolean);
    rows.forEach((row) => {
      const haystack = row.textContent.toLowerCase();
      const match = tokens.every((token) => haystack.includes(token));
      row.hidden = !match;
      if (match) visible += 1;
    });
    updateCount(visible);
  };

  const debouncedFilter = () => {
    window.cancelAnimationFrame(pending);
    pending = window.requestAnimationFrame(applyFilter);
  };

  filterInput.addEventListener("input", debouncedFilter);
  updateCount(total);
});
