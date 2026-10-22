# harness2 工具使用說明書（淺白版）

> 這本手冊假設你「完全沒聽過這些名詞」。所有術語都會先用一句大白話解釋。
> 適合：第一次拿到這套工具的使用者、想幫自己的專案接上「自動改良」的開發者。

---

## 目錄

1. [一句話：這套工具是幹嘛的](#1)
2. [箱裡有什麼](#2)
3. [先認清一個最重要的觀念](#3)
4. [開始使用：三步上手](#4)
5. [八個基本指令（白話版）](#5)
6. [讓 AI 助手代勞：十個工具](#6)
7. [自動循環：harness2-loop（核心功能）](#7)
8. [換別的 AI 工具也能用](#8)
9. [搬到另一台電腦](#9)
10. [常見問題](#10)
11. [注意事項](#11)

---

## 1. 一句話：這套工具是幹嘛的

harness2 是一套**「讓 AI 助手變聰明」的訓練工具**。

它做的事：拿一批「測驗卷」（bench），讓 AI 照著我們給它的工作手冊（harness）去做題目，
做完評分；發現哪邊做得不好，就**自動調整那份工作手冊**（加提醒、加限制、改步驟），
然後再測一次——反覆幾輪，AI 的表現就會一直進步。

加上 `harness2-loop` 之後，整個流程變成**自動的**：
你的程式測試失敗、或你按了 commit，它就在背景記一張「待辦紙條」，
之後有人（或定時排程）撿起紙條，自動重跑「測驗＋改良」。你什麼都不用做。

---

## 2. 箱裡有什麼

| 東西 | 白話角色 | 檔案位置 |
|---|---|---|
| harness2 主程式 | 測驗＋改良的核心引擎（8 個指令） | `harness2/` |
| 免登入練習題 | 不花錢、不用帳號就能試跑的 demo | `harness2-demo` 指令 |
| MCP 工具包 | 讓 AI 助手（如 Agnes Code）可以「動嘴叫指令」 | `mcp_server/` |
| 流程本（recipe） | 把「準備→預檢→測驗→評分→報告」寫成可重跑的流程 | `recipes/` |
| 助手角色（agent） | 一個會幫你決定「用哪套卷、做幾輪」的 AI 角色 | `.agents/agents/` |
| 知識手冊（skill） | 教 AI 怎麼挑測驗、怎麼看結果、怎麼接自動化 | `.agents/skills/` |
| 自動循環插件 | 測試失敗／commit 時自動記「待辦紙條」 | `.Agnes Code/plugins/harness2-loop/` |
| 多 AI 適配包 | 讓你把自動循環接到其他 AI 工具（Cline、Kiro…） | `multi-agent/` |
| 互動流程圖 | 一張可放大拖曳的圖＋完整白話說明（瀏覽器開啟） | `.agnes/artifacts/flowcharts/` |
| 可攜式包裝 | 一把搬走整套的 zip | `scripts/pack_portable.py` 產生 |

---

## 3. 先認清一個最重要的觀念

> **harness2 改善的是「AI 怎麼做事」，不是「直接幫你修程式碼」。**

- 你的專案 `cargo test` 失敗 → 它記下紙條 → 重跑的是「AI 工作手冊的改良流程」。
- 結果：AI 下次遇到你這類任務會處理得更好；**你的程式碼本身不會被它改動**。

把它想成「管家每天自我進修」，不是「管家幫你洗碗」。

另外：你**不需要**「進入 harness2 專案」開發你自己的專案。
harness2 是站在你專案外面服務的機制（就像你用 VS Code 開發專案，不會「在 VS Code 裡面開發 VS Code」）。

---

## 4. 開始使用：三步上手

### 第 1 步：裝好引擎（只要一次）

需要 Python 3.12。在本專案資料夾裡：

```powershell
uv venv --python 3.12 .venv
.venv\Scripts\Activate.ps1
uv pip install -e '.[render]'
```

（沒有 uv 就改 `pip install -e '.[render]'`，但要先把環境換成 Python 3.12。）

### 第 2 步：用免費練習題確認一切正常（不花錢、不用帳號）

```powershell
harness2-demo --output runs/demo --k 1
```

跑完去 `runs/demo/` 會看到結果檔案，代表引擎 OK。

### 第 3 步：挑你的使用場景

| 你的情況 | 看哪一節 |
|---|---|
| 想在 Agnes Code 裡面用全套自動循環 | 第 7 節 |
| 用別家 AI（Cline / Kiro / Qoder / Trae…） | 第 8 節 |
| 想跑真實大測驗（jb / lab / wb） | 第 5 節（會花錢，小心） |
| 想把整套工具搬到另一台電腦 | 第 9 節 |

---

## 5. 八個基本指令（白話版）

| 指令 | 白話說明 | 花錢？ |
|---|---|---|
| `harness2-setup <卷名>` | **準備**：把測驗卷和相關資料備齊（只做一次） | 否 |
| `harness2-check --bench <卷名>` | **預檢**：快速確認「真的能跑」再動手 | 否 |
| `harness2 --bench <卷名>` | **真正的測驗＋改良**（最花时间、最重要的那步） | 用真卷時**會** |
| `harness2-judge --bench <卷名>` | **評分**：把測出來的成績打分 | 視卷而定 |
| `harness2-report --bench <卷名>` | **看報告**：採納了哪個版本的手冊、下一步建議 | 否 |
| `harness2-demo` | **免費練習題**：不用帳號不花錢，專給初學者確認安裝 | 否 |
| `harness2-agns-demo` | 用「這台機器隨附的 AI」當受測者跑練習（零憑證） | 否 |
| `harness2-bridge` | 把外部模型服務接進來（進階） | 視模型 |

**建議順序**：`setup → check → run → judge → report`，一次照序跑完。

常用開關（白話）：

- `--k 1`＝「想 1 輪」；調大就是多繞幾輪（更久、可能更強）
- `--mode parallel`＝同時試好幾個版本；`sequential`＝一個接一個深想
- `--dry-run`＝**空跑**：走一遍流程但不真的花錢，先確認路徑對

---

## 6. 讓 AI 助手代勞：十個工具

MCP 工具包讓 AI 助手「動嘴」就能做上面那些事（不用你手打指令）：

| 工具 | 白話 |
|---|---|
| `harness2_setup` / `harness2_check` | 準備、預檢 |
| `harness2_run` | 跑測驗＋改良（真正的那步） |
| `harness2_judge` / `harness2_report` | 評分、看報告 |
| `harness2_demo` / `harness2_agns_demo` | 免費練習題 |
| **`harness2_requeue`** | **撿起「待辦紙條」並照單重跑**（自動循環的关键） |
| `agnes_bridge_status` / `agnes_bridge_start` | 進階：外部模型服務的狀態／啟動 |

用法：在 Agnes Code 對話裡直接說「用 harness2-demo 跑一下，先空跑」即可；
或叫出助手角色：`@harness2-dev-agent 幫 my-app 選練習題跑一圈，不要燒錢`。

---

## 7. 自動循環：harness2-loop（核心功能）

### 它何時會動

只有兩種情況：
1. 你的**測試／建置失敗**（如 `cargo test`、`npm test`、`make` 跑錯）
2. 你 **git commit 成功**

其他所有動作（看文件、改檔案）都不會觸發它。

### 發生後做什麼（白話 5 步）

1. **記一張待辦紙條**（`pending_re.json`）：寫上「什麼事、該用哪些參數重跑」
2. **等一下再記**：10 分鐘內同種情況不重複記（避免它自己連環觸發）
3. **兩個人會去撿紙條**：
   - **B**：你開著 Agnes Code 時，助手工具 `harness2_requeue` 自動撿
   - **C**：沒開時，定時排程（每 60 分鐘）撿
   - 兩邊共用同一張紙條，誰先到誰處理，**不會重複跑**
4. **照紙條重跑**：準備→預檢→測驗＋改良→評分→報告，結果存進 `judged.json`
5. **你看結果**：有進步就照舊；卡住了就把「想幾輪」調大，下次自動生效

### 確認它有沒有在動

```powershell
# 每次判定都記一筆（「記了紙條」或「跳過」）
Get-Content "$HOME\.Agnes Code\plugins\harness2-loop\.state\harness2-loop.log" -Tail 10
# 紙條還在＝還沒被處理；被撿走後會消失
Test-Path "$HOME\.Agnes Code\plugins\harness2-loop\.state\pending_re.json"
# 實際重跑的完整輸出
Get-Content "$HOME\.Agnes Code\plugins\harness2-loop\.state\recipe-runs.log" -Tail 20
```

### 調參（改 `config.json`，改完馬上生效）

| 項目 | 白話 |
|---|---|
| `params.bench` | 用哪套卷：`demo` 最輕不花錢；`jb`/`lab`/`wb` 是真實大試 |
| `params.k` / `params.mode` | 重測強度；分數卡住就調大 k、改 `sequential` |
| `params.dry_run` | `"true"`＝先空跑看流程不花錢 |
| `cooldown_seconds` | 同種情況的間隔（預設 600 秒） |
| `build_patterns` | 換語言生態就加關鍵字，例如 Maven 加 `\bmvn\s+(test\|package)` |
| `runs_namespace` | 保持 `continuous` 不變，歷次結果才能互相比 |

### 關掉（不刪檔）

在 Agnes Code 設定檔加一列：`{ "disabledPlugins": ["harness2-loop"] }`
（專案：`<project>/.config/Agnes Code/settings.json`；全域：`~/.config/Agnes Code/settings.json`）

---

## 8. 換別的 AI 工具也能用

自動循環**不綁定任何一家 AI**。三條路（照順序優先）：

> **懶人模式（一次全設定好）**：如果你用 opencode，這一行直接幫你三件全做（git hook + opencode 的 MCP 設定 + 排程）：
> ```sh
> sh multi-agent/adapters/opencode/quickstart.sh /path/to/你的專案
> ```
> 跑完之後就「不用再動了」——之後每次 commit 自動記紙條、自動被撿起重跑。

1. **git 掛勾（最通用）**：任何用 git 的 AI 都生效。裝一次：
   ```sh
   sh multi-agent/adapters/git/install.sh /path/to/你的專案
   ```
   從此該專案每次 commit 都會自動記紙條。
2. **MCP 工具**：把 `multi-agent/adapters/mcp/` 裡「你家 AI」那份片段
   貼進它的 MCP 設定檔（各家位置不同，`multi-agent/README.md` 有對照表）。
3. **定時排程**：沒開任何 AI 也要跑，就用排程器定期撿紙條（Windows 排程工作／cron）。

沒有原生掛勾機制的 AI（例如 build 失敗時），用這一行手動記紙條：

```sh
(cargo test || sh multi-agent/adapters/build-failure/record-build-failure.sh cargo test)
```

**出過的現**：各家 AI 的設定檔名稱／路徑會跟著版本變，貼之前先對一眼該家的最新文件。

---

## 9. 搬到另一台電腦

整套是「無依賴」的（只用 Python 標準庫）：

```powershell
# 在本機產出打包（會自動檢查確實沒有第三方套件）
python scripts/pack_portable.py
# 產出：.agnes\artifacts\harness2-loop-portable.zip（約 48KB）
```

把 zip 帶到新機器，解壓後：

1. 裝好 Python 3.12 與 harness2 本體（`pip install -e .`）
2. 把解出來的 `.Agnes Code/plugins/harness2-loop/` 放到新機器的全域插件位置（或放進該專案）
3. 開 Agnes Code → 自動載入 → 完

zip 內的 `manifest.json` 有每個檔案的指紋（SHA-256），可核對完整性。

---

## 10. 常見問題

| 問 | 答 |
|---|---|
| 它會改我的程式碼嗎？ | **不會**。它只改「給 AI 的工作手冊」，你的專案不動。 |
| 要一直開著 Agnes Code 才會跑嗎？ | 不用。沒開時，排程路徑（C）每 60 分鐘自動撿一次紙條。 |
| 跑起來好慢／好貴？ | 把 `params.dry_run` 設 `"true"`（空跑），或 `bench` 設 `demo`（免費）。 |
| 報告裡 `score` 是 `None`？ | 那代表「那次評分沒成功」，**不是 0 分、也不是退步**。看 log 修完再判斷。 |
| 測試失敗一次它就一直重跑嗎？ | 不會。10 分鐘冷卻內同種情況只記一次；而且它重跑的是「改良流程」，不會去反覆修你的 build。 |
| 怎麼確認整套真的在動？ | 看第 7 節那三條 log 命令；或手動餵一筆假資料（下方）： |

手動煙霧測試（三行，確認觸發鏈路通）：

```powershell
'{"event":"PostToolUseFailure","tool_input":{"command":"cargo test"}}' |
  python "$HOME\.Agnes Code\plugins\harness2-loop\scripts\rerun_recipe.py" build-failure
Get-Content "$HOME\.Agnes Code\plugins\harness2-loop\.state\harness2-loop.log" -Tail 5
```

看到「記了紙條」的記錄＝路徑 OK。

---

## 11. 注意事項

- **花錢提醒**：跑 `jb` / `lab` / `wb` 真實大試時，AI 真的會動用模型額度；初次使用請從 `demo` + 空跑開始。
- **憑證檔案**（`.agns_bridge.env`）不要放進 git、不要傳给别人——它已設為自動忽略。
- **各 AI 工具的路徑會變**：第 8 節的 MCP 片段是起點，正式使用前對一次該家的最新文件。
- **這套工具的定位**：持續改良 AI 的工作方法，不是 CI/CD、不是測試框架本身。
  它假設你的專案「有用 git」；build 失敗的訊號可自動或手動記錄。

---

*本說明書隨 `dev_log.md` 一起保持最新；若行為與此處不符，以 `dev_log.md` 最後一段為準。*
