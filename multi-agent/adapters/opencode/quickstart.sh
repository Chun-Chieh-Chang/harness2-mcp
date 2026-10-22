#!/usr/bin/env bash
# harness2-loop × opencode 傻瓜式初始化
# 用法：bash quickstart.sh [專案目錄，預設 .]
# 一次跑完三件事：① 裝 git hook ② 寫 opencode MCP ③ 註冊排程（可選）
# 以後每次 git commit 都自動記「待辦紙條」，drain 自動跑，零人工。

set -eu

PROJECT="${1:-.}"
# This script lives at <root>/multi-agent/adapters/opencode/quickstart.sh
# so the repo root is three levels up from the script's own directory.
HARNESS2_REPO="${HARNESS2_REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}"
FLAG_DIR="${HARNESS2_LOOP_FLAG_DIR:-$HOME/.Agnes Code/plugins/harness2-loop/.state}"
BENCH="${HARNESS2_LOOP_BENCH:-demo}"
MODE="${HARNESS2_LOOP_MODE:-parallel}"

echo "== harness2-loop quickstart for opencode =="
echo "   target project: $PROJECT"
echo "   harness2 repo : $HARNESS2_REPO"
echo ""

# ---- 1. git post-commit hook ----
echo "[1/3] installing git post-commit hook ..."
HOOK_SRC="$HARNESS2_REPO/multi-agent/adapters/git/post-commit.sh"
INSTALL_SH="$HARNESS2_REPO/multi-agent/adapters/git/install.sh"
bash "$INSTALL_SH" "$PROJECT"
echo "      done: every commit in this project now writes a pending flag."

# ---- 2. opencode MCP config ----
# opencode reads project-level `opencode.json` (or a global variant).
# We write a small project-level one here. Python is used ONLY when a real
# interpreter is found (guard against the Windows MS-Store `python` alias).
echo "[2/3] writing opencode MCP config (project-level opencode.json) ..."
OC_JSON="$PROJECT/opencode.json"

# find a real python (same guard as post-commit.sh)
PYBIN=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import json" >/dev/null 2>&1; then
    PYBIN="$cand"; break
  fi
done

# Windows-friendly path (git-bash gives MSYS paths; opencode wants native)
WIN_REPO=$HARNESS2_REPO
WIN_RUNS="$HARNESS2_REPO/runs"
if command -v cygpath >/dev/null 2>&1; then
  WIN_REPO=$(cygpath -w "$HARNESS2_REPO")
  WIN_RUNS=$(cygpath -w "$HARNESS2_REPO/runs")
fi

if [ -n "$PYBIN" ]; then
  "$PYBIN" - "$OC_JSON" "$WIN_REPO" "$WIN_RUNS" <<'PY'
import json, sys, os
path, repo, runs = sys.argv[1:4]
entry = {"mcp": {"harness2": {
    "type": "local",
    "command": ["python", "-m", "mcp_server.harness2_mcp"],
    "cwd": repo,
    "environment": {"HARNESS2_REPO": repo, "HARNESS2_RUNS_DIR": runs},
    "enabled": True,
}}}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
        if not isinstance(existing, dict):
            existing = {}
        existing.setdefault("mcp", {}).setdefault("harness2", {}).update(entry["mcp"]["harness2"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False); f.write("\n")
        print("      merged harness2 into existing", path)
    except Exception as e:
        print("      WARN: could not parse existing %s (%s) — leaving it untouched;" % (path, e))
        print("             please add the harness2 entry manually (see USER_GUIDE.md §8).")
else:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False); f.write("\n")
    print("      created", path)
PY
else
  # No real python: only safe to WRITE a fresh file; never merge into an
  # existing one (pure-shell JSON merge is unreliable). 
  if [ -f "$OC_JSON" ] && [ -s "$OC_JSON" ]; then
    echo "      $OC_JSON already exists and no working python was found."
    echo "      Manual: add the 'harness2' mcpServers block below into it:"
    echo '      {"mcp":{"harness2":{"type":"local","command":["python","-m","mcp_server.harness2_mcp"],"cwd":"'"$WIN_REPO"'","environment":{"HARNESS2_REPO":"'"$WIN_REPO"'","HARNESS2_RUNS_DIR":"'"$WIN_RUNS"'"},"enabled":true}}}'
  else
    cat > "$OC_JSON" <<EOF
{
  "mcp": {
    "harness2": {
      "type": "local",
      "command": ["python", "-m", "mcp_server.harness2_mcp"],
      "cwd": "$WIN_REPO",
      "environment": {
        "HARNESS2_REPO": "$WIN_REPO",
        "HARNESS2_RUNS_DIR": "$WIN_RUNS"
      },
      "enabled": true
    }
  }
}
EOF
    echo "      created $OC_JSON (pure shell, no python needed)"
  fi
fi
echo "      opencode now exposes 10 harness2_* tools (incl. harness2_requeue)."

# ---- 3. optional: scheduled drain (C path) ----
echo "[3/3] registering a 60-min scheduler (path C, off-session drain) ..."
if command -v crontab >/dev/null 2>&1; then
  DRAIN="$HARNESS2_REPO/.Agnes Code/plugins/harness2-loop/scripts/drain_requeue.py"
  LINE="0 */1 * * * * python '$DRAIN'"
  # idempotency: skip if already present
  if crontab -l 2>/dev/null | grep -qF "$DRAIN"; then
    echo "      cron entry already exists — skipping."
  else
    ( crontab -l 2>/dev/null; echo "$LINE" ) | crontab -
    echo "      cron added: $LINE"
  fi
elif command -v schtasks >/dev/null 2>&1; then
  DRAIN="$HARNESS2_REPO/.Agnes Code/plugins/harness2-loop/scripts/drain_requeue.py"
  if schtasks /Query /TN harness2-loop-drain >/dev/null 2>&1; then
    echo "      Task Scheduler entry already exists — skipping."
  else
    schtasks /create /sc minute /mo 60 /tn harness2-loop-drain \
      /tr "python \"$DRAIN\"" >/dev/null
    echo "      Task Scheduler entry created."
  fi
else
  echo "      no crontab / schtasks found — skipping scheduled drain (path B still works in-session)."
fi

echo ""
echo "✔ quickstart done."
echo ""
echo "From now on, ZERO manual steps:"
echo "  • any 'git commit' in $PROJECT  →  writes pending_re.json automatically"
echo "  • opencode open?               →  just say '撿起待辦紙條' and harness2_requeue drains it"
echo "  • opencode closed?             →  scheduler drains it within 60 min"
echo "  • you can even turn it OFF     →  see USER_GUIDE.md §11"
echo ""
echo "Uninstall (optional):"
echo "  rm \"$PROJECT/.git/hooks/post-commit\""
echo "  rm -f \"$OC_JSON\"   # or just delete the 'harness2' key inside it"
