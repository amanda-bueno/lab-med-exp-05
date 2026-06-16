from __future__ import annotations

import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
DEFAULT_PORT = int(os.getenv("LAB05_DASHBOARD_PORT", "8050"))


def create_server() -> ThreadingHTTPServer:
    handler = partial(SimpleHTTPRequestHandler, directory=ROOT)
    errors: list[str] = []
    for port in range(DEFAULT_PORT, DEFAULT_PORT + 20):
        try:
            return ThreadingHTTPServer((HOST, port), handler)
        except OSError as exc:
            errors.append(f"{port}: {exc}")
    raise SystemExit("Could not start dashboard server. Tried ports:\n" + "\n".join(errors))


def main() -> None:
    server = create_server()
    host, port = server.server_address
    print(f"Dashboard running at http://{host}:{port}/dashboard/web/index.html")
    server.serve_forever()


if __name__ == "__main__":
    main()
