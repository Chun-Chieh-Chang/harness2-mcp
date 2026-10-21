# Agnes demo CLI -- runs the real Harness^2 recursion against the Agnes
# substrate using the deterministic bundled worker (no model credentials).

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..agnes_demo import AgnesAdapter, AgnesDemoProposer
from ..core.schedule import mode_token, run_domain


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Harness^2 task-level recursion over the Agnes substrate (deterministic)."
    )
    parser.add_argument("--output", type=Path, default=Path("runs/agns_demo"))
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--mode", choices=("parallel", "sequential", "both"), default="both")
    args = parser.parse_args(argv)
    if args.k < 1:
        parser.error("--k must be positive")

    root = args.output.expanduser().resolve()
    adapter = AgnesAdapter(root)
    proposer = AgnesDemoProposer(adapter.spec.channels["proposer"])
    modes = ("agg", "seq") if args.mode == "both" else (mode_token(args.mode),)

    result = run_domain(
        "accounting",
        adapter.tasks(),
        args.k,
        adapter=adapter,
        prop=proposer,
        runs_root=adapter.spec.runs_root,
        library_root=root / "library" / f"k{args.k}",
        modes=modes,
    )
    result["substrate"] = adapter.substrate.name
    result["execution_count"] = adapter.execution_count
    result["editor_calls"] = len(proposer._calls)

    report = root / "agns_demo.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Agnes demo: {result['done']} tasks completed; {result['failed']} failed. {report}")
    return int(result["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
