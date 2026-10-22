#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""harness2-loop zero-touch installer — cross-platform, stdlib-only.

Run ONCE on your machine. After this, every 'git commit' in ANY repo on
this machine writes a pending flag, and a 60-minute scheduler drains it.
No per-project or per-agent setup, and no bash on PATH required.

Usage:
    python multi-agent/adapters/zero-touch-setup.py            # install
    python multi-agent/adapters/zero-touch-setup.py --uninstall
    python multi-agent/adapters/zero-touch-setup.py --help

Mechanism (verified on git 2.53 / Windows):
  1. Build ~/.harness2-loop-template = [git's built-in template] + a
     'hooks/post-commit' that writes the pending flag. Snapshotting the
     built-in template first keeps every default .sample hook, so nothing
     is lost.
  2. git config --global init.templatedir  ~/.harness2-loop-template
     (NOTE: the real git key is init.templatedir, NOT core.hooksTemplateDir.)
     Every future 'git init' now copies hooks/post-commit into .git/hooks/.
  3. Register a 60-minute scheduler (Windows Task Scheduler on win32,
     cron on POSIX) that runs drain_requeue.py — pure Python, no shell.

Opt-out per project: drop a file named HARNESS2_LOOP_OFF at the root.

Uninstall: python multi-agent/adapters/zero-touch-setup.py --uninstall
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # multi-agent/adapters/
REPO_ROOT = HERE.parent.parent                          # <repo>/
POST_COMMIT = REPO_ROOT / "multi-agent" / "adapters" / "git" / "post-commit.sh"
DRAIN_PY = REPO_ROOT / ".Agnes Code" / "plugins" / "harness2-loop" / "scripts" / "drain_requeue.py"

TEMPLATE_DIR = Path.home() / ".harness2-loop-template"   # correct structure: <tpl>/hooks/post-commit
LEGACY_DIR = Path.home() / ".harness2-loop-hooks"        # earlier (buggy) path — cleaned up
SCHEDULER_NAME = "harness2-loop-drain"


def say(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str) -> None:
    say("ERROR: " + msg)
    sys.exit(1)


def run(cmd, quiet: bool = False):
    if not quiet:
        say("$ " + " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd],
                          stdout=None if quiet else sys.stdout,
                          stderr=None if quiet else sys.stderr).returncode


def quiet(cmd):
    return subprocess.run([str(c) for c in cmd],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def build_template() -> None:
    """Create TEMPLATE_DIR = git built-in template + our hooks/post-commit."""
    if not POST_COMMIT.exists():
        fail(f"source hook not found: {POST_COMMIT}\n"
             "  (did you clone the full harness2 repo / unpack the portable zip?)")
    # 1) snapshot git's built-in template from a throwaway default repo so we
    #    keep every default .sample hook (zero regression).
    quiet(["git", "config", "--global", "--unset", "init.templatedir"])  # may not be set -> ignore
    tmp = tempfile.mkdtemp(prefix="h2zt-def-")
    if quiet(["git", "init", "-q", tmp]) != 0:
        fail("could not create a throwaway repo to snapshot the default template — is git installed?")
    src = os.path.join(tmp, ".git")
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    for item in ("description", "config"):
        p = os.path.join(src, item)
        if os.path.exists(p):
            shutil.copy2(p, TEMPLATE_DIR / item)
    info_src = os.path.join(src, "info", "exclude")
    if os.path.exists(info_src):
        (TEMPLATE_DIR / "info").mkdir(exist_ok=True)
        shutil.copy2(info_src, TEMPLATE_DIR / "info" / "exclude")
    hooks_src = os.path.join(src, "hooks")
    hooks_dst = TEMPLATE_DIR / "hooks"
    hooks_dst.mkdir(exist_ok=True)
    if os.path.isdir(hooks_src):
        for f in os.listdir(hooks_src):
            shutil.copy2(os.path.join(hooks_src, f), hooks_dst / f)
    # 2) overlay our post-commit (executable)
    shutil.copy2(POST_COMMIT, hooks_dst / "post-commit")
    os.chmod(str(hooks_dst / "post-commit"), 0o755)
    shutil.rmtree(tmp, ignore_errors=True)
    say(f"      template built: {TEMPLATE_DIR} "
        f"({len(list((TEMPLATE_DIR/'hooks').iterdir()))} hooks incl. our post-commit)")


def clean_legacy() -> None:
    # Remove the earlier buggy config key + the wrong-path dir, if present.
    quiet(["git", "config", "--global", "--unset", "core.hooksTemplateDir"])
    if LEGACY_DIR.exists():
        shutil.rmtree(LEGACY_DIR, ignore_errors=True)
        say(f"      removed legacy {LEGACY_DIR.name}/")


def install() -> None:
    clean_legacy()
    build_template()
    if quiet(["git", "config", "--global", "init.templatedir", str(TEMPLATE_DIR)]) != 0:
        fail("could not set 'git config --global init.templatedir' — is git installed?")
    say(f"      every NEW 'git init' now copies hooks/post-commit into .git/hooks/.")
    say("      For EXISTING repos, copy once: ")
    say(f"        copy {TEMPLATE_DIR}/hooks/post-commit  <repo>/.git/hooks/post-commit")


def install_scheduler() -> None:
    py = sys.executable or "python"
    log_path = (
        Path(os.environ.get("TEMP", str(Path.home()))) / "harness2-loop-drain.log"
        if os.name == "nt" else Path.home() / ".harness2-loop-drain.log"
    )
    if os.name == "nt":
        if quiet(["schtasks", "/Query", "/TN", SCHEDULER_NAME]) == 0:
            say(f"      [sched] Task Scheduler '{SCHEDULER_NAME}' already exists — skip")
            return
        if not DRAIN_PY.exists():
            fail(f"drain script missing: {DRAIN_PY}")
        rc = run(["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", "60",
                  "/TN", SCHEDULER_NAME,
                  "/TR", f'"{py}" "{DRAIN_PY}" >> "{log_path}" 2>&1'])
        if rc == 0:
            say(f"      [sched] registered Task Scheduler '{SCHEDULER_NAME}' (every 60 min, log -> {log_path})")
        else:
            say(f"      [sched] schtasks failed (exit {rc}). Register manually:\n"
                f'              schtasks /Create /F /SC MINUTE /MO 60 /TN {SCHEDULER_NAME} '
                f'/TR "{py} "{DRAIN_PY}" >> "{log_path}" 2>&1"')
    else:
        crontab = shutil.which("crontab")
        if not crontab:
            say("      [sched] crontab unavailable — skip (in-session drain still works)")
            return
        marker = "harness2-loop-drain"
        line = f"0 * * * * {py} '{DRAIN_PY}' >> {log_path} 2>&1  # {marker}"
        existing = subprocess.run([crontab, "-l"], text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
        if marker in existing:
            say("      [sched] cron entry already present — skip")
            return
        kept = "\n".join(l for l in (existing + "\n").splitlines() if marker not in l).rstrip()
        new_cron = (kept + "\n" + line + "\n").lstrip()
        if subprocess.run([crontab, "-"], input=new_cron, text=True,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            say(f"      [sched] registered cron: {line}")
        else:
            say(f"      [sched] crontab update failed — add manually: {line}")


def uninstall() -> None:
    say("Uninstalling zero-touch ...")
    quiet(["git", "config", "--global", "--unset", "init.templatedir"])
    quiet(["git", "config", "--global", "--unset", "core.hooksTemplateDir"])
    for d in (TEMPLATE_DIR, LEGACY_DIR):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            say(f"      removed {d}")
    if os.name == "nt":
        quiet(["schtasks", "/Delete", "/TN", SCHEDULER_NAME, "/F"])
        say("      removed Task Scheduler entry (if it existed)")
    else:
        crontab = shutil.which("crontab")
        if crontab:
            existing = subprocess.run([crontab, "-l"], text=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
            kept = [l for l in existing.splitlines() if "harness2-loop-drain" not in l]
            subprocess.run([crontab, "-"], input="\n".join(kept) + ("\n" if kept else ""),
                           text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            say("      removed cron entry")
    say("Per-project opt-out files (HARNESS2_LOOP_OFF) are untouched.")
    say("Any repo whose .git/hooks/post-commit you copied manually must be cleaned by hand.")


def main() -> None:
    if sys.version_info < (3, 8):
        fail("Python 3.8+ required")
    if not REPO_ROOT.exists():
        fail(f"could not locate harness2 repo root (inferred {REPO_ROOT})")

    argv = sys.argv[1:]
    if not argv or argv[0] in {"install", "-i"}:
        say("== harness2-loop zero-touch installer (cross-platform) ==")
        say(f"   platform : {platform.system()}   repo root: {REPO_ROOT}")
        say("")
        say("[1/2] git global hook template ...")
        install()
        say("")
        say("[2/2] 60-minute off-session scheduler ...")
        install_scheduler()
        say("")
        say("ZERO-TOUCH READY.")
        say("  • Any 'git commit' on this machine now auto-writes a pending flag.")
        say("  • In-session: any MCP agent drains it via harness2_requeue.")
        say("  • Off-session: the 60-min scheduler drains it.")
        say("  • Per-project opt-out:  create <project>/HARNESS2_LOOP_OFF")
        say(f"  • Undo everything:       python {Path(__file__).name} --uninstall")
        return

    if argv[0] in {"--uninstall", "uninstall", "-u"}:
        uninstall()
        return
    if argv[0] in {"--help", "-h", "help"}:
        print(__doc__)
        return
    fail(f"unknown argument: {argv[0]}  (use --help)")


if __name__ == "__main__":
    main()
