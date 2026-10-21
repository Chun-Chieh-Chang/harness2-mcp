# Agnes demo adapter -- local, no-credentials integration of Agnes Code as a
# recursively-harnessed substrate.  Mirrors demo.py but uses AgnesSubstrate.

from __future__ import annotations

import os
import shutil
import tempfile
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from .core import tree
from .core.proposer import Proposer, Reply
from .core.spec import BenchPrompts, BenchSpec, ChannelSpec
from .substrate.agnes import AgnesSubstrate

BASE_SCRIPT = """import csv
import sys
from decimal import Decimal

with open(sys.argv[1]) as source:
    amounts = [Decimal(row['amount']) for row in csv.DictReader(source)]
total = sum((amount for amount in amounts if amount > 0), Decimal(0))
print(f'Total: {total:.2f}')
"""

TASKS = {
    "ledger-1": "100.25\n-20.10\n5.00\n",
    "ledger-2": "35.50\n-10.25\n-5.00\n",
}


class AgnesAdapter:
    """BenchmarkAdapter driving AgnesSubstrate with the deterministic bundled worker.

    Same ledger-reconciliation tasks as demo.py; swap the substrate so
    Harness^2's c1..c8 recursion refines the Agnes harness surface.
    """

    def __init__(self, root: Path):
        self.root = root
        self.substrate = AgnesSubstrate()
        channel = ChannelSpec("opencode", "local/deterministic")
        self.spec = BenchSpec(
            name="agns_demo",
            runs_root=root / "runs",
            install_mode="agn_workspace",
            prompts=BenchPrompts(work="reconcile signed amounts in a transaction ledger"),
            channels={"proposer": channel, "selector": channel},
            leak_globs=("reference_answer.txt",),
        )
        self.execution_count = 0

        # Seed the base harness + task data (same as DemoAdapter)
        surface = self.substrate.surface()
        base = {name: "" for name in surface.always_on}
        base["systemprompt.md"] = (
            "Reconcile the ledger using python scripts/summarize.py.\n"
        )
        base["scripts/summarize.py"] = BASE_SCRIPT
        tree.write_tree(surface, base, self.base_harness(), stubs=False)

        for task_id, amounts in TASKS.items():
            src = self.task_files(task_id)
            src.mkdir(parents=True, exist_ok=True)
            (src / "ledger.csv").write_text("amount\n" + amounts, encoding="utf-8")

    # -- BenchmarkAdapter protocol -------------------------------------------

    def tasks(self, split: str = "all") -> list[str]:
        return list(TASKS.keys())

    def domain_of(self, task_id: str) -> str:
        return "accounting"

    def task_prompt(self, task_id: str) -> str:
        return "Sum every signed amount in ledger.csv. Return Total: with two decimal places."

    def task_files(self, task_id: str) -> Path:
        return self.root / "sources" / task_id

    def base_harness(self) -> Path:
        return self.root / "base"

    def validate_tree(self, harness: dict[str, str]) -> None:
        if "scripts/summarize.py" not in harness:
            raise ValueError("The Agnes executor requires scripts/summarize.py")

    def execute(
        self,
        task_id: str,
        harness_dir: Path | None,
        run_id: str,
        *,
        timeout: int | None = None,
    ) -> Path:
        self.execution_count += 1
        run_dir = self.root / "executions" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        ledger = self.task_files(task_id) / "ledger.csv"
        timeout = timeout or 10

        cli = os.environ.get("AGNES_CLI") or None
        if cli:
            # B3: prefer the real Agnes headless CLI. Contract: run with cwd=
            # a workspace containing the staged harness + ledger.csv; it may
            # either write answer.txt in the workspace or print the answer.
            safe_id = str(run_id).replace("/", "-").replace("\\", "-")
            workspace = Path(tempfile.mkdtemp(prefix=f"agns-demo-{safe_id}-"))
            h = harness_dir or self.base_harness()
            if h.is_dir():
                shutil.copytree(h, workspace, dirs_exist_ok=True)
            (workspace / "ledger.csv").write_text(
                ledger.read_text(encoding="utf-8"), encoding="utf-8"
            )
            env = dict(os.environ, AGNES_TASK=task_id, AGNES_WORKSPACE=str(workspace))
            result = subprocess.run(
                cli, shell=True, cwd=workspace, env=env,
                capture_output=True, text=True, check=False, timeout=timeout,
            )
            answer_file = workspace / "answer.txt"
            answer = answer_file.read_text(encoding="utf-8") if answer_file.is_file() else result.stdout
            traj = f"[ACTION] AGNES_CLI: {cli} (task={task_id})\n[OBSERVATION]\n{result.stdout}"
            if result.returncode != 0:
                traj += f"[ERROR]\n{result.stderr}"
            shutil.rmtree(workspace, ignore_errors=True)
            (run_dir / "answer.txt").write_text(answer, encoding="utf-8")
            (run_dir / "trajectory.md").write_text(traj, encoding="utf-8")
            return run_dir

        script = (harness_dir or self.base_harness()) / "scripts" / "summarize.py"
        result = subprocess.run(
            [sys.executable, str(script), str(ledger)],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        traj = (
            "[ACTION] Agnes runs scripts/summarize.py on ledger.csv\n"
            "[OBSERVATION]\n" + result.stdout
        )
        if result.returncode != 0:
            traj += f"[ERROR]\n{result.stderr}"
        (run_dir / "answer.txt").write_text(result.stdout, encoding="utf-8")
        (run_dir / "trajectory.md").write_text(traj, encoding="utf-8")
        return run_dir

    def delivered(self, run_dir: Path) -> bool:
        return (run_dir / "answer.txt").is_file()

    def trajectory(self, run_dir: Path, *, obs_trunc: int) -> str:
        return (run_dir / "trajectory.md").read_text(encoding="utf-8")

    def deliverable_text(self, run_dir: Path) -> str:
        return (run_dir / "answer.txt").read_text(encoding="utf-8")

    def deliverable_files(self, run_dir: Path) -> dict[str, str]:
        return {"answer.txt": self.deliverable_text(run_dir)}


class AgnesDemoProposer(Proposer):
    """Deterministic prop-ose-probe-compose; no model service needed."""

    def call(self, mission, context_dir, label, **kwargs) -> Reply:
        context = Path(context_dir)
        workspace = None

        if label.startswith("select."):
            with (context / "source" / "ledger.csv").open() as source:
                expected = sum(
                    (Decimal(row["amount"]) for row in __import__("csv").DictReader(source)),
                    Decimal(0),
                )
            candidates = sorted((context / "candidates").glob("*.md"))
            chosen = next(
                (path.stem for path in candidates if f"Total: {expected:.2f}" in path.read_text()),
                None,
            ) or (candidates[0].stem if candidates else "base")
            text = (
                f"<why>The signed total matches the source ledger.</why>\n"
                f"```choice\n{chosen}\n```"
            )

        elif label.startswith("experience."):
            changed = (context / "harness" / "scripts" / "summarize.py").read_text() != (
                context / "base_harness" / "scripts" / "summarize.py"
            ).read_text()
            text = (
                "<edits>\ncomponent: scripts/summarize.py\ncandidates: inv1\n"
                "change: dropped the positive-only filter from the amount sum\n"
                "observed: the probe total included the credits the base run omitted\n"
                f"verdict: {'helped' if changed else 'no observed effect'}\n</edits>\n\n"
            ) + (
                "<experience>\n"
                "cue: When a ledger includes credits and debits\n"
                "lesson: Include both signs when summing in scripts/summarize.py.\n"
                "evidence: The probe total changed from positive-only to all-signed.\n"
                "confidence: high\n</experience>"
                if changed
                else "NO_ENTRY"
            )

        else:
            workspace = context / "harness"
            script = workspace / "scripts" / "summarize.py"
            script.write_text(
                script.read_text().replace(" if amount > 0", ""), encoding="utf-8"
            )
            text = (
                "<notes>Keep signed amounts: the base total omitted credits in the source ledger.</notes>"
            )

        reply = Reply(label=label, text=text, ok=True, attempts=1, workspace=workspace)
        self._calls.append(reply)
        return reply


__all__ = ["AgnesAdapter", "AgnesDemoProposer", "TASKS"]
