#!/usr/bin/env python
"""Agnes OpenAI-compatible bridge (Path A) -- dependency-light, desktop-runnable.

Harness^2 talks to a model endpoint two ways:
  * OpenCode executor: a `provider/model` that OpenCode resolves (any OpenAI-compat base URL).
  * Codex executor:    a Responses-API endpoint (harness2-bridge / HARNESS2_CODEX_BASE_URL).

This bridge exposes a plain OpenAI chat-completions service that forwards to an
Agnes model backend, so either path can point Harness^2 at Agnes with zero
framework changes. Runs on Windows/macOS/Linux with only the Python stdlib.

Configuration (environment or .env loaded from CWD):
  AGNES_API_URL      Base URL of Agnes's OpenAI-compatible model service
                     e.g. https://agnes.example/v1   (or your Sapiens AI endpoint)
  AGNES_API_KEY      Bearer key for the Agnes backend (optional if it is open)
  AGNES_MODEL        Default model id to advertise / fallback when unspecified
  AGNES_PROXY_HOST   Bind host, default 127.0.0.1
  AGNES_PROXY_PORT   Bind port,  default 8620

Then in harness2's .env:
  # OpenCode executor (default): use an OpenAI-compatible provider that points here
  HARNESS2_SOLVER_MODEL=openai/agnes                 # provider = openai, model = agnes
  OPENAI_BASE_URL=http://127.0.0.1:8620/v1           # OpenCode provider override
  OPENAI_API_KEY=agnes-bridge
  HARNESS2_IMPROVER_MODEL=openai/agnes
  HARNESS2_JUDGE_MODEL=agnes
  # ... or the Codex executor:
  HARNESS2_CODEX_BASE_URL=http://127.0.0.1:8620/v1
  HARNESS2_CODEX_API_KEY=agnes-bridge

Usage:
  python -m agnes_bridge.agnes_openai_proxy          # from the harness2 repo root
  # or: python agnes_bridge/agnes_openai_proxy.py
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request
import urllib.error
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- config ----------------------------------------------------------------

def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# Minimal .env loader (KEY=VALUE), shell wins. Same semantics as harness2.config.
def _load_dotenv(path: str = ".env") -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh.read().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].lstrip()
                key, _, value = line.partition("=")
                key = key.strip()
                if not key:
                    continue
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                os.environ.setdefault(key, value)
    except OSError:
        pass


_load_dotenv()

API_URL = _env("AGNES_API_URL")
API_KEY = _env("AGNES_API_KEY")
DEFAULT_MODEL = _env("AGNES_MODEL", "agnes")
# Upstream auth header: "bearer" (default) or "x-api-key" for gateways
# that authenticate via the X-Api-Key header instead of Bearer.
# "bearer" (Authorization: Bearer <key>), "x-api-key" (X-Api-Key: <key>),
# or "raw" (Authorization: <key> without the Bearer prefix -- used by the
# Agnes China gateway apihub.agnes-ai.cn).
AUTH_HEADER = _env("AGNES_AUTH_HEADER", "bearer").strip().lower()
HOST = _env("AGNES_PROXY_HOST", "127.0.0.1")
PORT = int(_env("AGNES_PROXY_PORT", "8620"))
TIMEOUT = int(_env("AGNES_PROXY_TIMEOUT", "300"))


# ---- upstream call ----------------------------------------------------------

def _forward_chat(payload: dict) -> tuple[int, bytes, str]:
    """Forward an OpenAI chat-completions body to the Agnes backend."""
    if not API_URL:
        return (
            HTTPStatus.SERVICE_UNAVAILABLE.value,
            json.dumps(
                {
                    "error": {
                        "message": (
                            "AGNES_API_URL is not set. Point it at Agnes's "
                            "OpenAI-compatible model service."
                        )
                    }
                }
            ).encode(),
            "application/json",
        )

    url = API_URL.rstrip("/")
    if not url.endswith(("/chat/completions", "/responses")):
        url = url + "/chat/completions"

    body = dict(payload)
    body.setdefault("model", DEFAULT_MODEL)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    key = API_KEY or _env("AGNES_PROXY_KEY", "agnes-bridge")
    if AUTH_HEADER == "x-api-key":
        headers["X-Api-Key"] = key
    elif AUTH_HEADER == "raw":
        headers["Authorization"] = key
    else:
        headers["Authorization"] = f"Bearer {key}"

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "application/json")
    except urllib.error.URLError as e:
        return (
            HTTPStatus.BAD_GATEWAY.value,
            json.dumps({"error": {"message": f"upstream unreachable: {e.reason}"}}).encode(),
            "application/json",
        )


def _list_models() -> dict:
    return {
        "object": "list",
        "data": [
            {"id": DEFAULT_MODEL, "object": "model", "owned_by": "agnes-bridge"},
            {"id": "agnes", "object": "model", "owned_by": "agnes-bridge"},
        ],
    }


# ---- HTTP server -------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quiet default logging
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") in ("/v1/models", "/models", "/"):
            self._send(
                HTTPStatus.OK.value,
                json.dumps(_list_models()).encode(),
                "application/json",
            )
        else:
            self._send(
                HTTPStatus.NOT_FOUND.value,
                json.dumps({"error": "not found"}).encode(),
                "application/json",
            )

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._send(
                HTTPStatus.BAD_REQUEST.value,
                json.dumps({"error": "invalid json"}).encode(),
                "application/json",
            )
            return

        path = self.path.rstrip("/")
        if path in ("/v1/chat/completions", "/v1/responses", "/chat/completions", "/responses"):
            status, body, ctype = _forward_chat(payload)
            self._send(status, body, ctype)
        else:
            self._send(
                HTTPStatus.NOT_FOUND.value,
                json.dumps({"error": "not found"}).encode(),
                "application/json",
            )


def main() -> int:
    print(
        f"Agnes OpenAI-compatible bridge -> {API_URL or '(AGNES_API_URL not set)'}\n"
        f"  listening on http://{HOST}:{PORT}/v1\n"
        f"  advertise model: {DEFAULT_MODEL}\n"
        f"  upstream auth: {'X-Api-Key' if AUTH_HEADER == 'x-api-key' else ('Authorization: <key> (raw)' if AUTH_HEADER == 'raw' else 'Authorization: Bearer')}\n"
        f"  set in harness2 .env: OPENAI_BASE_URL / HARNESS2_CODEX_BASE_URL = "
        f"http://{HOST}:{PORT}/v1\n"
    )
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
