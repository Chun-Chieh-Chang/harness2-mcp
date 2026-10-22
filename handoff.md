# handoff — harness2 × Agnes Code integration

> 交接狀態文件。接手者請先讀這裡，再看 [README § Agnes Code integration](README.md#agnes-code-integration) 與
> [.Agnes Code/plugins/harness2-loop/README.md](.Agnes Code/plugins/harness2-loop/README.md)。
> 建立時間：2026-10-21 · 工作目錄：`E:\Self-developed_Apps\G3\harness2`

---

## 1. 一句話概況

harness2 已從「手動 CLI 框架」升級為「**Agnes Code 內建、可自動重跑**的開發工具」：
透過 5 份整合資產（MCP server / recipe / custom agent / skill / hooks 插件），
讓任意專案在 Agnes Code 視窗內即可觸發 `setup → check → run → judge → report`，
並在 build 失敗 / git commit 時**自動**重跑——形成持續改良閉環。

---

## 2. 已完成的資產（in-tree）

| # | 資產 | 路徑 | 狀態 | 備註 |
|---|---|---|---|---|
| 1 | MCP stdio server | `mcp_server/harness2_mcp.py` | ✅ 完成 | 9 個 `harness2_*` 工具 + 2 個 `agns_bridge_*` helper；零第三方依賴；`ast.parse` 通過 |
| 2 | MCP 包 docstring | `mcp_server/__init__.py` | ✅ 完成 | 說明啟動方式 + config.yaml 擴展現块 |
| 3 | Recipe | `recipes/harness2-any-project.yaml` | ✅ 完成 | setup→check→run→judge→report 全流水線；`json_schema` 結構化輸出；跨平台 retry；**已對照官方 `recipe-reference.md` 逐欄核對**，但未機器解析（本機 PyYAML 缺失） |
| 4 | Custom agent | `.agents/agents/harness2-dev-agent.md` | ✅ 完成 | 6 步工作序、bench/k/mode 決策、約束條款 |
| 5 | Skill | `.agents/skills/harness2-develop/SKILL.md` | ✅ 完成 | 5 節：bench 選取、操作順序、擴充參數、讀結果、接入自動化（含 hooks 插件） |
| 6 | Hooks 插件（閉環） | `.Agnes Code/plugins/harness2-loop/` | ✅ 完成 | 含 `plugin.json` / `hooks/hooks.json` / `scripts/rerun_recipe.py`（寫旗標）/ `scripts/drain_requeue.py`（C 端 drain）/ `scripts/rerun.cmd` / `config.json` / `README.md` / `.state/`（含 `pending_re.json` 旗標） |
| 7 | 互動流程圖 | `.agnes/artifacts/flowcharts/harness2-loop-flowchart.html` | ✅ 完成 | 依 flowchart-spec：零依賴原生 SVG + vanilla JS、資料驅動格點、ISO 5807 符號、顯式路由、互動四件套、內建幾何自審計徽章；**已納入 9 節白話結構化說明側欄** |
| 8 | 三層審計管線 | `scripts/verify-flowchart-spec.js` | ✅ 落檔 | 依 spec 要求存在；本機無 Node 未執行（誠實標註），已在有 Node 環境跑過才算 PASS |
| 9 | `.gitignore` | `.gitignore` | ✅ 完成 | 排除 `runs/`、`.state/`、`.agnes/cache|work|artifacts/`、`.agns_bridge.env` 機密、`__pycache__/` |
| 10 | 初始化 git repo | `.git/` | ✅ 完成 | `git init` + 首個整合 commit `d70e879`；中途清掉一個 PowerShell 意外產出的 0 字节 `$null` 檔案 |
| 11 | README § Agnes Code integration | `README.md` | ✅ 完成 | 含 5 資產對照表、flowchart 連結、activation 步驟、閉環 ASCII 圖、schedule 互補說明 |
| 12 | **多 agent 適配包** | `multi-agent/` | ✅ 完成 | 讓閉環套在**任何** agent（opencode / Antigravity / WorkBuddy / Qoder / Trae / Cline / Kiro / MiniMax）上。三層：① 通用 git `post-commit` 觸發器（`adapters/git/`）；② 8 份 per-agent `mcpServers` 片段（`adapters/mcp/`，JSON 全數校驗通過）；③ 排程 drain（`drain_requeue.py`）＋手動 build 失敗一鍵 `adapters/build-failure/`。見 `multi-agent/README.md` |

### 整合資產之間的關係（一張話）
- **MCP server**＝手動入口：session 內用 `harness2_*` 工具即時調 CLI。
- **recipe**＝可重複/排程的流程本：本節全部動作的最终執行物。
- **agent**＝角色：幫你決定 bench/k/mode/substrate 與順序。
- **skill**＝知識：挑 bench、讀結果、接自動化。
- **hooks 插件**＝觸發器：在「失敗 / commit」時**記訊號**（寫 `.state/pending_re.json` 旗標）；真正重跑由 **B**（MCP `harness2_requeue`，session 內 drain）與 **C**（`drain_requeue.py`，排程 drain）兩端消費旗標執行，互補事件維度與時間維度。
- **MCP server**＝手動入口 + B 端 drain：`harness2_*` 工具即時調 CLI；`harness2_requeue` 消費 pending 旗標自動重跑。
- **flowchart HTML**＝視覺化資產 + 白話說明；**verify-flowchart-spec.js**＝它的三層審計管線。

---

## 3. 待完成 / 仍需人工確認

| # | 事項 | 阻塞原因 | 建議動作 |
|---|---|---|---|
| P1 | ~~`config.json` 的 `cli` 欄位在多數機器 PATH 上找不到~~ | **已以旗標協議關閉**：桌面版 Agnes Code 只有 GUI（`AgnesCode.exe`）+ `agnesd.exe`，無 headless CLI 二進位（已驗證）。改為「hook 只寫 `.state/pending_re.json` 旗標 → B（MCP `harness2_requeue`）或 C（`drain_requeue.py` 排程）drain 執行」，兩端都不需要外部 CLI。已移除 `config.json` 的 `cli` 欄。 | 無（待辦清掉）；若要改 drain 路徑，調 `config.json` 的 `requeue.flag_path` 與 `schedule_hint` |
| P2 | recipe 未機器解析（PyYAML 未安裝） | Python 3.15 無 C++ 工具鏈，`pip install pyyaml` 失敗 | 在有 PyYAML 的環境（或 `uv pip install pyyaml`）機器解析 `recipes/harness2-any-project.yaml` 確認 schema；或 drain 一次經 MCP `harness2_requeue` 看是否報 recipe schema 錯 |
| P3 | `scripts/verify-flowchart-spec.js` 未在本機跑過（Node 缺失） | 本機無 Node.js | 裝 Node 20+ 後 `node scripts/verify-flowchart-spec.js .agnes/artifacts/flowcharts/harness2-loop-flowchart.html`，全綠才算 LAYER 1/2/3 全 PASS |
| P4 | `.agnes/cache/docs*` 內是外部文件快照，未 git 追蹤 | `.gitignore` 已排除 | 若日後要分享文件，改把 `docs/` 內文件 copy 進本 repo 並移除 cache 路徑引用 |
| P5 | ~~若要把 hooks 做成「跨專案」而非「本專案」~~ | **已解決**：全域插件已裝到 `~/.Agnes Code/plugins/harness2-loop/`（任何專案開 Agnes 都自動載入，MCP 端雙路徑讀全域/專案旗標）；且 `multi-agent/` 提供 agent-agnostic 的 git `post-commit` 觸發器，任何用 git 的專案 commit 即觸發 | 無（待辦清掉）；跨 agent 細節見 `multi-agent/README.md` |

---

## 4. 已知限制（誠實記錄，非缺陷）

- **閉環是事件驅動、執行靠 drain**：hooks 只「記訊號」（寫 `pending_re.json`）；真正重跑要由 **B**（MCP `harness2_requeue`，需有開著的 Agnes session）或 **C**（排程 `drain_requeue.py`，session 外）消費旗標。桌面版無 CLI，所以兩端都不 spawn 外部二進位。
- **`AfterShellExecution` 只在成功時觸發**：build 失敗只能用 `PostToolUseFailure` 接住；commit 只用 `AfterShellExecution` + `matcher: ^git\s+commit`。
- **裸 `"*"` matcher 在 Agnes 是非法 regex**：整條規則會被靜默跳過，所以 build-failure 規則故意不寫 matcher、改在腳本內用 `config.build_patterns` 過濾。
- **`PostToolUseFailure` 想 block 工具調用需印 `{"decision":"block"}`**：本插件是純觀測（`exit 0`），block 政策要另外用 `PreToolUse` 寫規則。
- **`score=None` 是 judge 故障，不是 0 分**：讀 `judged.json` 時不要誤判為退步。
- **harness2 本體不變**：整合層只驱动既有 CLI，不修改 8 個 CLI entry point 或 8 個 harness 組件。

---

## 5. 接手者可快速上手的 5 條命令

```powershell
# 0) 確認 plugin 被偵測到（專案 / 全域皆可）
Get-ChildItem ".Agnes Code\plugins\harness2-loop" -Recurse
#    或在任何專案下：Get-ChildItem "$HOME\.Agnes Code\plugins\harness2-loop" -Recurse

# 1) MCP 工具（harness2_*）由插件在 Agnes Code session 自動載入，無須手動啟用
#    （桌面版無 CLI，故沒有 `Agnes Code mcp` 指令；直接開 Agnes Code 即可）

# 2) 手動餵 build 失敗 payload 給 hook（煙霧測試）
'{"event":"PostToolUseFailure","tool_input":{"command":"cargo test"}}' |
  python ".Agnes Code\plugins\harness2-loop\scripts\rerun_recipe.py" build-failure

# 3) 看判定日誌
Get-Content ".Agnes Code\plugins\harness2-loop\.state\harness2-loop.log" -Tail 10

# 4) 看 drain 路徑實際跑 recipe 的輸出
Get-Content ".Agnes Code\plugins\harness2-loop\.state\recipe-runs.log" -Tail 20

# 5) 跨 agent 通用觸發器：把 git post-commit hook 裝到任何專案
sh multi-agent/adapters/git/install.sh /path/to/your-project
```

---

## 6. 未做的 / 需注意（明講）

- 沒有改動 `harness2/` 內 Python 包（純整合層）。
- `.Agnes Code/plugins/harness2-loop/` 已綁定專案；**全域複用**靠 `~/.Agnes Code/plugins/`（已裝）＋ `multi-agent/adapters/git/`（agent-agnostic）。
- **multi-agent 的 8 份 MCP 片段是「起點」**：各 agent 的 MCP key 名／設定檔路徑會隨版本變，正式使用前請對該 agent 現行文件確認一次（`multi-agent/README.md` 有逐個標明）。
- **WorkBuddy 無文件化 MCP 路徑**：`workbuddy.mcp.json` 只是備用；可靠路徑是 git hook（層 1）＋排程 drain（層 3）。
- 沒有把 flowchart HTML 註冊為「多份」artifact；只用一個 `dedupe_key=harness2-loop-flowchart` 原地更新。
- 沒有在 README 放 Mermaid 靜態版（HTML 已是單一交付物；Mermaid 在插件 README 內）。
- 遠端已 push 到 `https://github.com/Chun-Chieh-Chang/harness2-mcp`（见 dev_log.md）。

---

*此文件會隨每次大改同步更新。下次接手請先重讀 §3 待辦表。*
