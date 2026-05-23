from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE_DIR = PROJECT_ROOT / "site"
DEFAULT_PDF_DIR = PROJECT_ROOT / "data" / "pdfs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve the generated FOIA site and expose a local gitignored PDF cache under /pdfs/."
    )
    parser.add_argument("--site-dir", type=Path, default=DEFAULT_SITE_DIR, help="Generated site directory.")
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR, help="Local PDF cache directory.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind.")
    return parser.parse_args()


def safe_join(base_dir: Path, request_path: str) -> Path:
    parsed_path = urlparse(request_path).path
    path_parts = [
        part
        for part in Path(unquote(parsed_path)).parts
        if part not in ("", "/", ".", "..")
    ]
    return base_dir.joinpath(*path_parts)


def build_handler(site_dir: Path, pdf_dir: Path) -> type[SimpleHTTPRequestHandler]:
    class ResearchDeskHandler(SimpleHTTPRequestHandler):
        def translate_path(self, path: str) -> str:
            parsed_path = urlparse(path).path
            if parsed_path.startswith("/pdfs/"):
                relative_pdf_path = parsed_path.removeprefix("/pdfs/")
                return str(safe_join(pdf_dir, relative_pdf_path))

            target = safe_join(site_dir, parsed_path)
            if parsed_path in ("", "/"):
                target = site_dir / "index.html"
            elif target.is_dir():
                target = target / "index.html"
            return str(target)

    return ResearchDeskHandler


def main() -> int:
    args = parse_args()
    site_dir = args.site_dir.resolve()
    pdf_dir = args.pdf_dir.resolve()

    handler = build_handler(site_dir, pdf_dir)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {site_dir} on http://{args.host}:{args.port}")
    print(f"Local PDF cache available at http://{args.host}:{args.port}/pdfs/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
