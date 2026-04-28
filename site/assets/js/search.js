function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Unable to load ${src}`));
    document.head.appendChild(script);
  });
}

function loadStylesheet(href) {
  return new Promise((resolve, reject) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.onload = resolve;
    link.onerror = () => reject(new Error(`Unable to load ${href}`));
    document.head.appendChild(link);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  const status = document.getElementById("pagefind-status");
  const container = document.getElementById("search-interface");

  if (!status || !container) {
    return;
  }

  try {
    await Promise.all([
      loadStylesheet("./pagefind/pagefind-ui.css"),
      loadScript("./pagefind/pagefind-ui.js")
    ]);

    // PagefindUI is injected by the generated Pagefind asset bundle.
    // eslint-disable-next-line no-undef
    new PagefindUI({
      element: "#search-interface",
      showSubResults: true,
      resetStyles: false,
      translations: {
        placeholder: "Search sample FOIA documents"
      }
    });

    status.textContent = "Keyword search index loaded.";
    status.dataset.state = "ready";
  } catch (error) {
    status.textContent =
      "Pagefind assets are not available yet. Run `npm run build:search` after generating the site.";
    status.dataset.state = "warning";
    container.innerHTML =
      "<p class=\"empty-state\">The keyword search UI will appear here once Pagefind finishes indexing the generated site.</p>";
    console.warn(error);
  }
});
