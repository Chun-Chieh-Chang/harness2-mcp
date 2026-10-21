"""Minimal example of a working AGNES_CLI implementation.

Contract (as documented in agnes_bridge/README.md):
  - Runs with cwd = a staged workspace containing the harness + ledger.csv
  - Env vars AGNES_TASK (task id) and AGNES_WORKSPACE (workspace path) are set
  - Must write `answer.txt` in the workspace OR print the answer to stdout

This stub does a simple ledger total and writes answer.txt.

Usage (in .agns_bridge.env):
  AGNES_CLI=python /path/to/fake_agnes_cli_example.py

Replace with your actual Agnes headless CLI command for production use.
"""

import os
import sys
import csv
from decimal import Decimal

def main() -> None:
    ws = os.environ.get("AGNES_WORKSPACE")
    task = os.environ.get("AGNES_TASK", "(unknown)")
    if not ws or not os.path.isdir(ws):
        print(f"[fake-agnes] AGNES_WORKSPACE not set or missing: {ws!r}")
        sys.exit(1)

    ledger_path = os.path.join(ws, "ledger.csv")
    if not os.path.exists(ledger_path):
        print(f"[fake-agnes] ledger.csv not found in {ws}")
        sys.exit(1)

    with open(ledger_path, newline="") as f:
        total = sum((Decimal(row["amount"]) for row in csv.DictReader(f)), Decimal(0))

    answer = f"Total: {total:.2f}"
    # Write to answer.txt AND print (contract allows either or both)
    with open(os.path.join(ws, "answer.txt"), "w") as out:
        out.write(answer)
    print(f"[fake-agnes] task={task} answered {total}")

if __name__ == "__main__":
    main()
