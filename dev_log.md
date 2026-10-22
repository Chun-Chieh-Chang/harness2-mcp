# dev log — harness2 × Agnes Code integration

Chronological log of the integration work. Newest at the bottom.
Each entry: **date · what · why · verification**.

---

## 2026-10-21

### 09:xx — initial integration plan
- **What**: explored the harness2 repo (8 CLI entry points, 8 harness
  components, two recursion modes, benches `jb`/`wb`/`lab` + `demo`).
- **Why**: make harness2 a built-in, auto-runnable Agnes Code tool for
  arbitrary projects.
- **Refs**: official Agnes Code docs — using-extensions, session-recipes,
  recipe-reference, custom-agents, using-skills, hooks (cached under
  `.agnes/cache/docs*/`).

### 10:xx — MCP server (asset 1)
- **What**: `mcp_server/harness2_mcp.py` (381 lines) + `__init__.py`.
- Zero-dep stdio JSON-RPC; 9 `harness2_*` tools + 2 `agns_bridge_*`
  helpers; REPO_ROOT from `HARNESS2_REPO` or `parents[1]`.
- **Verification**: `python -c "import ast; ast.parse(...)"` OK.

### 11:xx — recipe (asset 2)
- **What**: `recipes/harness2-any-project.yaml` (170 lines).
- setup→check→run→judge→report; structured `json_schema` output;
  cross-platform retry; self-contained stdio extension block.
- **Verification**: field-by-field against `recipe-reference.md`
  (no PyYAML on this box → not machine-parsed).

### 12:xx — custom agent + skill (assets 3 & 4)
- **What**: `.agents/agents/harness2-dev-agent.md` (50 lines);
  `.agents/skills/harness2-develop/SKILL.md` (70 lines).
- **Why**: role (agent) vs on-demand knowledge (skill); project-scope so
  Agnes auto-discovers them in this repo.

### 13:xx — hooks plugin (asset 5)
- **What**: `.Agnes Code/plugins/harness2-loop/` — `plugin.json`,
  `hooks/hooks.json`, `scripts/rerun_recipe.py`, `scripts/rerun.cmd`,
  `config.json`, `README.md`, `.state/`.
- **Events**: `PostToolUseFailure` (failed build/test — `AfterShellExecution`
  only fires on success, so failures must be caught here) +
  `AfterShellExecution` with `matcher: ^git\s+commit`.

### 14:xx — flowchart (visual asset)
- **What**: `.agnes/artifacts/flowcharts/harness2-loop-flowchart.html`
  (single-file, zero-dependency native SVG + vanilla JS, per flowchart-spec).
  Data-driven grid, explicit routes, ISO 5807 shapes, cursor-anchored zoom,
  pointer-capture pan, in-browser geometry self-audit badge.
- **Verification**: JS brace/bracket balance, tag balance, 38 unique
  node/edge ids, edge ref integrity (Node 3-layer pipeline not run — no
  Node on this box).

### 15:xx — docs (README + handoff)
- **What**: README `## Agnes Code integration` section; created
  `handoff.md` (assets table, P1–P5, known limits, 5 quick commands).

---

## 2026-10-21 (later) — flag protocol (B+C)

- **What**: discovered desktop Agnes Code ships **no headless CLI binary**
  (only `AgnesCode.exe` GUI + `agnesd.exe`). So the hook cannot spawn
  `Agnes Code run --recipe …` directly.
- **How fixed**: the hook now **writes a flag** (`.state/pending_re.json`)
  instead of spawning. Two drain paths consume it:
  - **B** (in-session): MCP tool `harness2_requeue` in
    `mcp_server/harness2_mcp.py` (routes by bench; explicit args win).
  - **C** (scheduled): `scripts/drain_requeue.py` via Task Scheduler / cron,
    direct `python -m harness2.cli.*` — no external CLI.
- **Verification**: end-to-end via `b_test.py` (flag read → bench routing →
  consume → empty-queue no-op) + drain no-op + `_pipeline` shaping.
- **Docs synced**: plugin README (flag protocol + mermaid), top README
  (flag-protocol ASCII loop), handoff P1 closed.

---

## 2026-10-22

### 08:xx — global plugin + multi-agent package
- **What**:
  - Installed the plugin to the **global** location
    (`~/.Agnes Code/plugins/harness2-loop/`) so it applies to **any**
    project (MCP side reads global + project flag paths, global wins).
  - Built `multi-agent/` so the loop works under **any** coding agent
    (opencode, Antigravity, WorkBuddy, Qoder, Trae, Cline, Kiro, MiniMax):
    - `adapters/git/post-commit.sh` + `install.sh` — universal git trigger.
      Python is used **only** when a real interpreter is found (guards
      against the Windows MS-Store `python` alias); otherwise pure-shell JSON.
    - `adapters/build-failure/record-build-failure.sh` — manual build-fail
      one-liner for agents without native hooks.
    - `adapters/mcp/*.mcp.json` — 8 per-agent `mcpServers` fragments
      (all JSON-validated; opencode uses a `command` array, others share
      the `mcpServers` shape; WorkBuddy has no documented MCP surface).
    - `README.md` — 3-layer mapping + per-agent quickstart + caveats.
- **Verification**: `install.sh` into a temp git repo → commit → hook wrote
  a **valid** `pending_re.json` (`signal=commit bench=demo` + correct SHA).
  Build-failure script also produced a valid flag.
- **Docs synced**: README `## Multi-agent adapters` section; handoff P5
  closed, asset #12 added, quick commands updated; `dev_log.md` created.

---

---

## 2026-10-22 (later) — audit, cleanup, doc sync, portable packaging

- **Full inventory + cleanup (zero-regression)**:
  - No dead code in the integration layer (every file is referenced).
  - Removed an accidentally-tracked `.agnes/uploads/*.png` screenshot;
    added `.agnes/uploads/` to `.gitignore` (runtime/privacy, not source).
- **Doc sync to "no headless CLI / flag protocol" reality** (100% accurate):
  - `recipes/…yaml` header, README activation, handoff P2 + quick commands,
    plugin-README mermaid, and the MCP docstring (added the missing
    `harness2_requeue`, now 10 tools) all updated; removed the 4 residual
    `Agnes Code <cli>` assumptions (SSOT/MECE).
- **Restore baseline**: sandbox-verified (4-py + 13-json + flowchart HTML
  structural PASS; functional smoke of the flag protocol PASS) before the
  atomic audit commit.
- **Portable zero-dependency package** (#5): `scripts/pack_portable.py`
  builds `.agnes/artifacts/harness2-loop-portable.zip` (27 files, ~48 KB,
  `zero_dep: True`, SHA-256 manifest). Re-runnable/idempotent. Excludes
  runtime `.state/`, caches, and machine-local `.env`.
- **Security/privacy inventory** (#6, pre-push): no real secrets in tracked
  files (`AGNES_API_KEY` hits are placeholders/env-var reads only); large
  files are intentional assets; credential `.env` is gitignored.

---

## 2026-10-22 (final) — language discipline + cleanup

- **Global rule hard-coded**: `~/.config/Agnes Code/.agneshints` (user-wide,
  auto-loaded into every session's system prompt) now bans simplified-Chinese
  characters in project tooling / system files / code / docs; conversation
  language is explicitly left unconstrained.
- **Repo-tracked rule**: `.agneshints` at repo root (versioned, so every
  clone inherits it; project-level wins over global on conflict).
- **Simplified->Traditional cleanup** of 3 files that had drifted:
  `handoff.md`, `USER_GUIDE.md`, `agns_bridge/agns_gui.py` (UI string
  literals only; `ast.parse` re-verified).
- The `.agneshints` files intentionally *list* the banned simplified chars as
  samples — that is the rule's definition, not a violation.

*This file is appended to with each major change. Keep newest last.*
