"""Temporary mock Continue serve API for smoke-testing continue_dev tool."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class _State:
    is_processing = False
    queue_length = 0
    history: list[dict] = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        print(fmt % args)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/state":
            self._json(404, {"error": "not found"})
            return
        self._json(
            200,
            {
                "isProcessing": _State.is_processing,
                "queueLength": _State.queue_length,
                "session": {"history": _State.history},
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/message":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        message = str(body.get("message") or "")
        _State.is_processing = False
        _State.queue_length = 0
        _State.history = [
            {"message": {"role": "user", "content": message}},
            {"message": {"role": "assistant", "content": f"MOCK OK: {message[:120]}"}},
        ]
        self._json(200, {"queued": True, "position": 1})


if __name__ == "__main__":
    host, port = "127.0.0.1", 65432
    print(f"mock Continue API on http://{host}:{port}")
    HTTPServer((host, port), Handler).serve_forever()
