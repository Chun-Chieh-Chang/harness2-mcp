# harness2-loop

A local Agnes Code **plugin** that turns the `harness2` integration into a
**continuous-improvement closed loop**. It re-runs the
`recipes/harness2-any-project.yaml` recipe automatically whenever a build/test
step fails or a commit lands, so the harness keeps refining the project over
time instead of waiting for a human to re-invoke it.

This is the fifth integration artifact on top of: the MCP server
(`mcp_server/harness2_mcp.py`), the recipe (`recipes/harness2-any-project.yaml`),
the custom agent (`.agents/agents/harness2-dev-agent.md`), and the skill
(`.agents/skills/harness2-develop/SKILL.md`).

## How it works (matches the official Agnes hooks model)

Hooks are discovered from a plugin's `hooks/hooks.json` and run as local
commands when a matching lifecycle event fires:

| File | Role |
|------|------|
| `plugin.json` | Manifest. Identifies the plugin (`name: harness2-loop`). |
| `hooks/hooks.json` | Maps events → commands. |
| `scripts/rerun_recipe.py` | The real runner (reads the payload, decides, spawns the detached re-run). |
| `scripts/rerun.cmd` | Windows fallback if the hook runner has no POSIX `sh -c`. |
| `config.json` | Per-machine knobs (recipe, params, cooldown, triggers, CLI). |
| `.state/` | Runtime logs + cooldown markers (created on first run). |

### Events used

| Event | Why |
|-------|-----|
| `PostToolUseFailure` | Fires after a tool call fails. `AfterShellExecution`/`AfterFileEdit` only fire on **success**, so a failed build must be caught here. No `matcher` → runs on every tool failure, filtered in-script to only build/test-looking commands. |
| `AfterShellExecution` with `matcher: ^git\s+commit` | Fires after a successful shell command that is a `git commit`. This is the commit trigger. |

A bare `"*"` matcher is **invalid** in Agnes (the whole rule is silently
skipped), so the build-failure rule deliberately omits `matcher` and does the
filtering in `rerun_recipe.py` instead.

### Payload → decision

The hook command receives the event payload on **stdin** (`event`,
`session_id`, `tool_name`, `tool_input.command`, `message`,
`working_dir`). `rerun_recipe.py`:

1. only fires on build/test signals for `build-failure`
   (`config.build_patterns`) and on `git commit` for `commit`;
2. applies a per-signal **cooldown** (`config.cooldown_seconds`, default 600s)
   so the recipe's own builds/commits do not re-trigger the loop;
3. launches `Agnes Code run --recipe <recipe> --params ...` as a **detached**
   background process and returns immediately.

The script is observation-only: it always exits `0` and never blocks the
session (a failing hook is logged by Agnes, not fatal).

## Flow diagrams

> **互動版（推薦）**：spec 級零依賴原生 SVG 全鏈路流程圖
> [.agnes/artifacts/flowcharts/harness2-loop-flowchart.html](../../.agnes/artifacts/flowcharts/harness2-loop-flowchart.html)
> （資料驅動格點 + 顯式路由 + ISO 5807 符號 + 滾輪縮放 / 拖曳平移 / ⛶ 全圖適配 / 🔝 起點置頂 + 內建幾何自審計徽章）。
> 三層審計管線：`node scripts/verify-flowchart-spec.js .agnes/artifacts/flowcharts/harness2-loop-flowchart.html`。
> 下方為等價 Mermaid 靜態版（無 Node 環境時可直接貼到支援 Mermaid 的維基 / GitHub）。

### Closed loop (whole system)

```mermaid
flowchart TD
    subgraph once["One-time setup (do once)"]
        A1["Open harness2 in Agnes Code (project window)"] --> A2["Agnes Code mcp harness2<br/>(harness2_* tools in session scope)"]
        A2 --> A3["Align config.json: cli / params / dry_run / cooldown"]
        A3 --> A4["Smoke test: feed a fake payload to rerun_recipe.py<br/>log must show 'launched: ...'"]
    end

    subgraph human["Human-driven"]
        H1["@harness2-dev-agent: develop / iterate the harness<br/>(skill picks bench / k / mode / substrate)"] --> H2["Change code / tune harness components"]
    end

    H2 --> E1{"build / test failed?"}
    H2 --> E2{"git commit succeeded?"}
    E1 -- yes --> F1["PostToolUseFailure event<br/>payload piped to hook via stdin"]
    E2 -- yes --> F2["AfterShellExecution<br/>matcher: ^git commit"]

    F1 --> G0
    F2 --> G0
    subgraph hook["harness2-loop plugin (background, never blocks session)"]
        G0["rerun_recipe.py decides"] --> G1{"signal matched?<br/>build patterns / git commit"}
        G1 -- no --> S1["logged to .state/harness2-loop.log<br/>exit 0"]
        G1 -- yes --> G2{"same-signal cooldown<br/>already hit (default 600s)?"}
        G2 -- yes --> S1
        G2 -- no --> G3["detached launch:<br/>Agnes Code run --recipe ...<br/>write cooldown stamp, exit 0"]
    end

    subgraph recipe["background recipe run"]
        G3 --> R1["harness2-setup"] --> R2["harness2-check"]
        R2 --> R3["harness2 run<br/>Propose-Probe-Compose"]
        R3 --> R4["harness2-judge<br/>same identity params"] --> R5["harness2-report"]
    end

    R5 --> O["runs/demo/.../judged.json<br/>runs_namespace = continuous"]
    O --> M{"Human review"}
    M -- "scores climbing" --> M1["keep k / mode, loop continues"]
    M -- "scores flat" --> M2["upgrade to k+1 sequential<br/>edit config.json params<br/>auto-applied at next commit"]
    M1 --> H2
    M2 --> H2
```

### Hook decision logic (every event)

```mermaid
flowchart LR
    P["stdin payload<br/>(event / tool_input / message)"] --> D{"signal type"}
    D -- "build-failure" --> B{"command matches<br/>config.build_patterns?"}
    D -- "commit" --> C{"command contains<br/>git commit?"}
    B -- no --> X["skip (logged)"]
    C -- no --> X
    B -- yes --> G{"trigger enabled<br/>in config?"}
    C -- yes --> G
    G -- no --> X
    G -- yes --> CD{"within cooldown for<br/>this signal (600s)?"}
    CD -- yes --> X
    CD -- no --> L["detached launch:<br/>Agnes Code run --recipe ..."] --> Z["exit 0<br/>(never blocks the session)"]
    X --> Z
```

Key point: every path ends in `exit 0` (observation-only). Worst case is "this re-run was skipped", never a blocked session. Blocking tool calls is a separate `PreToolUse` policy and must not be mixed into this plugin.

## Enable it

The plugin lives under the project plugins dir, so Agnes Code loads it
automatically when it starts from this project:

```
<project>/.Agnes Code/plugins/harness2-loop/
```

Verify detection (the name `harness2-loop` should appear):

```powershell
Get-ChildItem "<project>\.Agnes Code\plugins\harness2-loop" -Recurse
```

To **disable** it without deleting files, add its name to `disabledPlugins` in
the Agnes Code settings (project `<project>/.config/Agnes Code/settings.json`,
or user `~/.config/Agnes Code/settings.json`):

```json
{ "disabledPlugins": ["harness2-loop"] }
```

## Tuning

Edit `config.json`:

- `repo_root` / `recipe` – where the CLI runs and which recipe to re-run.
- `params` – the `--params` passed to the recipe (bench, k, mode, substrate,
  seed, dry_run, min_gain, model). Set `dry_run: "true"` to dry-run the loop.
- `cooldown_seconds` – guard against self-triggering (raise it if runs are long).
- `build_failure_trigger` / `commit_trigger` – switch each trigger on/off.
- `runs_namespace` – a stable namespace so loop runs share a judged namespace
  (keep it constant so results stay comparable).

## Troubleshooting

- Hook didn't run: confirm the plugin dir is under the *current* project, the
  event name is supported, the matcher regex is valid (no bare `*`), and the
  plugin is not in `disabledPlugins`.
- Hook runs but nothing re-triggers: check `.state/harness2-loop.log` for
  `no build/commit signal`, `within cooldown`, or `disabled in config`.
- A `PostToolUseFailure` hook that wants to *block* must print
  `{"decision":"block","reason":"..."}` to stdout; this plugin only observes,
  so it prints nothing and exits 0.
- Windows: if the hook runner cannot use `sh -c`, point the `command` in
  `hooks/hooks.json` at `scripts/rerun.cmd` instead of the python invocation.
