#!/usr/bin/env python3
"""harness2-loop scheduled drain (path C): consume the pending re-run flag.

A scheduler (Agnes Code desktop scheduling, or Windows Task Scheduler --
see config.json schedule_hint.windows_task_sch) invokes this script
periodically. It:

  1. reads .state/pending_re.json (written by rerun_recipe.py on build
     failure / git commit),
  2. runs the same pipeline the recipe would (setup -> check -> run ->
     judge -> report for jb/lab/wb, or the deterministic demo for
     demo/ags-demo) via direct `python -m harness2.cli.*` invocation --
     no external Agnes Code CLI binary is required,
  3. appends to .state/recipe-runs.log, then REMOVES the flag (consumed).

If no flag is pending, it logs "nothing pending" and exits 0 (safe no-op,
idempotent under a scheduler).

Config: <plugin_root>/config.json (HARNESS2_LOOP_CONFIG to override).
"""
import json
import os
import subprocess
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# reuse helpers from the hook script (same package dir)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from rerun_recipe import root, load_config, state_dir, append_log, queue_path
except Exception:  # pragma: no cover - fall back to inline equivalents
    def root():
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def load_config(root_path):
        p = os.environ.get("HARNESS2_LOOP_CONFIG") or os.path.join(root_path, "config.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def state_dir(root_path):
        d = os.path.join(root_path, ".state")
        os.makedirs(d, exist_ok=True)
        return d

    def append_log(root_path, msg):
        try:
            with open(os.path.join(state_dir(root_path), "harness2-loop.log"), "a", encoding="utf-8") as fh:
                fh.write("[%s] %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), msg))
        except Exception:
            pass

    def queue_path(root_path):
        return os.path.join(state_dir(root_path), "pending_re.json")


def _cli_module_for(tool):
    return {
        "harness2-setup": "harness2.cli.setup",
        "harness2-check": "harness2.cli.check",
        "harness2": "harness2.cli.run_sweep",
        "harness2-judge": "harness2.cli.judge",
        "harness2-report": "harness2.cli.report",
        "harness2-demo": "harness2.cli.demo",
        "harness2-agns-demo": "harness2.cli.agns_demo",
    }[tool]


def _pipeline(bench, params):
    """Same step ordering as recipes/harness2-any-project.yaml."""
    k = int(params.get("k", 1))
    mode = str(params.get("mode", "parallel"))
    substrate = str(params.get("substrate", "oc"))
    seed = params.get("seed", None)
    dry_run = str(params.get("dry_run", "true")).lower() in ("1", "true", "yes")
    identity = []
    if seed not in (None, ""):
        identity += ["--seed", str(seed)]
    if bench in ("demo",):
        return [
            "harness2-demo --k %d" % max(k, 1),
        ]
    if bench == "ags-demo":
        return [
            "harness2-agns-demo --k %d --mode %s" % (max(k, 1), mode),
        ]
    setup_cmd = "harness2-setup %s --substrate %s" % (bench, substrate)
    if dry_run:
        setup_cmd += " --dry-run"
    return [
        setup_cmd,
        "harness2-check --bench %s --substrate %s %s" % (bench, substrate, " ".join(identity)),
        "harness2 --bench %s --substrate %s %s --k %d --modes %s %s" % (
            bench, substrate, " ".join(identity), k, mode,
            "--dry-run" if dry_run else ""),
        "harness2-judge --bench %s --substrate %s %s --k %d --modes %s" % (
            bench, substrate, " ".join(identity), k, mode),
        "harness2-report --bench %s --substrate %s %s --k %d --modes %s" % (
            bench, substrate, " ".join(identity), k, mode),
    ]


def main():
    root_path = root()
    cfg = load_config(root_path)
    repo_root = cfg.get("repo_root") or os.getcwd()
    flag_path = queue_path(root_path)

    if not os.path.exists(flag_path):
        append_log(root_path, "drain: nothing pending, no-op")
        print("nothing pending")
        return 0

    try:
        with open(flag_path, "r", encoding="utf-8") as fh:
            flag = json.load(fh)
    except Exception:
        os.unlink(flag_path)
        append_log(root_path, "drain: stale flag removed")
        print("stale flag removed")
        return 0

    params = dict(flag.get("params") or {})
    if cfg.get("schedule_hint", {}).get("dry_run") == "true" and "dry_run" not in params:
        params["dry_run"] = "true"
    bench = str(params.get("bench", "demo"))
    cmds = _pipeline(bench, params)

    runs_dir = cfg.get("runs_dir") or os.path.join(repo_root, "runs")
    env = {**os.environ, "HARNESS2_RUNS_DIR": runs_dir}
    if flag.get("runs_namespace"):
        env["HARNESS2_RUNS_NAMESPACE"] = str(flag["runs_namespace"])

    log_path = os.path.join(state_dir(root_path), "recipe-runs.log")
    exit_code = 0
    with open(log_path, "a", encoding="utf-8") as out:
        out.write("\n=== drain %s (signal=%s bench=%s) ===\n" % (
            flag.get("iso", "?"), flag.get("signal", "?"), bench))
        for cmd in cmds:
            # "tool --flags" -> [python, -m, module, flags...]
            tool, _, flags = cmd.partition(" ")
            module = _cli_module_for(tool)
            argv = [sys.executable, "-m", module] + flags.split()
            out.write("$ %s\n" % " ".join(argv))
            out.flush()
            proc = subprocess.run(argv, cwd=repo_root, env=env,
                                  stdout=out, stderr=subprocess.STDOUT)
            if proc.returncode != 0:
                out.write("[exit=%d] %s\n" % (proc.returncode, " ".join(argv)))
                exit_code = proc.returncode
                break
        out.write("[drain complete exit=%d]\n" % exit_code)

    os.unlink(flag_path)  # consumed
    append_log(root_path, "drain: consumed flag (signal=%s bench=%s) exit=%d" % (
        flag.get("signal", "?"), bench, exit_code))
    print("drained flag for bench=%s (exit=%d)" % (bench, exit_code))
    return 0 if exit_code == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # scheduler-safe: never crash the schedule
        try:
            append_log(root(), "drain: error: %s" % exc)
        except Exception:
            pass
        sys.exit(0)
