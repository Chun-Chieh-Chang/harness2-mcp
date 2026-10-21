# Agnes integration -- added locally for the desktop experiment.
# Mirrors opencode.py / codex.py against the Substrate protocol in base.py.
#
# "Agnes" here means the user's Agnes Code desktop agent (Sapiens AI).
# Two integration axes:
#   * Path B (this file): Agnes is a *substrate* -- an agent framework whose
#     c1..c8 harness (system prompt, guardrails, memory, tool guidance,
#     subagents, skills, scripts, plugins) Harness^2 recursively refines.
#   * Path A (see agnes_bridge/): Agnes is the *frozen model* behind an
#     OpenAI-compatible endpoint the executor talks to.
#
# Desktop-first: when AGNES_CLI is not set, `execute` runs a deterministic
# bundled worker so the whole recursion is reproducible with no credentials.

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping

from .. import config
from ..core import runmark as RM
from ..core import tree as HT
from ..core.tree import SurfaceSpec
from .base import Install, Launcher, RunRequest

# The Agnes editable surface: the same c1..c8 roles, Agnes-native filenames.
AGNES_SURFACE = SurfaceSpec(
    name="agnes",
    always_on=(
        "systemprompt.md",
        "guardrails.md",
        "LongTermMEMORY.md",
        "tool_descriptions/tool_guidance.md",
    ),
    always_on_max=24_000,
    always_on_cap_reason="every token here competes with the agent's own output budget",
    skill_dir="skills",
    skill_name_rule="must_match",
    trigger_hint=(
        "Fix it by adding a trigger line naming `{name}` to systemprompt.md or "
        'guardrails.md, e.g. "When <the situation>, load the `{name}` skill."'
    ),
    autotrigger_file="guardrails.md",
    trigger_line="- When {desc}, load the `{name}` skill.\n",
    subagent_requires_mode=True,
    plugin_dir="plugin",
    hooks_file=None,
    stubs=(
        (
            "scripts/README.md",
            "<!-- c7: Agnes deterministic helpers, run as `python3 scripts/<name>.py`. -->\n",
        ),
        (
            "sub_agents/README.md",
            "<!-- c5: Agnes subagents, AGENT.md frontmatter `mode: subagent`. -->\n",
        ),
        (
            "plugin/README.md",
            "<!-- c8: Agnes plugins act inside the tool loop. -->\n",
        ),
        (
            "skills/README.md",
            "<!-- c6: Agnes skills, SKILL.md frontmatter `name:` matches the dir. -->\n",
        ),
    ),
)

# Agnes install modes. We accept any of the global INSTALL_MODES so a benchmark
# can hand us a tree staged under any delivery channel; Agnes materialises the
# same c1..c8 set regardless of which opencode/codex mode produced the tree.
_AGNES_INSTALL_MODES = ("agn_workspace", "workspace_agents_md", "home_dir_jinja",
                        "workspace_config", "codex_root")

# Deterministic bundled worker (no model needed). Reads the staged harness's
# scripts/summarize.py and applies it to a task ledger, exactly like demo.py.
_WORKER = """import csv, sys
from decimal import Decimal
with open(sys.argv[1]) as src:
    rows = [Decimal(r['amount']) for r in csv.DictReader(src)]
print(f'Total: {sum(rows, Decimal(0)):.2f}')
"""


def _agnes_cli() -> str | None:
    return os.environ.get("AGNES_CLI") or None


def _run_agnes_cli(cli: str, workspace: Path, task_ref: str, *, timeout: int) -> tuple[bool, str, str]:
    """Run the user's Agnes headless CLI against a staged workspace.

    Contract (documented in agnes_bridge/README.md): the CLI is executed with
    cwd = the staged harness workspace and env AGNES_TASK / AGNES_WORKSPACE;
    it either writes `answer.txt` in the workspace or prints the answer.
    Returns (ok, trajectory_text, answer_text).
    """
    env = dict(os.environ)
    env["AGNES_TASK"] = str(task_ref)
    env["AGNES_WORKSPACE"] = str(workspace)
    proc = subprocess.run(
        cli,
        shell=True,
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    answer_file = workspace / "answer.txt"
    if answer_file.is_file():
        answer = answer_file.read_text(encoding="utf-8")
        try:
            answer_file.unlink()
        except OSError:
            pass
    else:
        answer = proc.stdout.strip()
    traj = f"[ACTION] AGNES_CLI: {cli} (task={task_ref})\n[OBSERVATION]\n{proc.stdout}"
    if proc.returncode != 0:
        traj += f"[ERROR]\n{proc.stderr}"
    return proc.returncode == 0, traj, answer


def _run_worker(script: Path, ledger: Path, out: Path, *, timeout: int) -> tuple[bool, str]:
    """Run the staged deterministic worker. Returns (ok, trajectory_text)."""
    proc = subprocess.run(
        [sys.executable, str(script), str(ledger)],
        capture_output=True, text=True, timeout=timeout,
    )
    ok = proc.returncode == 0
    traj = (
        "[ACTION] Agnes runs scripts/summarize.py on the task ledger\n"
        f"[OBSERVATION]\n{proc.stdout}"
    )
    if not ok:
        traj += f"[ERROR]\n{proc.stderr}"
    return ok, traj


class AgnesSubstrate:
    """Agnes Code behind the one Substrate interface (Path B)."""

    name = "ags"

    def __init__(self, launcher: Launcher | None = None):
        self._launcher = launcher

    def surface(self) -> SurfaceSpec:
        return AGNES_SURFACE

    def preflight(self) -> None:
        """Health checks before money is spent; never starts the model chain."""
        cli = _agnes_cli()
        if cli:
            return  # real Agnes CLI/SDK path; endpoint availability tested on first call
        # Deterministic fallback: just need an interpreter.
        if not (sys.executable and Path(sys.executable).is_file()):
            raise RuntimeError(
                "No Agnes executor found. Set AGNES_CLI to your Agnes Code "
                "executable/SDK command, or leave it unset to use the bundled "
                "deterministic worker."
            )

    def materialise(self, tree_dir: Path, spec, ctx: Mapping[str, str]) -> Install:
        mode = spec.install_mode
        if mode not in _AGNES_INSTALL_MODES:
            raise ValueError(
                f"install_mode {mode!r} is not an Agnes mode; this substrate "
                f"supports {_AGNES_INSTALL_MODES}"
            )
        tree_dir = Path(tree_dir)
        if not HT.is_tree(AGNES_SURFACE, tree_dir):
            raise ValueError(f"{tree_dir} is not an Agnes harness tree (no always-on file)")
        staged = Path(tempfile.mkdtemp(prefix=f"adapt-ags-{mode}-"))
        try:
            shutil.copytree(tree_dir, staged, dirs_exist_ok=True)
            for key, body in ctx.items():
                if key.startswith("file:"):
                    rel = HT.normalize_rel(key[len("file:"):])
                    p = staged / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(body, encoding="utf-8")
        except BaseException:
            shutil.rmtree(staged, ignore_errors=True)
            raise
        return Install(
            staging_dir=staged,
            fingerprint=RM.fingerprint(tree_dir),
            extras={"install_mode": mode},
        )

    def execute(
        self, task_ref: str, install: Install, run_ids: list[str], timeout: int
    ) -> list[Path]:
        """One run_dir per run_id. Rollout is driven by the benchmark launcher
        (self._launcher) when supplied, else by the bundled deterministic worker
        so the desktop experiment runs with no credentials."""
        if self._launcher is not None:
            return self._launcher(RunRequest(task_ref, tuple(run_ids), timeout), install)

        cli = _agnes_cli()
        out_dirs: list[Path] = []
        workspace = Path(install.staging_dir)
        for run_id in run_ids:
            run_dir = workspace / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            if cli:
                # Real Agnes headless CLI (B3 preferred executor).
                try:
                    ok, traj, answer = _run_agnes_cli(cli, workspace, task_ref, timeout=timeout)
                except (subprocess.TimeoutExpired, OSError) as exc:
                    ok, traj, answer = False, f"[ERROR]\nAGNES_CLI failed: {exc}", ""
                (run_dir / "answer.txt").write_text(answer, encoding="utf-8")
                (run_dir / "trajectory.md").write_text(traj, encoding="utf-8")
                (run_dir / "ok").write_text("1" if ok else "0", encoding="utf-8")
                out_dirs.append(run_dir)
                continue

            ledger = workspace / "ledger.csv"
            script = workspace / "scripts" / "summarize.py"
            if script.is_file() and ledger.is_file():
                ok, traj = _run_worker(script, ledger, run_dir, timeout=timeout)
                (run_dir / "answer.txt").write_text(traj.split("[OBSERVATION]\n", 1)[-1].split("[ERROR]")[0], encoding="utf-8")
                (run_dir / "trajectory.md").write_text(traj, encoding="utf-8")
                (run_dir / "ok").write_text("1" if ok else "0", encoding="utf-8")
            else:
                # No worker: record a failed rollout so recursion has a contrast.
                (run_dir / "trajectory.md").write_text(
                    "[ERROR]\nAgnes executor produced no answer (no worker script).",
                    encoding="utf-8",
                )
            out_dirs.append(run_dir)
        return out_dirs

    def read_trajectory(
        self, stream_path: Path, *, obs_trunc: int, max_chars: int, args_trunc: int = 400
    ) -> str:
        text = stream_path.read_text(encoding="utf-8") if stream_path.is_file() else ""
        return text[:max_chars]


__all__ = ["AGNES_SURFACE", "AgnesSubstrate"]
