"""Static server for dashboard/dist: `python -m http.server` plus caching headers.

Framework names every asset by its content (`heart.485e076b.json`) or package version
(`_npm/d3@7.9.0/...`), so those can be cached for good. Pages keep their names across builds, so
browsers must check them each time (`no-cache` revalidates; an unchanged page costs a 304).
Without these headers a browser may show a page from before the last rebuild, whose assets no
longer exist, and the dashboard looks broken until the cache is cleared.

It also answers /coach.json from the coach's journal on each request, so the Coach page is current
without rebuilding the site. That needs the project's environment (npm runs this with ../.venv).

    python3 scripts/serve.py [--bind 127.0.0.1] [--port 3001] [--directory dist]
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import re
import sys
from pathlib import Path

DIST = Path(__file__).resolve().parents[1] / "dist"
HASHED = re.compile(r"\.[0-9a-f]{8}\.[A-Za-z0-9]+$")


def coach_json() -> tuple[int, bytes]:
    """The Coach page's live data, or a 503 with the reason."""
    try:
        src = Path(__file__).resolve().parents[2] / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from apple_health.coach import live

        return 200, json.dumps(live.build(), default=str, ensure_ascii=False).encode()
    except Exception as e:  # the page falls back to the build-time snapshot
        return 503, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode()


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/coach.json":
            status, body = coach_json()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def end_headers(self) -> None:
        path = self.path.split("?", 1)[0]
        if path.startswith("/_npm/") or HASHED.search(path):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=3001)
    p.add_argument("--directory", default=str(DIST))
    a = p.parse_args(argv)
    handler = functools.partial(Handler, directory=a.directory)
    with http.server.ThreadingHTTPServer((a.bind, a.port), handler) as httpd:
        print(f"Serving {a.directory} on http://{a.bind}:{a.port}/", flush=True)
        with contextlib.suppress(KeyboardInterrupt):
            httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
