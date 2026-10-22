#!/usr/bin/env bash
# Shared logic for harness2-loop quickstart scripts.
# Each per-agent quickstart-<agent>.sh sources this and only supplies its own
# MCP config path + key shape. This keeps the 8 agent variants DRY.
#
# Exposes:
#   install_git_hook PROJECT_DIR          - copies post-commit.sh into PROJECT_DIR/.git/hooks/
#   write_mcp_json TARGET_JSON KEYPATH CMD ARGS  - non-destructive merge into JSON file
#   install_scheduler DRAIN_PY           - idempotent crontab/schtasks registration
#   find_real_python                    - echoes "python3" or "python" or "" (MS-Store guard)
#   to_windows_path MSYS_PATH            - converts git-bash MSYS path to Windows (if applicable)

set -u

# Resolve repo root. common.sh lives at <root>/multi-agent/adapters/common.sh
# (and is sourced from siblings at the same depth), so the repo root is two
# levels up from this file's directory.
HARNESS2_REPO="${HARNESS2_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# ---------------------------------------------------------------- find_real_python
find_real_python() {
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import json" >/dev/null 2>&1; then
      echo "$cand"; return 0
    fi
  done
  echo ""; return 0
}

# ---------------------------------------------------------------- to_windows_path
# git-bash reports MSYS paths (/e/...) which JSON consumers on Windows want as
# native (E:\...). Uses cygpath when available, else echoes input unchanged.
to_windows_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1" 2>/dev/null || printf '%s' "$1"
  else
    printf '%s' "$1"
  fi
}

# ---------------------------------------------------------------- to_msys_path
# Inverse: a Windows path (C:\...) passed from PowerShell/cmd becomes an MSYS
# path (/c/...) that bash mkdir/cd handle cleanly. No-op when already MSYS or
# cygpath is absent. Use on any PROJECT/target dir BEFORE bash file ops.
to_msys_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -u "$1" 2>/dev/null || printf '%s' "$1"
  else
    printf '%s' "$1"
  fi
}

# ---------------------------------------------------------------- install_git_hook
install_git_hook() {
  # $1 = target project dir
  local PROJECT_DIR="$1"
  local install_sh="$HARNESS2_REPO/multi-agent/adapters/git/install.sh"
  if [ ! -f "$install_sh" ]; then
    echo "      [hook] install.sh not found under $HARNESS2_REPO — skip"
    return 0
  fi
  # install.sh is POSIX; run it with the system sh (usually fine) or git-bash sh
  local sh_bin
  sh_bin=$(command -v sh || echo sh)
  "$sh_bin" "$install_sh" "$PROJECT_DIR"
}

# ---------------------------------------------------------------- write_mcp_json
# write_mcp_json TARGET_JSON KEYPATH STYLE REPO RUNS
#   STYLE = "opencode"    -> {type:local, command:[...], cwd, environment:{...}, enabled}
#   STYLE = "mcpServers"  -> {command:"python", args:[...], cwd, env:{...}}
# Non-destructive merge into an existing JSON file; creates fresh if absent.
write_mcp_json() {
  local TARGET_JSON="$1" KEYPATH="$2" STYLE="$3" REPO="$4" RUNS="$5"
  local py
  py=$(find_real_python)
  REPO=$(to_windows_path "$REPO"); RUNS=$(to_windows_path "$RUNS")
  # bash file-ops need MSYS paths; native Windows Python needs Windows paths.
  local TARGET_MSYS TARGET_WIN
  TARGET_MSYS=$(to_msys_path "$TARGET_JSON")
  TARGET_WIN=$(to_windows_path "$TARGET_JSON")
  mkdir -p "$(dirname "$TARGET_MSYS")" 2>/dev/null || true

  if [ -n "$py" ]; then
    "$py" - "$TARGET_WIN" "$KEYPATH" "$STYLE" "$REPO" "$RUNS" <<'PY'
import json, sys, os
target, keypath, style, repo, runs = sys.argv[1:6]
if style == "opencode":
    payload = {"type": "local",
               "command": ["python", "-m", "mcp_server.harness2_mcp"],
               "cwd": repo,
               "environment": {"HARNESS2_REPO": repo, "HARNESS2_RUNS_DIR": runs},
               "enabled": True}
else:
    payload = {"command": "python",
               "args": ["-m", "mcp_server.harness2_mcp"],
               "cwd": repo,
               "env": {"HARNESS2_REPO": repo, "HARNESS2_RUNS_DIR": runs}}
node = {}
if os.path.exists(target):
    try:
        with open(target, encoding="utf-8") as f:
            node = json.load(f) or {}
    except Exception as e:
        print("      [mcp] WARN: existing %s not valid JSON (%s); leaving untouched" % (target, e))
        sys.exit(0)
parts = keypath.split(".")
parent = node
for p in parts[:-1]:
    parent = parent.setdefault(p, {})
parent.setdefault(parts[-1], {}).update(payload)
os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
with open(target, "w", encoding="utf-8") as f:
    json.dump(node, f, indent=2, ensure_ascii=False); f.write("\n")
print("      [mcp] wrote %s -> %s (%s style)" % (target, keypath, style))
PY
    return 0
  fi

  # No python: only safe to create a FRESH file (never merge). Escape backslashes
  # for JSON so Windows paths stay valid.
  if [ -f "$TARGET_JSON" ] && [ -s "$TARGET_JSON" ]; then
    echo "      [mcp] WARN: $TARGET_JSON exists but no usable python found."
    echo "             Please merge the harness2 block manually (see USER_GUIDE.md §8)."
    return 1
  fi
  local ER ER2
  ER=$(printf '%s' "$REPO" | sed 's/\\/\\\\/g')
  ER2=$(printf '%s' "$RUNS" | sed 's/\\/\\\\/g')
  if [ "$STYLE" = "opencode" ]; then
    printf '{\n  "mcp": {\n    "harness2": {\n      "type": "local",\n      "command": ["python", "-m", "mcp_server.harness2_mcp"],\n      "cwd": "%s",\n      "environment": {"HARNESS2_REPO": "%s", "HARNESS2_RUNS_DIR": "%s"},\n      "enabled": true\n    }\n  }\n}\n' \
      "$ER" "$ER" "$ER2" > "$TARGET_JSON"
  else
    printf '{\n  "mcpServers": {\n    "harness2": {\n      "command": "python",\n      "args": ["-m", "mcp_server.harness2_mcp"],\n      "cwd": "%s",\n      "env": {"HARNESS2_REPO": "%s", "HARNESS2_RUNS_DIR": "%s"}\n    }\n  }\n}\n' \
      "$ER" "$ER" "$ER2" > "$TARGET_JSON"
  fi
  echo "      [mcp] created $TARGET_JSON (pure shell)"
}

# ---------------------------------------------------------------- install_scheduler
# Idempotent. On Windows use schtasks; elsewhere crontab.
install_scheduler() {
  local DRAIN_PY="$1"
  DRAIN_PY=$(to_windows_path "$DRAIN_PY")
  if command -v schtasks >/dev/null 2>&1; then
    if schtasks /Query /TN harness2-loop-drain >/dev/null 2>&1; then
      echo "      [sched] Task Scheduler entry 'harness2-loop-drain' already exists — skip"
      return 0
    fi
    if schtasks /create /sc minute /mo 60 /tn harness2-loop-drain \
            /tr "python \"$DRAIN_PY\"" >/dev/null 2>&1; then
      echo "      [sched] registered Windows Task Scheduler (every 60 min)"
    else
      echo "      [sched] schtasks registration failed — please register manually:"
      echo "              schtasks /create /sc minute /mo 60 /tn harness2-loop-drain /tr \"python \\\"$DRAIN_PY\\\"\""
    fi
    return 0
  fi
  if command -v crontab >/dev/null 2>&1; then
    if crontab -l 2>/dev/null | grep -qF "$DRAIN_PY"; then
      echo "      [sched] cron entry already exists — skip"
      return 0
    fi
    # Drain every hour on the 0th minute (5-field cron; 6th field for seconds not needed)
    local LINE="0 * * * * python '$DRAIN_PY' >> /tmp/harness2-loop-drain.log 2>&1"
    ( crontab -l 2>/dev/null; echo "$LINE" ) | crontab -
    echo "      [sched] registered cron: $LINE"
    return 0
  fi
  echo "      [sched] no crontab / schtasks available — skip (B path still works in-session)"
}

# ---------------------------------------------------------------- opt-out check
is_disabled() {
  # $1 = project dir; return 0 if disabled, 1 otherwise.
  [ -f "$1/HARNESS2_LOOP_OFF" ]
}
