"""Harness2 MCP server: exposes the harness2 CLI suite as Agnes Code extension tools.

Stdio transport, newline-delimited JSON-RPC (MCP protocol). Zero third-party
dependencies: runs with the same Python that has harness2 installed.

Launch (stdio, what the extension config uses):

    python -m mcp_server.harness2_mcp

Tools exposed (one per CLI entry point in pyproject.toml, plus bridge helpers):

    harness2_setup    -> harness2-setup  <bench>
    harness2_check    -> harness2-check  --bench <bench>
    harness2_run      -> harness2        --bench <bench> ... (costs money when real)
    harness2_judge    -> harness2-judge  --bench <bench> ...
    harness2_report   -> harness2-report --bench <bench> ...
    harness2_demo     -> harness2-demo   (deterministic, zero credentials)
    harness2_agns_demo-> harness2-agns-demo (Path B: Agnes as substrate)
    agnes_bridge_status / agnes_bridge_start (Path A: OpenAI-compatible proxy on 127.0.0.1:8620)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("HARNESS2_REPO", Path(__file__).resolve().parents[1]))

# ---------------------------------------------------------------- tool registry

_CLI_MAP = {
    "harness2": "harness2.cli.run_sweep",
    "harness2-judge": "harness2.cli.judge",
    "harness2-report": "harness2.cli.report",
    "harness2-setup": "harness2.cli.setup",
    "harness2-check": "harness2.cli.check",
    "harness2-demo": "harness2.cli.demo",
    "harness2-agns-demo": "harness2.cli.agns_demo",
}

_BENCHES = ["jb", "lab", "wb"]
_SUBSETS = ["office", "web", "code"]
_SUBSTRATES = ["oc", "cx", "ags"]


def _cell_props() -> dict[str, Any]:
    p: dict[str, Any] = {
        "bench": {"type": "string", "enum": _BENCHES, "description": "Benchmark selector"},
        "substrate": {
            "type": "string",
            "enum": _SUBSTRATES,
            "default": "oc",
            "description": "Executor: oc=opencode, cx=codex, ags=agnes (demo paths)",
        },
    }
    return p


def _identity_props() -> dict[str, Any]:
    return {
        "k": {"type": "integer", "minimum": 1, "default": 1, "description": "Recursion budget R=4k/P=3k"},
        "mode": {
            "type": "string",
            "default": "parallel",
            "description": "parallel | sequential (or comma list)",
        },
        "seed": {"type": "integer", "description": "Optional stream-order seed"},
    }


def _run_control_props() -> dict[str, Any]:
    return {
        "split": {"type": "string", "enum": ["all", "train", "test"], "default": "all"},
        "max_tasks": {"type": "integer", "description": "Per-domain cap"},
        "only_domains": {"type": "string", "description": "Comma list of domains"},
        "workers": {"type": "integer", "default": 1},
        "dry_run": {"type": "boolean", "default": False, "description": "Preview stream, no model calls"},
    }


def _flag_args(prefix: str, values: dict[str, Any], mapping: dict[str, str]) -> list[str]:
    """Convert camelCase tool values into CLI flags via {flag: value_key} mapping."""
    args: list[str] = []
    for flag, key in mapping.items():
        val = values.get(key)
        if val is None:
            continue
        args.append(f"{flag}={str(val)}")
    return args


def _cli_args(tool: str, args: dict[str, Any]) -> list[str]:
    if tool == "harness2-setup":
        out = [str(args.get("bench", "jb"))]
        if args.get("subset"):
            out += ["--subset", str(args["subset"])]
        if args.get("substrate"):
            out += ["--substrate", str(args["substrate"])]
        if args.get("dry_run"):
            out.append("--dry-run")
        return out
    if tool == "harness2-check":
        out = ["--bench", str(args.get("bench", "jb"))]
        if args.get("subset"):
            out += ["--subset", str(args["subset"])]
        if args.get("substrate"):
            out += ["--substrate", str(args["substrate"])]
        return out
    if tool == "harness2-run":
        out = ["--bench", str(args.get("bench", "jb"))]
        if args.get("subset"):
            out += ["--subset", str(args["subset"])]
        out += _flag_args("run", args, {
            "--substrate": "substrate", "--k": "k", "--seed": "seed",
            "--modes": "mode", "--split": "split", "--max-tasks": "max_tasks",
            "--only-domains": "only_domains", "--workers": "workers",
        })
        out = [x for x in out if not (x.startswith("--") and x.endswith("=") and x == "--" + x[2:])]
        if args.get("dry_run"):
            out.append("--dry-run")
        # argparse accepts both "--k=2" and "--k 2"; keep the = form, drop empties
        return [x for x in out if "=" in x or x in ("--dry-run",) or x.startswith("--bench") or x in _BENCHES or x.startswith("--subset") or x in _SUBSETS]
    if tool in ("harness2-judge", "harness2-report"):
        out = ["--bench", str(args.get("bench", "jb"))]
        if args.get("subset"):
            out += ["--subset", str(args["subset"])]
        out += _flag_args(tool, args, {
            "--substrate": "substrate", "--k": "k", "--seed": "seed", "--modes": "mode",
        })
        return out
    if tool == "harness2-demo":
        out = ["--output", "runs/demo", "--k", str(args.get("k", 2))]
        return out
    if tool == "harness2-agns-demo":
        out = ["--k", str(args.get("k", 2)), "--mode", str(args.get("mode", "both"))]
        return out
    raise ValueError(f"unknown tool {tool}")


def _run_cli(tool: str, args: dict[str, Any], timeout_s: int) -> tuple[bool, str]:
    module = _CLI_MAP[tool]
    cmd = [sys.executable, "-m", module, *(_cli_args(tool, args) if tool != "harness2-demo" else _cli_args(tool, args))]
    # harness2-setup takes the benchmark as a positional, others use flags: handled in _cli_args
    try:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, timeout=timeout_s,
            capture_output=True, text=True,
            env={**os.environ, "HARNESS2_RUNS_DIR": os.environ.get("HARNESS2_RUNS_DIR", str(REPO_ROOT / "runs"))},
        )
        out = (proc.stdout or "") + (f"\n[stderr]\n{proc.stderr}" if proc.stderr else "")
        ok = proc.returncode == 0
        return ok, (out or "(no output)") + f"\n[exit={proc.returncode}]"
    except subprocess.TimeoutExpired:
        return False, f"TIMED OUT after {timeout_s}s: {tool} {json.dumps(args)}"
    except FileNotFoundError as exc:
        return False, f"spawn failed: {exc}"


# ---------------------------------------------------------------- requeue flag protocol (B)

# The harness2-loop hooks plugin (no headless CLI exists on desktop Agnes
# Code) records trigger flags here; MCP tools drain it instead of spawning.
#
# Two possible locations, checked in order:
#   1. GLOBAL plugin:  ~/.Agnes Code/plugins/harness2-loop/.state/pending_re.json
#      (set up once, applies to ANY project; the preferred location)
#   2. PROJECT plugin: <REPO_ROOT>/.Agnes Code/plugins/harness2-loop/.state/…
#      (legacy per-project copy; kept for backward compatibility)
_REQUEUE_REL = os.path.join(".Agnes Code", "plugins", "harness2-loop", ".state", "pending_re.json")


def _requeue_paths() -> list[Path]:
    global_root = Path.home() / ".Agnes Code" / "plugins" / "harness2-loop"
    project_root = REPO_ROOT / ".Agnes Code" / "plugins" / "harness2-loop"
    return [global_root / ".state" / "pending_re.json", project_root / ".state" / "pending_re.json"]


def _requeue_path() -> Path:
    """Return the FIRST path that has a pending flag (global wins)."""
    for p in _requeue_paths():
        if p.exists():
            return p
    return _requeue_paths()[0]


def _requeue_read() -> dict | None:
    for p in _requeue_paths():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def _requeue_consume() -> bool:
    p = _requeue_path()
    try:
        p.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _requeue_args_from_flag(flag: dict, explicit: dict[str, Any]) -> dict[str, Any]:
    """Merge flag params into explicit args; explicit wins (agent can override)."""
    merged = dict(explicit)
    fp = flag.get("params") or {}
    for k, v in fp.items():
        merged.setdefault(k, v)
    runs_ns = flag.get("runs_namespace")
    if runs_ns:
        os.environ.setdefault("HARNESS2_RUNS_NAMESPACE", str(runs_ns))
    runs_dir = flag.get("runs_dir")
    if runs_dir:
        os.environ.setdefault("HARNESS2_RUNS_DIR", runs_dir)
    bench = fp.get("bench")
    if bench and "bench" not in explicit:
        merged["bench"] = bench
    return merged


def _drain_requeue(args: dict[str, Any]) -> tuple[bool, str]:
    flag = _requeue_read()
    if not flag:
        return True, "requeue empty: no pending trigger flag"
    bench = str((flag.get("params") or {}).get("bench", "demo"))
    bench_map = {"demo": "harness2-demo", "ags-demo": "harness2-agns-demo",
                 "jb": "harness2", "lab": "harness2", "wb": "harness2"}
    tool = bench_map.get(bench, "harness2-run")
    if tool == "harness2-demo":
        k = int((flag.get("params") or {}).get("k", 2))
        ok, text = _run_cli("harness2-demo", {"k": k, "output": "runs/demo",
                                                "timeout_s": int(args.get("timeout_s", 600))}, int(args.get("timeout_s", 600)))
    elif tool == "harness2-agns-demo":
        fp = flag.get("params") or {}
        ok, text = _run_cli("harness2-agns-demo", {"k": int(fp.get("k", 2)),
                                                    "mode": str(fp.get("mode", "both"))}, int(args.get("timeout_s", 3600)))
    else:
        ok, text = _run_cli("harness2-run", _requeue_args_from_flag(flag, {
            "bench": bench,
            "k": int((flag.get("params") or {}).get("k", 1)),
            "mode": str((flag.get("params") or {}).get("mode", "parallel")),
            "substrate": str((flag.get("params") or {}).get("substrate", "oc")),
            "seed": (flag.get("params") or {}).get("seed"),
            "dry_run": str((flag.get("params") or {}).get("dry_run", "true")).lower() in ("1", "true", "yes"),
        }), int(args.get("timeout_s", 7200)))
    _requeue_consume()
    stamp = flag.get("iso", "?")
    return ok, f"[requeue drain signal={flag.get('signal','?')} @ {stamp}]\n{text}"

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "harness2_setup",
        "description": "Install a benchmark's runners, deps, and data (jb|lab|wb). Dry-run supported.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bench": {"type": "string", "enum": _BENCHES},
                "subset": {"type": "string", "enum": _SUBSETS, "description": "wb only"},
                "substrate": {"type": "string", "enum": ["oc", "cx"], "default": "oc"},
                "dry_run": {"type": "boolean", "default": False},
                "timeout_s": {"type": "integer", "default": 900},
            },
            "required": ["bench"],
        },
    },
    {
        "name": "harness2_check",
        "description": "Preflight an installed benchmark (runners, tools, judge). Cheap, no model calls.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **_cell_props(),
                "subset": {"type": "string", "enum": _SUBSETS, "description": "wb only"},
                "timeout_s": {"type": "integer", "default": 120},
            },
            "required": ["bench"],
        },
    },
    {
        "name": "harness2_run",
        "description": "Run one adaptation sweep (Propose-Probe-Compose). Costs money when not dry_run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **_cell_props(),
                "subset": {"type": "string", "enum": _SUBSETS, "description": "wb only"},
                **_identity_props(),
                **_run_control_props(),
                "timeout_s": {"type": "integer", "default": 7200},
            },
            "required": ["bench"],
        },
    },
    {
        "name": "harness2_judge",
        "description": "Judge the selected run of each task in a sweep namespace; caches judged.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **_cell_props(),
                "subset": {"type": "string", "enum": _SUBSETS, "description": "wb only"},
                **_identity_props(),
                "bases": {"type": "boolean", "default": False, "description": "Score reference (base) executions instead"},
                "timeout_s": {"type": "integer", "default": 3600},
            },
            "required": ["bench"],
        },
    },
    {
        "name": "harness2_report",
        "description": "Generate the report for a judged sweep (same identity as the run/judge).",
        "inputSchema": {
            "type": "object",
            "properties": {
                **_cell_props(),
                "subset": {"type": "string", "enum": _SUBSETS, "description": "wb only"},
                **_identity_props(),
                "timeout_s": {"type": "integer", "default": 1800},
            },
            "required": ["bench"],
        },
    },
    {
        "name": "harness2_demo",
        "description": "Local deterministic demo of both recursion modes. Zero credentials, safe to run anywhere.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "k": {"type": "integer", "default": 2},
                "output": {"type": "string", "default": "runs/demo"},
                "timeout_s": {"type": "integer", "default": 600},
            },
        },
    },
    {
        "name": "harness2_agns_demo",
        "description": "Path B demo: Agnes as substrate (AGNES_CLI or bundled deterministic worker). Zero credentials when AGNES_CLI is unset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "k": {"type": "integer", "default": 2},
                "mode": {"type": "string", "enum": ["parallel", "sequential", "both"], "default": "both"},
                "timeout_s": {"type": "integer", "default": 3600},
            },
        },
    },
    {
        "name": "harness2_requeue",
        "description": "Drain a pending re-run flag written by the harness2-loop hooks plugin (flag protocol). If a flag is pending, auto-runs the recipe for its bench/signal. Safe no-op when no flag exists. Use this when a build-failure or commit event has been recorded and you want to close the continuous-improvement loop in-session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timeout_s": {"type": "integer", "default": 7200},
            },
        },
    },
    {
        "name": "agnes_bridge_status",
        "description": "Check whether the Agnes OpenAI-compatible proxy (Path A) is running on 127.0.0.1:8620 and list /v1/models.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "agnes_bridge_start",
        "description": "Start the stdlib OpenAI-compatible bridge proxy (python -m agnes_bridge.agnes_openai_proxy). Needs AGNES_API_URL/AGNES_API_KEY/AGNES_MODEL in .agns_bridge.env or the environment.",
        "inputSchema": {"type": "object", "properties": {"port": {"type": "integer", "default": 8620}}},
    },
]

_TOOL_NAME_TO_CLI = {
    "harness2_setup": "harness2-setup",
    "harness2_check": "harness2-check",
    "harness2_run": "harness2-run",
    "harness2_judge": "harness2-judge",
    "harness2_report": "harness2-report",
    "harness2_demo": "harness2-demo",
    "harness2_agns_demo": "harness2-agns-demo",
}


def _bridge_status() -> tuple[bool, str]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8620/v1/models", timeout=3) as r:
            return True, f"bridge UP: {r.read(4096).decode(errors='replace')}"
    except Exception as exc:  # noqa: BLE001 - report any probe failure
        return False, f"bridge DOWN: {exc}"


def _bridge_start(args: dict[str, Any]) -> tuple[bool, str]:
    port = int(args.get("port", 8620))
    pidfile = REPO_ROOT / ".agnes" / "work" / "agns_bridge.pid"
    ok, msg = _bridge_status()
    if ok:
        return True, f"already running (port {port}): {msg}"
    cmd = [sys.executable, "-m", "agns_bridge.agnes_openai_proxy"]
    proc = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    pidfile.write_text(str(proc.pid))
    return True, f"bridge started pid={proc.pid} port={port}; env must carry AGNES_API_URL/AGNES_API_KEY/AGNES_MODEL"


def _dispatch(name: str, args: dict[str, Any]) -> tuple[bool, str]:
    if name == "harness2_requeue":
        return _drain_requeue(args)
    if name == "agnes_bridge_status":
        return _bridge_status()
    if name == "agnes_bridge_start":
        return _bridge_start(args)
    cli = _TOOL_NAME_TO_CLI.get(name)
    if cli is None:
        return False, f"unknown tool {name}"
    timeout = int(args.get("timeout_s", 1800)) if name.endswith("_demo") or name.startswith("harness2_") else int(args.get("timeout_s", 900))
    ok, text = _run_cli(cli, {k: v for k, v in args.items() if k != "timeout_s"}, timeout)
    # Non-invasive flag awareness: if the hooks plugin has recorded a pending
    # re-run, tell the agent so it can drain it via harness2_requeue.
    if name == "harness2_run" and _requeue_read():
        text += "\n[requeue] NOTE: a pending re-run flag from harness2-loop is queued; call harness2_requeue to drain it."
    return ok, text


# ---------------------------------------------------------------- MCP transport

_PROTOCOL_VERSION = "2024-11-05"


def _respond(msg_id: Any, result: Any) -> None:
    json.dump({"jsonrpc": "2.0", "id": msg_id, "result": result}, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _respond_error(msg_id: Any, code: int, message: str) -> None:
    json.dump({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method")
        msg_id = req.get("id")
        params = req.get("params") or {}

        if method == "initialize":
            _respond(msg_id, {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "harness2-mcp", "version": "0.1.0"},
            })
        elif method == "ping":
            _respond(msg_id, {})
        elif method in ("notifications/initialized", "notifications/cancelled"):
            continue
        elif method == "tools/list":
            _respond(msg_id, {"tools": _TOOLS})
        elif method == "tools/call":
            name = (params or {}).get("name", "")
            args = (params or {}).get("arguments") or {}
            try:
                ok, text = _dispatch(name, args)
            except Exception as exc:  # noqa: BLE001
                ok, text = False, f"internal error: {exc}"
            _respond(msg_id, {
                "content": [{"type": "text", "text": text}],
                "isError": not ok,
            })
        else:
            if msg_id is not None:
                _respond_error(msg_id, -32601, f"method not found: {method}")


if __name__ == "__main__":
    main()
