# Agnes × Harness² integration (local add)

Two seams, both wired: **Path B** (Agnes as substrate — verified runnable on
the Windows desktop with zero credentials) and **Path A** (Agnes as the frozen
model endpoint via an OpenAI-compatible bridge).

> Upstream Harness² targets Linux. The demo paths here are platform-agnostic
> Python, so they run on the Windows desktop; model-backed formal benchmarks
> still follow `docs/SETUP.md` (D1: not verified on this machine).

## One-click desktop runner (P1)

From the `harness2/` repo root:

```powershell
agns-desktop.bat        # double-click in Explorer, or run from PowerShell
```

It: loads `.agns_bridge.env` → ensures `pip install -e .` → runs
`harness2-agns-demo` (k=2, both modes) → prints + opens
`runs\agns_demo\agns_demo.json` in Explorer.

Linux/macOS equivalent: `bash agnes_bridge/run_agns_paths.sh all`
or `powershell -File agnes_bridge/run_agns_paths.ps1 all`.

## Executor priority (B3)

`AGNES_CLI` drives which rollout executor runs, in this order:

1. **`AGNES_CLI` set** → your real Agnes headless CLI/SDK. It is executed with
   `cwd` = a workspace containing the staged harness + `ledger.csv`, and env
   vars `AGNES_TASK` / `AGNES_WORKSPACE`. Contract: it may **write
   `answer.txt`** in that workspace **or print the answer to stdout**.
   (Both `AgnesSubstrate.execute` and `AgnesAdapter.execute` honor this.)
2. **`AGNES_CLI` empty** → bundled deterministic worker
   (`scripts/summarize.py`), fully reproducible, zero credentials.

Set it in `.agns_bridge.env` (loaded by the one-click runner) or export it in
your shell:

```powershell
$env:AGNES_CLI = "agnes run --headless"   # your actual Agnes non-interactive command
```

### Files changed for B3

- `harness2/substrate/agnes.py` — `_run_agnes_cli()` + executor-priority logic
- `harness2/agnes_demo.py` — `AgnesAdapter.execute()` honors `AGNES_CLI`
- `.agns_bridge.env` / `.agns_bridge.env.example` — `AGNES_CLI=` slot

## Path A — Agnes as the frozen model (A1)

Fill the endpoint slots in `.agns_bridge.env`:

```ini
AGNES_API_URL=https://YOUR-AGNES-ENDPOINT/v1
AGNES_API_KEY=YOUR-KEY
AGNES_MODEL=agnes
```

Then start the bridge in a second terminal (stdlib-only, no deps):

```powershell
python -m agnes_bridge.agnes_openai_proxy
# listens on http://127.0.0.1:8620/v1
```

Point harness2 at it:

```powershell
# OpenCode executor (default)
$env:OPENAI_BASE_URL="http://127.0.0.1:8620/v1"; $env:OPENAI_API_KEY="agnes-bridge"
$env:HARNESS2_SOLVER_MODEL="openai/agnes"; $env:HARNESS2_IMPROVER_MODEL="openai/agnes"
$env:HARNESS2_JUDGE_MODEL="agnes"
python -m harness2.cli.run_sweep --bench jb --substrate oc --k 1 --mode parallel

# or Codex executor
$env:HARNESS2_CODEX_BASE_URL="http://127.0.0.1:8620/v1"; $env:HARNESS2_CODEX_API_KEY="agnes-bridge"
python -m harness2.cli.run_sweep --bench jb --substrate cx --k 1 --mode parallel
```

## Path B — Agnes as a substrate

- `harness2/substrate/agnes.py` — `AGNES_SURFACE` (c1..c8 → Agnes filenames)
  + `AgnesSubstrate` (`surface/materialise/execute/read_trajectory/preflight`).
- `harness2/substrate/__init__.py` — exports `AgnesSubstrate`.
- `harness2/agnes_demo.py` — `AgnesAdapter` + `AgnesDemoProposer`.
- `harness2/cli/agns_demo.py` — the `harness2-agns-demo` entrypoint.
- `harness2/cli/_common.py` — `ags` in `SUBSTRATES`.
- `harness2/core/spec.py` — `agn_workspace` in `INSTALL_MODES`.
- `harness2/core/prompts.py` — `agnes` prompt surface registered.
- `harness2/core/schedule.py` — Windows-safe `flock` fallback.

Run:

```powershell
python -m harness2.cli.agns_demo --k 2 --mode both
# verified: 2/2 tasks ok, 28 executions, 56 editor calls, 0 failures
```

## What "接 Agnes" means concretely

- **Path A** = use Agnes's *model*; Harness² improves the harness around it.
- **Path B** = Agnes *is* the harness target; Harness² recursively rewrites
  Agnes's system prompt / guardrails / memory / tool guidance / subagents /
  skills / scripts / plugins.
