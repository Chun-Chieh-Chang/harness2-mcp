---
name: harness2-develop
description: >
  Develop or refine an agent harness for any project with Harness². Use when
  the user asks to improve an agent's harness, run a Harness² sweep, pick the
  right benchmark (jb/lab/wb/demo/ags-demo), read sweep results under runs/,
  or start the harness2→Agnes Code automation (MCP tools, recipe, agent).
---

# Harness² Development Workflow

Teach Agnes Code to pick the right Harness² inputs for an arbitrary project and
to read its outputs correctly. One skill, one workflow.

## 1. Pick the benchmark family

| Situation | `--bench` | Notes |
|---|---|---|
| Validate the pipeline itself, zero credentials | `demo` or `ags-demo` | `harness2-demo --output runs/demo --k 2`; `harness2-agns-demo --k 2 --mode both`. Path B (`ags`) needs no keys when `AGNES_CLI` is empty (bundled deterministic worker). |
| Professional work tasks | `jb` | `harness2-setup jb` first; needs GCloud + pinned runners. |
| Legal work | `lab` | Needs Pandoc + Poppler on the runner host. |
| Office / web / code | `wb` | Add `--subset office|web|code` to **every** command after setup; needs Docker. |

Model-backed benches need the model configured (Path A: `.agns_bridge.env`
→ `python -m agnes_bridge.agnes_openai_proxy`, then point
`OPENAI_BASE_URL`/`HARNESS2_SOLVER_MODEL` at it; Path B: `AGNES_CLI`).
Formal benches assume Linux per `docs/SETUP.md`; demo paths are
platform-agnostic.

## 2. Order of operations (never skip the cheap checks)

1. `harness2-setup <bench>` — install runners/dependencies once.
2. `harness2-check --bench <bench>` — preflight; cheap, offline.
3. `harness2 --bench <bench> --k 1 --mode parallel [--dry-run]` — start with
   `k=1` and `--max-tasks` small; costs money when not `--dry-run`.
4. `harness2-judge --bench <bench> --k 1 --mode parallel` — **same identity
   as the run** (bench, subset, k, mode, seed, substrate), otherwise the
   namespace doesn't match and judging refuses or reads the wrong run.
5. `harness2-report --bench <bench> --k 1 --mode parallel` — same identity.

## 3. Scaling knobs

- `--k K --mode parallel`: probe K general + K domain candidates, compose K
  refinements (wider).
- `--k K --mode sequential`: carry the refined harness through K steps
  (deeper).
- `--substrate oc|cx`: executor (OpenCode default, or Codex). `ags` is the
  Agnes substrate for demo paths.
- Re-running the same command resumes from `runs/`; a new
  `HARNESS2_RUNS_DIR` is required when changing models or task selection.

## 4. Reading results

- `runs/<bench>/` holds task summaries, deliverables, adopted harnesses,
  reflection notes, evaluation rows (`judged.json`), and report outputs.
- A failed judge is `score=None`, never a zero — do not read it as a
  regression.
- If the improved score does not beat the base, the next move is one
  sequential pass with `k+1`, not a second parallel pass at the same k.

## 5. Wiring into Agnes Code automation

- Tools: `harness2_*` via the `harness2-mcp` extension
  (`python -m mcp_server.harness2_mcp`); enable with `Agnes Code mcp harness2`.
- Repeatable flow: `recipes/harness2-any-project.yaml` (run or schedule via
  `Agnes Code schedule add`).
- Role: the `harness2-dev-agent` custom agent (`.agents/agents/`) decides
  bench/k/mode/substrate per project and enforces the ordering above.
- Continuous loop: the `harness2-loop` plugin
  (`.Agnes Code/plugins/harness2-loop/`) re-runs the recipe on
  `PostToolUseFailure` (failed build/test) and `AfterShellExecution`
  (`git commit`), detached, with a cooldown so it can't self-trigger. Loaded
  automatically for this project; disable via `disabledPlugins:
  ["harness2-loop"]` in Agnes Code settings; tune in the plugin's
  `config.json` (recipe, params, `cooldown_seconds`, `runs_namespace`).
  See the plugin's `README.md` for the exact event semantics.
