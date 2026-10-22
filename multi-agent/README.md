# harness2-loop across agents (multi-agent adapters)

The continuous-improvement closed loop is **not tied to Agnes Code**.
It is a *flag + two drain paths* design, and that design can sit on top of
**any coding agent** — as long as the agent either (a) can call an MCP tool,
or (b) uses git, or (c) a scheduler runs on the box.

This directory ships three layers of adapters so you can turn the loop on
under opencode, Antigravity IDE, WorkBuddy, Qoder, Trae, Cline, Kiro, and
MiniMax Code (and, by extension, Claude / Cursor / anything else).

## The three universal layers

| Layer | Trigger | Works on | Drains via |
|---|---|---|---|
| **1 · git hook** | `git commit` in any project | **every agent that uses git** (all of them) | MCP `harness2_requeue` or scheduled `drain_requeue.py` |
| **2 · MCP tool** | agent calls `harness2_requeue` in-session | any agent with MCP support | same tool is the drain |
| **3 · scheduler** | periodic cron / Task Scheduler | **any OS**, agent-agnostic | `drain_requeue.py` |

Layer 1 is the key insight: **git hooks are agent-agnostic**. Install the
hook once per project and every commit writes the flag — you don't need that
agent to "support harness2-loop" at all.

### Files

```
multi-agent/
├── adapters/
│   ├── git/
│   │   ├── post-commit.sh          # writes pending_re.json on every commit
│   │   └── install.sh              # copies post-commit.sh into .git/hooks/
│   ├── build-failure/
│   │   └── record-build-failure.sh # manual one-liner for failing builds
│   ├── mcp/                        # one mcpServers block per agent
│   │   ├── opencode.mcp.json
│   │   ├── antigravity.mcp.json
│   │   ├── workbuddy.mcp.json
│   │   ├── qoder.mcp.json
│   │   ├── trae.mcp.json
│   │   ├── cline.mcp.json
│   │   ├── kiro.mcp.json
│   │   └── minimax.mcp.json
│   ├── opencode/
│   │   └── quickstart.sh          # one-line autopilot for opencode
│   ├── common.sh                  # shared helpers (find python, paths, json merge)
│   ├── quickstart.sh              # ONE dispatcher for all 8 agents (sh)
│   ├── zero-touch-setup.py        # global installer — the SSOT (cross-platform Python)
│   ├── zero-touch-setup.cmd       # double-click launcher (Windows, no bash needed)
│   └── zero-touch-setup.sh        # thin wrapper: prefers Python, falls back to sh
└── README.md                       # this file
```

## Autopilot (no manual steps)

### One-line per agent — `quickstart.sh` dispatcher

One script covers **all 8 agents** (git hook + that agent's MCP config +
60-minute scheduler). No more per-agent variants to maintain:

```sh
# list supported agents + where each MCP file lands
bash multi-agent/adapters/quickstart.sh --list

# set up a specific agent for a specific project
bash multi-agent/adapters/quickstart.sh opencode /path/to/your-project
bash multi-agent/adapters/quickstart.sh cline    /path/to/another-project
```

Each run is **idempotent** (re-running never duplicates) and **non-destructive**
(existing JSON is merged, not clobbered). After one run, every commit in that
project auto-writes the flag; the agent drains in-session, the scheduler
drains off-session. **Nothing else to type.**

| Agent | MCP file written | JSON shape |
|---|---|---|
| opencode | `<project>/opencode.json` | `mcp.harness2` (type:local + command array) |
| cline / trae / qoder / kiro / antigravity / minimax | `<project>/.<agent>/mcp.json` | `mcpServers.harness2` |
| workbuddy | `~/.workbuddy/mcp.json` | `mcpServers.harness2` (no documented project path) |

### Truly zero-touch — `zero-touch-setup.py` (run ONCE, then never)

If you want **no per-project, per-agent setup at all**, install the global
version. The installer is **cross-platform Python** (no bash required), so on
Windows you do *not* need git-bash on your PATH:

```powershell
# Windows — double-click, or run:
.\multi-agent\adapters\zero-touch-setup.cmd
# or any OS, from the repo:
python multi-agent/adapters/zero-touch-setup.py
```

What that single command does, permanently:

1. **Git global hook** — builds `~/.harness2-loop-template` (git's built-in
   template *plus* our `hooks/post-commit`, so no default `.sample` hook is
   lost) and sets `git config --global init.templatedir` to it. Every new
   `git init` then copies `post-commit` into `.git/hooks/`. No per-project
   install, no bash needed.
2. **One scheduler** — a 60-min cron / Task Scheduler job runs
   `drain_requeue.py` (pure Python) off-session, forever.
3. **Any MCP agent** — in-session drains via `harness2_requeue` as before.

Result: you **never run a quickstart again** — commit anywhere, it
auto-triggers, the scheduler auto-drains.

**Blast radius**: every *new* git repo on this machine gets the hook. To
opt a specific project out: create `<project>/HARNESS2_LOOP_OFF`. To undo
everything: `python multi-agent/adapters/zero-touch-setup.py --uninstall`.

> **Note for pre-existing repos** (created before the install, like this one):
> run `git init` inheritance only covers *new* repos. For an existing repo,
> copy the hook once:
> `copy ~\.harness2-loop-template\hooks\post-commit <repo>\.git\hooks\post-commit`.
>
> **Recommended default**: start with the per-project dispatcher
> (`quickstart.sh` / `.cmd`). Use zero-touch only when you truly want it
> machine-wide.

## Per-agent quickstart

For each agent, do **two** things: (1) install the git hook so commits
trigger, (2) add its MCP block so the agent can drain in-session.

### 1. Install the universal git trigger (do this once per project)

```sh
# from the harness2 repo
sh multi-agent/adapters/git/install.sh /path/to/your-project
```

Every `git commit` in that project now writes a flag. To also catch a
failing build without a native hook, run it manually:

```sh
(cargo test || sh /path/to/harness2/multi-agent/adapters/build-failure/record-build-failure.sh cargo test)
```

### 2. Add the agent's MCP block (so `harness2_requeue` is callable)

Each file under `adapters/mcp/` is a **fragment** to merge into that
agent's own MCP config. The exact target location differs per agent:

| Agent | MCP config location | Notes |
|---|---|---|
| **opencode** | `opencode.json` → `mcp.harness2` | use `type:"local"` + `command` array; **or run `adapters/opencode/quickstart.sh` (one-line autopilot)** |
| **Cline** | `~/.cline/mcp.json` or VS Code → Cline panel → MCP Servers | standard `mcpServers` block; CLI vs extension |
| **Trae** | `<project>/.trae/mcp.json` | project-scoped, commitable |
| **Qoder** | Qoder CLI / IDE MCP settings (stdio/sse/http) | stdio block shown |
| **Antigravity** | Antigravity MCP settings | MCP supported natively |
| **Kiro** | `.kiro/` MCP config **or Kiro powers/hooks** | Kiro also has native hooks — see below |
| **MiniMax Code** | MiniMax Code MCP settings (`mcpServers`) | local stdio block |
| **WorkBuddy** | no documented MCP path | **prefer Layer 1 (git) + Layer 3 (scheduler)**; add MCP block only if you confirm it supports it |

> These fragment files use the `mcpServers` shape that Claude Desktop /
> Cursor / Trae / Cline / MiniMax share. opencode uses `mcp` with a
> `command` array. Kiro and WorkBuddy may use different key names — confirm
> against their current docs before pasting; the *server* (python
> `-m mcp_server.harness2_mcp`) is identical everywhere.

### 3. (Optional) scheduled drain for agents that won't stay open

If an agent won't have a session open at the moment the flag is written,
the scheduler picks it up (this is agent-agnostic):

```sh
# Windows Task Scheduler (every 60 min)
schtasks /create /sc minute /mo 60 /tn harness2-loop-drain ^
  /tr "python \"E:\Self-developed_Apps\G3\harness2\mcp_server\..\..\harness2-loop\scripts\drain_requeue.py\""

# macOS / Linux cron
0 */1 * * * * python /path/to/.Agnes Code/plugins/harness2-loop/scripts/drain_requeue.py
```

(Kiro note: it has **native hooks + powers**, so you can also wire
`post-commit` / failed-task events directly — the flag file and drain
script stay the same; only the trigger differs.)

## What all agents share

Regardless of agent, the loop is:

```
commit / build-failure
        ↓
write .state/pending_re.json   (layer 1 git hook, or layer 2/3)
        ↓
drain → harness2 setup→check→run→judge→report   (harness2_requeue or drain_requeue.py)
        ↓
runs/…/judged.json   →  you review, bump k/mode, next commit
```

The agent only decides **when** the drain happens (in-session via MCP, or
off-session via scheduler). The harness2 pipeline and the flag file are
agent-independent.

## Honest caveats

- **MCP key names / config paths differ per agent and change over time.**
  Each fragment above is a *starting point*; verify the exact key against
  that agent's current docs before trusting it.
- **WorkBuddy** has no documented MCP surface — the git hook + scheduler
  layers are the reliable path there.
- The git hook writes to the **global** plugin `.state/` dir by default
  (`~/.Agnes Code/plugins/harness2-loop/.state`); override with
  `HARNESS2_LOOP_FLAG_DIR` if you keep the plugin elsewhere.
- `cwd` / `HARNESS2_REPO` in each fragment points at the harness2 repo on
  **this machine** — update to your own path.
