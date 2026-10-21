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
| 6 | Hooks 插件（閉環） | `.Agnes Code/plugins/harness2-loop/` | ✅ 完成 | 含 `plugin.json` / `hooks/hooks.json` / `scripts/rerun_recipe.py` / `scripts/rerun.cmd` / `config.json` / `README.md` / `.state/` |
| 7 | 互動流程圖 | `.agnes/artifacts/flowcharts/harness2-loop-flowchart.html` | ✅ 完成 | 依 flowchart-spec：零依賴原生 SVG + vanilla JS、資料驅動格點、ISO 5807 符號、顯式路由、互動四件套、內建幾何自審計徽章；**已納入 9 節白話結構化說明側欄** |
| 8 | 三層審計管線 | `scripts/verify-flowchart-spec.js` | ✅ 落檔 | 依 spec 要求存在；本機無 Node 未執行（誠實標註），已在有 Node 環境跑過才算 PASS |
| 9 | `.gitignore` | `.gitignore` | ✅ 完成 | 排除 `runs/`、`.state/`、`.agnes/cache|work|artifacts/`、`.agns_bridge.env` 機密、`__pycache__/` |
| 10 | 初始化 git repo | `.git/` | ✅ 完成 | `git init` + 首個整合 commit `d70e879`；中途清掉一個 PowerShell 意外產出的 0 字节 `$null` 檔案 |
| 11 | README § Agnes Code integration | `README.md` | ✅ 完成 | 含 5 資產對照表、flowchart 連結、activation 步驟、閉環 ASCII 圖、schedule 互補說明 |

### 整合資產之間的關係（一張話）
- **MCP server**＝手動入口：session 內用 `harness2_*` 工具即時調 CLI。
- **recipe**＝可重複/排程的流程本：本節全部動作的最终執行物。
- **agent**＝角色：幫你決定 bench/k/mode/substrate 與順序。
- **skill**＝知識：挑 bench、讀結果、接自動化。
- **hooks 插件**＝觸發器：讓上面四樣在「失敗 / commit」時**自動**轉。
- **flowchart HTML**＝視覺化資產 + 白話說明；**verify-flowchart-spec.js**＝它的三層審計管線。

---

## 3. 待完成 / 仍需人工確認

| # | 事項 | 阻塞原因 | 建議動作 |
|---|---|---|---|
| P1 | `config.json` 的 `cli` 欄位（預設 `"Agnes Code"`）在多數機器 PATH 上找不到 | 本機無 Agnes Code CLI 二進位 | 先查 CLI 實際路徑（`Get-Command AgnesCode / agnes` 或問使用者），再寫入絕對路徑；寫完可再餵一次 commit payload 驗證 `launched:` |
| P2 | recipe 未機器解析（PyYAML 未安裝） | Python 3.15 無 C++ 工具鏈，`pip install pyyaml` 失敗 | 在有 PyYAML 的環境跑一次 `Agnes Code run --recipe recipes/harness2-any-project.yaml --params bench=demo --dry-run=true` 確認 schema；或改 `uv pip install pyyaml` |
| P3 | `scripts/verify-flowchart-spec.js` 未在本機跑過（Node 缺失） | 本機無 Node.js | 裝 Node 20+ 後 `node scripts/verify-flowchart-spec.js .agnes/artifacts/flowcharts/harness2-loop-flowchart.html`，全綠才算 LAYER 1/2/3 全 PASS |
| P4 | `.agnes/cache/docs*` 內是外部文件快照，未 git 追蹤 | `.gitignore` 已排除 | 若日後要分享文件，改把 `docs/` 內文件 copy 進本 repo 並移除 cache 路徑引用 |
| P5 | 若要把 hooks 做成「跨專案」而非「本專案」 | 目前插件放 `<project>/.Agnes Code/plugins/`，只在此 repo 生效 | 拷貝到 `~/.Agnes Code/plugins/harness2-loop/` 並調整 `config.json` 的 `repo_root` 指向目標專案 |

---

## 4. 已知限制（誠實記錄，非缺陷）

- **閉環是事件驅動，非排程**：hooks 只接 build 失敗 / commit；若要「每天自動跑一次」仍需 `Agnes Code schedule add`。
- **`AfterShellExecution` 只在成功時觸發**：build 失敗只能用 `PostToolUseFailure` 接住；commit 只用 `AfterShellExecution` + `matcher: ^git\s+commit`。
- **裸 `"*"` matcher 在 Agnes 是非法 regex**：整條規則會被靜默跳過，所以 build-failure 規則故意不寫 matcher、改在腳本內用 `config.build_patterns` 過濾。
- **`PostToolUseFailure` 想 block 工具調用需印 `{"decision":"block"}`**：本插件是純觀測（`exit 0`），block 政策要另外用 `PreToolUse` 寫規則。
- **`score=None` 是 judge 故障，不是 0 分**：讀 `judged.json` 時不要誤判為退步。
- **harness2 本體不變**：整合層只驱动既有 CLI，不修改 8 個 CLI entry point 或 8 個 harness 組件。

---

## 5. 接手者可快速上手的 5 條命令

```powershell
# 0) 在 harness2 專案視窗開 Agnes Code，確認 plugin 被偵測到
Get-ChildItem ".Agnes Code\plugins\harness2-loop" -Recurse

# 1) 啟用 MCP 工具
Agnes Code mcp harness2

# 2) 手動餵 build 失敗 payload 給 hook（煙霧測試）
'{"event":"PostToolUseFailure","tool_input":{"command":"cargo test"}}' |
  python ".Agnes Code\plugins\harness2-loop\scripts\rerun_recipe.py" build-failure

# 3) 看判定日誌
Get-Content ".Agnes Code\plugins\harness2-loop\.state\harness2-loop.log" -Tail 10

# 4) 看背景 recipe 輸出
Get-Content ".Agnes Code\plugins\harness2-loop\.state\recipe-runs.log" -Tail 20
```

---

## 6. 未做的（明講）

- 沒有把 flowchart HTML 註冊為「多份」artifact；只用一個 `dedupe_key=harness2-loop-flowchart` 原地更新。
- 沒有在 README 放 Mermaid 靜態版（HTML 已是單一交付物；Mermaid 在插件 README 內）。
- 沒有改動 `harness2/` 內 Python 包（純整合層）。
- 沒有跑 `git remote add`（本機 repo，無遠端需求）。
- 沒有把 `.Agnes Code/plugins/harness2-loop/` 做成可跨專案複用；目前綁定本專案。

---

*此文件會隨每次大改同步更新。下次接手請先重讀 §3 待辦表。*
