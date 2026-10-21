#!/usr/bin/env python3
"""harness2-loop: continuous-improvement hook runner.

Invoked by Agnes Code hooks (PostToolUseFailure / AfterShellExecution).
It:
  1. reads the event payload from stdin (event / session_id / tool_input /
     message / working_dir),
  2. decides whether this event should trigger a re-run of the harness2
     improvement recipe (build-failure signal, or a git commit),
  3. applies a per-signal cooldown to stop the loop from re-triggering
     itself (the recipe itself runs builds/tests/commits),
  4. launches `Agnes Code run --recipe <recipe> ...` in a DETACHED
     background process and returns immediately.

This script is observation-only: it never blocks the session and always
exits 0 so it can never crash or block Agnes Code (hook failures are
logged, not fatal).

Config is read from <plugin_root>/config.json (path overridable via the
HARNESS2_LOOP_CONFIG env var).
"""
import json
import os
import re
import sys
import time
import datetime
import subprocess


TRIGGER_KEY = {
    "build-failure": "build_failure_trigger",
    "commit": "commit_trigger",
    "any": "any_trigger",
}
STATE_KEY = {
    "build-failure": "build_failure",
    "commit": "commit",
    "any": "any",
}

DEFAULT_BUILD_PATTERNS = [
    r"\b(cargo|npm|pnpm|yarn|make|go)\b.*\b(build|test)\b",
    r"\bpython\d?\b.*\b(pip\s+install|pytest|build|test)\b",
    r"\b(build|test|pytest)\b",
]


def root():
    return os.environ.get("FLUIGIN_ROOT") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )


def read_payload():
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    except Exception:
        raw = ""
    try:
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def load_config(root_path):
    cfg_path = os.environ.get("HARNESS2_LOOP_CONFIG") or os.path.join(
        root_path, "config.json"
    )
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def state_dir(root_path):
    d = os.path.join(root_path, ".state")
    os.makedirs(d, exist_ok=True)
    return d


def append_log(root_path, msg):
    p = os.path.join(state_dir(root_path), "harness2-loop.log")
    try:
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(
                "[%s] %s\n" % (
                    datetime.datetime.now().isoformat(timespec="seconds"),
                    msg,
                )
            )
    except Exception:
        pass

def within_cooldown(root_path, state_key, cooldown):
    if not cooldown:
        return False
    f = os.path.join(state_dir(root_path), "last_%s" % state_key)
    try:
        with open(f, "r") as fh:
            last = float(fh.read().strip())
        return (time.time() - last) < float(cooldown)
    except Exception:
        return False


def mark_run(root_path, state_key):
    f = os.path.join(state_dir(root_path), "last_%s" % state_key)
    try:
        with open(f, "w") as fh:
            fh.write(str(time.time()))
    except Exception:
        pass


def context_text(signal, payload):
    ti = payload.get("tool_input") or {}
    cmd = ti.get("command") if isinstance(ti, dict) else ""
    return " ".join(
        [
            payload.get("event") or "",
            cmd or "",
            payload.get("message") or "",
            payload.get("last_assistant_message") or "",
        ]
    )


def should_trigger(signal, cfg, payload):
    ctx = context_text(signal, payload)
    if signal == "commit":
        return re.search(r"\bgit\s+commit\b", ctx, re.IGNORECASE) is not None
    patterns = cfg.get("build_patterns") or DEFAULT_BUILD_PATTERNS
    return any(re.search(p, ctx, re.IGNORECASE) for p in patterns)


def spawn_detached(cmd_list, repo_root, log_path):
    if os.name == "nt":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        out = open(log_path, "a")
        subprocess.Popen(
            cmd_list,
            cwd=repo_root,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
    else:
        out = open(log_path, "a")
        subprocess.Popen(
            cmd_list,
            cwd=repo_root,
            start_new_session=True,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )


def main():
    signal = sys.argv[1] if len(sys.argv) > 1 else "any"
    root_path = root()
    payload = read_payload()
    cfg = load_config(root_path)

    trigger_key = TRIGGER_KEY.get(signal, "any_trigger")
    state_key = STATE_KEY.get(signal, "any")
    if not cfg.get(trigger_key, True):
        append_log(root_path, "%s: disabled in config (%s=false), skip" % (signal, trigger_key))
        return 0

    if not should_trigger(signal, cfg, payload):
        append_log(root_path, "%s: no build/commit signal in payload, skip" % signal)
        return 0

    if within_cooldown(root_path, state_key, cfg.get("cooldown_seconds", 600)):
        append_log(root_path, "%s: within cooldown, skip" % signal)
        return 0

    repo_root = cfg.get("repo_root") or os.getcwd()
    recipe = cfg.get("recipe", "recipes/harness2-any-project.yaml")
    recipe_path = recipe if os.path.isabs(recipe) else os.path.join(repo_root, recipe)

    cli = (cfg.get("cli", "Agnes Code")).split()
    params = dict(cfg.get("params") or {})
    if signal == "build-failure":
        params.setdefault("dry_run", "false")

    cmd_list = cli + ["run", "--recipe", recipe_path]
    for k, v in params.items():
        cmd_list.append("--params %s=%s" % (k, v))
    if cfg.get("runs_dir"):
        cmd_list += ["--runs-dir", cfg["runs_dir"]]
    if cfg.get("runs_namespace"):
        cmd_list += ["--runs-namespace", cfg["runs_namespace"]]

    log_path = os.path.join(state_dir(root_path), "recipe-runs.log")
    try:
        spawn_detached(cmd_list, repo_root, log_path)
        mark_run(root_path, state_key)
        append_log(root_path, "%s: launched: %s" % (signal, " ".join(cmd_list)))
    except Exception as e:
        # keep the log message ASCII-safe and actionable (error text is
        # locale-dependent and can render as mojibake in UTF-8 logs)
        err = str(e).encode("ascii", "replace").decode("ascii")
        hint = ""
        if "WinError 2" in err or "ENOENT" in err:
            hint = (" -- CLI not found on PATH. Set config.json 'cli' to the "
                    "absolute path of your Agnes Code CLI binary.")
        append_log(root_path, "%s: launch failed: %s%s" % (signal, err, hint))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # observation-only: never crash / block the session
        sys.exit(0)
