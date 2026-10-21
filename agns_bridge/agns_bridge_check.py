"""Second-window probe for the local Agnes OpenAI-compatible bridge.

Usage (from the harness2 repo root, or anywhere the tree is importable):
    python agnes_bridge/agns_bridge_check.py [wait_seconds]

It reads .agns_bridge.env, then polls the local bridge (default
http://127.0.0.1:8620/v1) with a tiny chat request until it answers 200
(bridge not up yet -> retry) or returns an HTTP error (upstream problem ->
stop and show diagnostics). On success it prints the exact variable block
to run harness2 against the bridge.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, ".agns_bridge.env")


def _load_env_file(path: str) -> dict:
    data = {}
    if not os.path.exists(path):
        return data
    with open(path, encoding="utf-8") as fh:
        for raw in fh.read().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip()
    return data


def main() -> int:
    wait_s = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    cfg = _load_env_file(ENV_FILE)
    host = cfg.get("AGNES_PROXY_HOST") or "127.0.0.1"
    port = cfg.get("AGNES_PROXY_PORT") or "8620"
    model = cfg.get("AGNES_MODEL") or "agnes-3.0-flash"
    base = "http://%s:%s/v1" % (host, port)
    upstream = cfg.get("AGNES_API_URL") or "(AGNES_API_URL unset)"
    auth = cfg.get("AGNES_AUTH_HEADER") or "bearer"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 8,
    }
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "agnes-bridge"},
    )

    print("[check] local bridge : %s" % base)
    print("[check] upstream     : %s  (auth header: %s)" % (upstream, auth))
    deadline = time.time() + wait_s
    while True:
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                answer = data["choices"][0]["message"]["content"]
            print("")
            print("AGNES LINK OK  ->  model answered %r  usage=%s" % (answer, data.get("usage")))
            print("")
            print("To run Harness^2 against Agnes, in a NEW shell (PowerShell):")
            print('  $env:OPENAI_BASE_URL="%s"' % base)
            print('  $env:OPENAI_API_KEY="agnes-bridge"')
            print('  $env:HARNESS2_SOLVER_MODEL="openai/%s"' % model)
            print('  $env:HARNESS2_IMPROVER_MODEL="openai/%s"' % model)
            print('  $env:HARNESS2_JUDGE_MODEL="%s"' % model)
            print("  python -m harness2.cli.run_sweep --bench lab --substrate oc --k 1 --mode parallel")
            print("")
            print("cmd.exe equivalent:  set OPENAI_BASE_URL=%s && set OPENAI_API_KEY=agnes-bridge ..." % base)
            return 0
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            print("")
            print("[check] bridge answered HTTP %d -> upstream problem, not retrying:" % e.code)
            print("  " + body[:400])
            if e.code == 503:
                print("  AGNES_API_URL missing in .agns_bridge.env; set it to your Agnes endpoint.")
            elif e.code in (401, 403):
                print("  Auth rejected. Check AGNES_API_KEY and AGNES_AUTH_HEADER.")
                print("  (apihub.agnes-ai.cn China gateway uses 'raw'; international uses 'bearer'.)")
            elif e.code in (502, 504):
                print("  Upstream unreachable; check AGNES_API_URL / network.")
            return 1
        except Exception as e:
            if time.time() >= deadline:
                print("")
                print("[check] bridge not reachable after %.0fs (%s)." % (wait_s, type(e).__name__))
                print("  Start it first:  python -m agnes_bridge.agnes_openai_proxy")
                return 1
            print("[check] bridge not up yet (%s); retrying..." % type(e).__name__)
            time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
