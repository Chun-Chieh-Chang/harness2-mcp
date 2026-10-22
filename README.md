<h3 align="center">
  <img src="assets/Harness2-wordmark.png" alt="Harness²" width="360"><br>
  Recursive Agent Harnessing for an Open World
</h3>

<p align="center">
  <a href="https://arxiv.org/pdf/2610.14224"><img src="https://img.shields.io/badge/Paper-arXiv-EA4335?logo=arxiv&logoColor=white" alt="Paper"></a>
  <a href="https://harness2.github.io"><img src="https://img.shields.io/badge/Website-harness2.github.io-4285F4?logo=googlechrome&logoColor=white" alt="Website"></a>
  <a href="docs/BENCHMARKS.md"><img src="https://img.shields.io/badge/Docs-Benchmark%20guides-FBBC04" alt="Benchmark guides"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-34A853" alt="License"></a>
</p>

<p align="center">
  <a href="docs/BENCHMARKS.md#jobbench">
    <img src="assets/harness2-setup.gif" alt="Install, set up, and run JobBench: uv pip install -e '.[render]', harness2-setup jb, then harness2 --bench jb --k 1 --mode parallel. Click for prerequisites and commands." width="640">
  </a>
</p>

A **harness** is the system around a model that enables it to act as an agent:
prompts, tools, memory, skills, orchestration, and more. **Harnessing** is the
process of optimizing that system.

Harness² is a plug-and-play framework for **recursive agent harnessing** in an
open world, where agents encounter tasks unseen during harness design. It
connects two levels of recursion while keeping model weights fixed:

* **Task-level recursion** refines the execution harness for the current task
  through a contrastive **Propose–Probe–Compose** step: propose edits, probe
  their effects on the same task, and compose a refined harness from behavioral
  contrasts between executions, without ground-truth feedback.
* **Harnessing-level recursion** updates a persistent *improvement harness*
  with adopted harnesses and evidence-supported lessons from each task to guide
  future refinement.

<p align="center">
  <a href="assets/harness2_pipeline.png">
    <img src="assets/harness2_pipeline.png" alt="Harness² pipeline. Task-level recursion: an agent executor runs the initial harness, a harness editor proposes invariant and domain edits, candidate probes execute them, and a harness composer combines them into the final harness. Harnessing-level recursion: an experience reflector reflects on the step and updates the improvement harness used for the next task." width="100%">
  </a>
</p>

Across three professional benchmarks and four model–harness configurations, a
single Harness² step improves GLM-5 and Gemini 3.5 Flash over their base
harnesses, with gains of up to 11.5 points on WorkBuddy-Bench, 4.5 points on
JobBench, and 11.8 percentage points on LAB's partial pass rate. Increasing the
task-level recursion budget brings further gains.

The release supports **parallel and sequential recursion**, **OpenCode and
Codex executors**, and **JobBench, LAB, and WorkBuddy-Bench**.

## Video overview

https://github.com/user-attachments/assets/76b10548-b14b-4c8f-9aa5-a93662df4d56

## Contents

- [Video overview](#video-overview)
- [Harness components](#harness-components)
- [Install](#install)
- [Run a benchmark](#run-a-benchmark)
- [Agnes Code integration](#agnes-code-integration)
- [Multi-agent adapters](#multi-agent-adapters)
- [Experiments](#experiments)
- [Web access](#web-access)
- [Results and resume](#results-and-resume)
- [Citation](#citation)
- [Contributing](#contributing)
- [License](#license)
- [Disclaimer](#disclaimer)

## Harness components

Harness² exposes eight editable components around the model: **system prompt,
guardrails, memory, tool guidance, subagents, skills, scripts, and plugins**.
They control context construction, the tool interface, delegation, and behavior
inside the tool loop.

<p align="center">
  <a href="assets/components.png">
    <img src="assets/components.png" alt="Eight harness components grouped by runtime role: system prompt, guardrails, memory, and skills construct context; tool guidance and scripts define the tool interface; subagents orchestrate delegated work; plugins control middleware." width="100%">
  </a>
</p>

## Install

Use **Linux, Python 3.12, and [uv](https://docs.astral.sh/uv/getting-started/installation/)**.
From the repository root:

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e '.[render]'
harness2-demo --output runs/demo --k 2
```

The local demo runs both recursion modes with deterministic editors and real
Python executions. It requires no model credentials.

For model-backed benchmarks, install **Node.js 20+, the Google Cloud CLI**, and
the [benchmark dependencies](docs/SETUP.md#requirements). LAB needs Pandoc and
Poppler; WorkBuddy-Bench needs Docker. Then configure your models:

```bash
cp .env.example .env
# Edit .env with your Vertex AI project and model IDs.
gcloud auth application-default login
```

See the [setup guide](docs/SETUP.md) for model settings, authentication
alternatives, and the [Codex executor](docs/SETUP.md#codex-executor).

## Run a benchmark

The following example installs LAB and runs one task, then evaluates and reports
its result. Model-backed runs incur API costs; start with a small task selection.

```bash
harness2-setup lab
harness2-check --bench lab
harness2 --bench lab --k 1 --mode parallel \
  --only-domains antitrust-competition --max-tasks 1
harness2-judge --bench lab --k 1 --mode parallel
harness2-report --bench lab --k 1 --mode parallel
```

Sequential recursion runs the same commands with `--mode sequential`. `--k` is
the task-level recursion budget; see [Experiments](#experiments). Judging and
reporting must use the same benchmark, executor, subset, `--k`, `--mode`, and
seed as the refinement run. Add `--dry-run` to `harness2` to preview task
selection without model calls.

| Benchmark | Tasks | Install | Guide |
|---|---|---|---|
| JobBench | Professional work | `harness2-setup jb` | [JobBench](docs/BENCHMARKS.md#jobbench) |
| LAB | Legal work | `harness2-setup lab` | [LAB](docs/BENCHMARKS.md#lab) |
| WorkBuddy-Bench | Office, web, and code | `harness2-setup wb` | [WorkBuddy](docs/BENCHMARKS.md#workbuddy-bench) |

Choose one benchmark per command. WorkBuddy also takes `--subset office`,
`--subset web`, or `--subset code` on every command after setup. The
[benchmark guides](docs/BENCHMARKS.md) cover each one's data, domains, and
grading.

## Agnes Code integration

Harness2 can be run as a built-in, auto-triggering tool inside [Agnes
Code](https://github.com/AgnesCode) instead of being invoked by hand. The
integration layer is **independent of the benchmark code** — it lives under
`mcp_server/`, `recipes/`, `.agents/`, `.Agnes Code/`, and
`scripts/verify-flowchart-spec.js`, and it drives the eight
`harness2-*` CLI entry points through an OpenAI-compatible bridge
([agns_bridge/](agns_bridge/README.md)) so that any project (bench `demo`,
`ags-demo`, `jb`, `lab`, or `wb`) can be continuously improved without
leaving the editor.

### The five integration assets

| Asset | Path | Role |
|---|---|---|
| MCP server | [`mcp_server/harness2_mcp.py`](mcp_server/harness2_mcp.py) | Zero-dependency stdio JSON-RPC server; exposes 9 `harness2_*` tools wrapping the CLI + 2 `agns_bridge_*` helpers. |
| Recipe | [`recipes/harness2-any-project.yaml`](recipes/harness2-any-project.yaml) | Repeatable / schedulable `setup → check → run → judge → report` flow with structured `json_schema` output and cross-platform retry. |
| Custom agent | [`.agents/agents/harness2-dev-agent.md`](.agents/agents/harness2-dev-agent.md) | Reusable role that picks `bench` / `k` / `mode` / `substrate` and enforces the ordering above. |
| Skill | [`.agents/skills/harness2-develop/SKILL.md`](.agents/skills/harness2-develop/SKILL.md) | On-demand knowledge: bench selection, order of operations, scaling knobs, reading results, wiring into automation. |
| Hooks plugin | [`.Agnes Code/plugins/harness2-loop/`](.Agnes Code/plugins/harness2-loop/) | Continuous-improvement closed loop: on `PostToolUseFailure` (failed build/test) or `AfterShellExecution` (successful `git commit`), writes a pending trigger flag; the flag is drained by MCP `harness2_requeue` (in-session, path B) or `drain_requeue.py` (scheduled, path C). |

### Interactive full-chain flowchart

A **zero-dependency native SVG + vanilla JS** flowchart — data-driven grid
layout, explicit routing, ISO 5807 / ANSI shapes, cursor-anchored zoom,
pointer-capture panning, and an in-browser geometry self-audit badge. It also
carries a structured 9-section plain-language documentation panel (event
semantics, decision chain, file layout, enable/disable, tuning, logs,
troubleshooting, role split).

[`harness2-loop-flowchart.html`](.agnes/artifacts/flowcharts/harness2-loop-flowchart.html)

Run the three-layer audit pipeline (requires Node.js):

```bash
node scripts/verify-flowchart-spec.js .agnes/artifacts/flowcharts/harness2-loop-flowchart.html
```

### Activation steps

```powershell
# 1. The harness2-loop plugin is auto-loaded from the project dir
#    (<project>/.Agnes Code/plugins/harness2-loop/) when Agnes Code opens
#    this project — no install step. Confirm it is detected:
Get-ChildItem ".Agnes Code\plugins\harness2-loop" -Recurse
#    (For use in ANY project, install it globally once — see "Global install"
#     in .Agnes Code/plugins/harness2-loop/README.md.)

# 2. One-time smoke test of the hook chain (no model calls, no cost):
#    feed a fake build-failure payload; the log must show a flag was written.
'{"event":"PostToolUseFailure","tool_input":{"command":"cargo test"}}' |
  python ".Agnes Code/plugins/harness2-loop/scripts/rerun_recipe.py" build-failure
Get-Content ".Agnes Code/plugins/harness2-loop/.state/harness2-loop.log" -Tail 5

# 3. (No external CLI needed) The hook only writes a pending flag;
#    the re-run is drained either in-session (MCP harness2_requeue) or
#    off-session (scheduled drain_requeue.py). See the flag protocol below.

# 4. (Optional, path C) register a periodic off-session drain.
#    On Windows, use Task Scheduler to run the drain script every N minutes:
schtasks /create /sc minute /mo 60 /tn harness2-loop-drain `
  /tr "python ""E:\Self-developed_Apps\G3\harness2\.Agnes Code\plugins\harness2-loop\scripts\drain_requeue.py"""
#    On Linux/macOS: add a cron entry calling the same drain_requeue.py.
```

To disable the hook loop without deleting files, add the plugin name to
`disabledPlugins` in the Agnes Code settings (project
`<project>/.config/Agnes Code/settings.json`, or user
`~/.config/Agnes Code/settings.json`):

```json
{ "disabledPlugins": ["harness2-loop"] }
```

### Continuous-improvement closed loop

Desktop Agnes Code has no headless CLI binary, so the hook **does not spawn
a process** — it records the trigger as a flag file, and one of two drain
paths executes the pipeline:

```
change harness / code
        ↓
build / test fails          OR          git commit succeeds
        ↓                                  ↓
PostToolUseFailure                     AfterShellExecution
(matcher: ^git\s+commit)
        └──────────────┬──────────────┘
                       ↓
        rerun_recipe.py decision chain
        (signal? → enabled? → cooldown? → write flag, exit 0)
                       ↓
              .state/pending_re.json
                       ↓
        ┌──────────────┴──────────────┐
        ↓                             ↓
  B · in-session                C · scheduled
  MCP harness2_requeue          drain_requeue.py
  (agent drains in Agnes       (Task Scheduler / cron
   session; explicit args      drains off-session; runs
   win over flag params)       via python -m harness2.cli.*)
        └──────────────┬──────────────┘
                       ↓
        setup → check → run → judge → report
        (runs/<bench>/…/judged.json, runs_namespace = continuous)
                       ↓
        human review → keep k/mode  OR  upgrade to k+1 sequential
                       ↓
        next commit / next failure → loop
```

The loop is **event-driven**: hooks record build/commit triggers; drain
path **B** (MCP tool in an open Agnes session) or **C** (periodic scheduler)
consumes the flag and runs the recipe. B and C share the same flag file and
are naturally mutually exclusive (first to drain wins), so no run is
duplicated.

See the [handoff doc](handoff.md) for a full status of what has been done,
what is still pending, and the known caveats.

## Multi-agent adapters

The closed loop is **not tied to Agnes Code**. It is a *flag + two drain
paths* design, which can sit on top of **any coding agent**. The
`multi-agent/` tree ships three agent-agnostic layers plus per-agent MCP
fragments:

| Layer | Trigger | Works on |
|---|---|---|
| **1 · git hook** | `git commit` in any project | every agent that uses git (all of them) |
| **2 · MCP tool** | agent calls `harness2_requeue` in-session | any agent with MCP support |
| **3 · scheduler** | cron / Task Scheduler | any OS, agent-agnostic |

Layer 1 is the key: **git hooks are agent-agnostic** — install once per
project and every commit writes the flag; the agent never needs to "support
harness2-loop".

```
multi-agent/
├── README.md                 # mapping + per-agent quickstart + caveats
├── adapters/git/
│   ├── post-commit.sh         # writes pending_re.json on every commit
│   └── install.sh            # copies the hook into <project>/.git/hooks/
├── adapters/build-failure/
│   └── record-build-failure.sh  # manual one-liner for failing builds
└── adapters/mcp/             # one mcpServers block per agent
    ├── opencode.mcp.json     antigravity.mcp.json  workbuddy.mcp.json
    ├── qoder.mcp.json        trae.mcp.json          cline.mcp.json
    ├── kiro.mcp.json         minimax.mcp.json
```

Quickstart:

```sh
# 1) install the universal git trigger into any project
sh multi-agent/adapters/git/install.sh /path/to/your-project

# 2) (optional) catch a failing build manually
(cargo test || sh multi-agent/adapters/build-failure/record-build-failure.sh cargo test)

# 3) (optional) add your agent's MCP block from multi-agent/adapters/mcp/
```

Works under **opencode, Antigravity IDE, WorkBuddy, Qoder, Trae, Cline,
Kiro, and MiniMax Code** (and by extension Claude / Cursor / others). See
[`multi-agent/README.md`](multi-agent/README.md) for the per-agent config
locations and honest caveats (per-agent MCP key names change; WorkBuddy has
no documented MCP surface, so prefer layers 1 + 3).

## Experiments

Scale task-level recursion in two ways: **parallel recursion** explores multiple
candidate harnesses and composes refinements from their execution evidence;
**sequential recursion** carries the refined harness and accumulated evidence
through successive Propose–Probe–Compose steps.

<p align="center">
  <a href="assets/harness2_recursion_modes.png">
    <img src="assets/harness2_recursion_modes.png" alt="Two ways to scale task-level recursion. Parallel: probe k general and k domain-specific candidate harnesses, then produce k compositions from the shared evidence. Sequential: carry the refined harness and accumulated evidence through k Propose–Probe–Compose steps." width="100%">
  </a>
</p>
<p align="center"><em>Parallel recursion explores wider; sequential recursion refines deeper.</em></p>

| Option | Behavior |
|---|---|
| `--k 1` | One Propose–Probe–Compose step |
| `--k K --mode parallel` | Probe `K` general and `K` domain-specific candidates, then produce `K` compositions |
| `--k K --mode sequential` | Refine the harness through `K` successive steps |
| `--substrate cx` | Use Codex instead of the default OpenCode executor |

After each task, harnessing-level recursion retains the adopted harness and
evidence-supported lessons to guide future refinement. See the
[experiment guide](docs/EXPERIMENTS.md) for task selection, concurrency,
reproducibility, and baseline comparisons.

## Web access

Executor network access is unrestricted, and Codex runs with its sandbox
disabled. Public benchmark rubrics may be accessible online. Before evaluation,
configure [network restrictions](docs/EXPERIMENTS.md#web-access) to prevent
access to benchmark answers and grading criteria.

## Results and resume

Results are saved under `runs/`, organized by benchmark and subset where
applicable. They include task summaries, deliverables, adopted harnesses,
reflection notes, and evaluation results.

Repeat the same command to resume. Use a new `HARNESS2_RUNS_DIR` when changing
models or task selection. See [results and resume](docs/EXPERIMENTS.md#results-and-resume)
for details; each command also supports `--help`.

## Citation

```bibtex
@article{xu2026harness2,
  title   = {Harness$^2$: Recursive Agent Harnessing for an Open World},
  author  = {Xu, Ruiyao and Chen, Yanfei and CuiZhu, Zhongying and Dalvi Mishra, Bhavana and Ming, Yifei and Yu, Han and Han, Rujun and Lee, Chen-Yu and Pfister, Tomas},
  journal = {arXiv preprint arXiv:2610.14224},
  year    = {2026},
  url     = {https://arxiv.org/abs/2610.14224}
}
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Harness² is licensed under [Apache 2.0](LICENSE). Third-party code under
[`third_party/`](third_party/README.md), benchmarks, and datasets retain their
upstream licenses; see
[third-party notices](dependencies/README.md).

## Disclaimer

This is not an officially supported Google product. This project is not eligible
for the [Google Open Source Software Vulnerability Rewards Program](https://bughunters.google.com/open-source-security).
