# Agnes × Harness² 使用教程

## 👉 最簡單用法：雙擊 `harness2\agns-gui.bat`

瀏覽器會自動開一個網頁控制台，**不用打任何指令**，只有三組按鈕：

| 按鈕 | 做的事 | 結果 |
|---|---|---|
| **①-A 跑 Demo（內建 worker）** | 用不需 API 的確定性 worker 跑 Harness² 遞迴 demo | 下方顯示 `2 題完成，0 失敗` |
| **①-B 跑 Demo（AGNES_CLI）** | 用你填在輸入框的 Agnes 指令跑（可留空改用①-A） | 同上 |
| **②-A 啟動 Bridge** | 在本機開一個把 Harness² 模型呼叫轉給 Agnes 的轉接器 | 下方顯示「Bridge 已啟動」 |
| **②-B 測試 Agnes 連線** | 透過 bridge 打一次 Agnes 模型，確認 200 | 下方顯示模型回覆 + token 用量 |
| **③-A 顯示結果** | 把最近一次 demo 的 JSON 變成白話摘要 | 完成/失敗題數、rollout 次數 |
| **③-B 打開結果資料夾** | 用 Windows 資源管理器開 `runs\agns_demo` | — |

**照 ① → ② → ③ 按就對了。** Bridge 端點（URL / key / model / auth）都放在
`.agns_bridge.env`，GUI 自動讀取，不需要在網頁上重填。

> 停止 Bridge：關掉 `agns-gui.bat` 那個黑色視窗（或按 Ctrl+C）。

---

## 進階：文字指令版本（給習慣 CLI 的人）

---

## 0. 先搞清楚你有兩條路徑

| 路徑 | Agnes 的角色 | 需要什麼 | 能不能桌面直接跑 |
|---|---|---|---|
| **B** | 被優化的 agent framework（substrate） | 不需要；預設走確定性 worker | ✅ 雙擊即可 |
| **A** | 凍結的模型端點（透過 OpenAI-compatible bridge） | Agnes API key + endpoint | ✅ 桌面跑 bridge；正式 bench 走 Linux |

你目前的設定檔 `.agns_bridge.env` 已填好（中國站 `apihub.agnes-ai.cn`，raw auth，
`agnes-3.0-flash`，兩把 key 都在），所以兩條路徑現在都能跑。

---



## 0.5 進化開發台（像 Agnes Code 一樣對話，做完就變強）

這是和本教程其他部分**不同的東西**：不是實驗台，是一個**互動開發助手**。

### 怎麼用

1. 雙擊 harness2\evolve-gui.bat（或 python evolve\evolve_gui.py）
2. 瀏覽器打開 http://127.0.0.1:8640，直接輸入開發任務，例如：
   - 「在 calc.py 實作 compound(principal, rate, years) 並補測試」
   - 「重命名 run_tests.py 為 make_tests.py，並更新所有引用」
3. 我會**即時顯示每一步工具動作**（讀檔案 / 寫檔案 / 跑 shell）
4. 任務完成後，**自動進化**：evolution engine 把這題的教訓寫進 .harness/
   （護欄、工具指南、記憶），VERSION +1，下一題開頭就比上一題強

### 跟「實驗台」的差別

| 實驗台（agns-gui.bat） | 進化開發台（evolve-gui.bat） |
|---|---|
| 跑固定 demo 題 | 你自由下達任何開發任務 |
| 結果是 JSON 數字 | 結果是實際改好的專案程式碼 + 可點開看 |
| 不進化你的 harness | **每題自動進化**，會累積 |

### 實際檔案位置

- 專案：evolve\demo_project\（calc.py + test_calc.py + run_tests.py，會隨任務累積新功能）
- harness：evolve\demo_project\.harness\（systemprompt / tool_guidance / guardrails / memory + experience.jsonl + VERSION）
- 想換成你自己的專案：改 evolve_gui.py 頂端的 PROJECT 指到任何資料夾即可

### 已驗證

三連真實任務（discount、compound、再複測）全部完成，harness 從 v0 進化到 v3，
護欄逐題累積了 3 條具體教訓（「讀再寫」「先確認符號存在」「浮點用近似比較」）。
\n## 1. 一次性安裝

```powershell
cd harness2
python -m pip install -e .
```

這會裝出 `harness2`、`harness2-agns-demo` 等 console scripts（之後可直接用
`harness2-agns-demo` 而不是 `python -m harness2.cli.agns_demo`）。

---

## 2. 路徑 B：雙擊跑 Agnes substrate 遞迴（最簡單，不耗 API）

**方法一（推薦，雙擊＋選單）：**

雙擊 `harness2\agns-desktop.bat`。它會：
1. 載入 `.agns_bridge.env`
2. **問你要哪個 rollout executor**：
   - 按 `1` = 內建確定性 worker（可重現、不耗 API）
   - 按 `2` = 真 Agnes headless CLI（用 `AGNES_CLI`）
     - 若 `AGNES_CLI` 在設定檔已填好，直接用；
     - 若留空，會讓你貼一個非互動指令（例 `agnes run --headless`）。
3. 確認 `pip install -e .`
4. 跑 `harness2-agns-demo --k 2 --mode both`
5. 印出 `runs/agns_demo/agns_demo.json` 並用 Explorer 打開結果

worker 分支預期：`2 tasks ok, 0 failed, 28 executions, 56 editor calls`。

**方法二（手動）：**

```powershell
cd harness2
python -m harness2.cli.agns_demo --output runs/agns_demo --k 2 --mode both
type runs\agns_demo\agns_demo.json
```

### 用「真正的 Agnes Code」跑 rollout（選做）

預設 `AGNES_CLI` 留空時走確定性 worker（可重現、不耗 API）。要真的讓 Harness²
驅動你的 Agnes Code，在 `.agns_bridge.env` 填：

```ini
AGNES_CLI=agnes run --headless
```

> Windows 上若想用 Python 實作，記得連解譯器一起寫，例如
> `AGNES_CLI=python agnes_bridge\fake_agnes_cli_example.py`
> （repo 裡 `agns_bridge\fake_agnes_cli_example.py` 就是一份符合契約的最小範例，
> 直接照它跑可驗證整條 CLI 路徑，再替換成你的 Agnes 指令）。

契約：`AgnesSubstrate.execute()` 會以 `cwd = 暫存 workspace` 執行這個指令，
workspace 裡有 staged harness + `ledger.csv`，並設定環境變量 `AGNES_TASK`、
`AGNES_WORKSPACE`。你的 Agnes 指令要**非互動**，且**寫 `answer.txt` 到
`AGNES_WORKSPACE`，或把答案印到 stdout**。

> 注意：`AGNES_CLI` 的 `run_id` 命名空間 id 含 `/`，Windows 上 `tempfile.mkdtemp`
> 會因此失敗；本 repo 已把該 prefix 改為洗掉分隔符（`agns_demo.py` 的
> `execute()`），所以 Windows 桌面可直接跑。

---

## 3. 路徑 A：把 Agnes 當模型端點接進 harness2（已驗證 200）

### 3.1 雙擊起 bridge + 自動驗證（推薦）

雙擊 `harness2\agns_bridge\agns-bridge-up.bat`。它會：
- 在本視窗啟動本地 bridge（`http://127.0.0.1:8620/v1` → 轉發到 Agnes）
- 同時開**第二個視窗**跑 `agns_bridge_check.py`：輪詢 bridge 直到回 200，
  然後印出「下一段要跑的 env 變量」

### 3.2 手動起 bridge（等價）

**視窗 1：**
```powershell
cd harness2
python -m agnes_bridge.agnes_openai_proxy
# 顯示: Agnes OpenAI-compatible bridge -> https://apihub.agnes-ai.cn/v1
#       listening on http://127.0.0.1:8620/v1
```

**視窗 2（新開）：**
```powershell
cd harness2
python agnes_bridge\agns_bridge_check.py
# 等它顯示 "AGNES LINK OK"，會把下面這段印出來
```

**視窗 2（接著上面的指令，把 harness2 指到 bridge）：**
```powershell
$env:OPENAI_BASE_URL      = "http://127.0.0.1:8620/v1"
$env:OPENAI_API_KEY       = "agnes-bridge"
$env:HARNESS2_SOLVER_MODEL   = "openai/agnes-3.0-flash"
$env:HARNESS2_IMPROVER_MODEL = "openai/agnes-3.0-flash"
$env:HARNESS2_JUDGE_MODEL    = "agnes-3.0-flash"

# 桌面 demo（不耗 API 額度，確認整條鏈路）
python -m harness2.cli.agns_demo --k 1 --mode both
```

### 3.3 跑正式 benchmark（需 Linux）

```powershell
python -m harness2.cli.run_sweep --bench lab --substrate oc --k 1 --mode parallel
```
> 正式 `jb/lab/wb` bench 依 `docs/SETUP.md` 要在 Linux 上先 `harness2-setup`，
> 並需要該 benchmark 的 model 額度。bridge 本身跨平台，桌面能驗證「harness2
> 透過 bridge 呼到 Agnes」這條鏈路。

### 3.4 用 Codex executor（選做）

```powershell
$env:HARNESS2_CODEX_BASE_URL = "http://127.0.0.1:8620/v1"
$env:HARNESS2_CODEX_API_KEY  = "agnes-bridge"
$env:HARNESS2_CODEX_MODEL     = "agnes-3.0-flash"
python -m harness2.cli.run_sweep --bench lab --substrate cx --k 1 --mode parallel
```

---

## 4. 出錯對照表

| 症狀 | 原因 | 解法 |
|---|---|---|
| bridge 503 | `AGNES_API_URL` 沒填 | 填進 `.agns_bridge.env`，重啟 bridge |
| bridge 回 401 "Invalid token" | header 格式不對 | 中國站 `apihub.agnes-ai.cn` 用 `AGNES_AUTH_HEADER=raw`；國際站用 `bearer` |
| bridge 回 404 model | 模型名不在該 host 清單 | 用 `python agnes_bridge\agns_bridge_check.py` 看 model；或打 `GET /v1/models` |
| 雙擊 bat 沒反應 | 視窗瞬間消失 | 手動跑 `python -m agnes_bridge.agnes_openai_proxy` 看錯誤 |
| demo 跑失敗 `StopIteration` | demo 的選擇器在 k>1 且無候選檔時舊版會炸 | 已加 fallback；重跑即正常 |

---

## 5. 檔案地圖

```
harness2/
├── .agns_bridge.env                    ← 所有參數（URL/key/model/auth）
├── .agns_bridge.env.example            ← 模板
├── agns-desktop.bat                    ← 雙擊跑路徑 B demo
├── agnes_bridge/
│   ├── agnes_openai_proxy.py           ← OpenAI-compatible 轉發 bridge（raw/bearer/x-api-key）
│   ├── agns_bridge_check.py            ← 第二視窗探活 + 印 harness2 指令
│   ├── agns-bridge-up.bat              ← 雙擊起 bridge + 自動開第二視窗驗證
│   ├── run_agns_paths.ps1 / .sh        ← 一鍵跑 A / B / all
│   └── README.md
├── harness2/
│   ├── substrate/agnes.py             ← AGNES_SURFACE + AgnesSubstrate（路徑 B）
│   ├── agnes_demo.py                   ← 零憑證 demo adapter + proposer
│   ├── cli/agns_demo.py               ← harness2-agns-demo CLI
│   └── core/{schedule,spec,prompts}.py ← 桌面修正（flock/install-mode/agnes surface）
└── runs/agns_demo/                    ← 結果 JSON + 執行軌跡
```

---

## 6. 一句話總結

- **想立刻看成果** → 雙擊 `agns-desktop.bat`（路徑 B）。
- **想讓 Harness² 真的圍繞你的 Agnes 模型優化** → 雙擊
  `agns_bridge\agns-bridge-up.bat`，照第二視窗印出的指令跑（路徑 A）。
- **想優化 Agnes 這個 framework 本身** → 把 `AGNES_CLI` 填上你的 Agnes
  非互動指令，再跑路徑 B。
