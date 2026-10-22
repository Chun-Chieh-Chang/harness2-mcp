#!/usr/bin/env bash
# harness2-loop quickstart dispatcher — one script for all 8 supported agents.
#
# Usage:
#   bash quickstart.sh <agent> [project_dir]
#   bash quickstart.sh --list
#
# Supported agents: opencode antigravity workbuddy qoder trae cline kiro minimax
#
# What it does (idempotent — safe to re-run):
#   [1] install the universal git post-commit hook into <project_dir>/.git/hooks/
#   [2] write the agent's MCP config (project-level JSON) non-destructively
#   [3] register a 60-minute scheduler for the off-session drain
#
# After this, ZERO manual steps are required: every commit auto-writes a
# pending flag; in-session the agent drains it via harness2_requeue; off-session
# the scheduler drains it.

set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=/dev/null
. "$HERE/common.sh"

AGENTS="opencode antigravity workbuddy qoder trae cline kiro minimax"

usage() {
  echo "Usage: $(basename "$0") <agent> [project_dir]"
  echo "       $(basename "$0") --list"
  echo ""
  echo "Agents: $AGENTS"
  echo ""
  echo "Env overrides:"
  echo "  HARNESS2_REPO         path to the harness2 repo (default: auto-detect)"
  echo "  HARNESS2_LOOP_FLAG_DIR  where the flag is written"
  echo "  HARNESS2_LOOP_BENCH / HARNESS2_LOOP_MODE"
  echo ""
  echo "Opt-out: drop a 'HARNESS2_LOOP_OFF' file in the project dir."
}

# ------------------------------------------------------------------ table: agent -> (mcp_target, style, notes)
# Relative to $1 (project dir) unless the path contains '/'.
mcp_target_for() {
  local a="$1" proj="$2"
  case "$a" in
    opencode)       echo "$proj/opencode.json" ;;
    cline)          echo "$proj/.cline/mcp.json" ;;
    trae)           echo "$proj/.trae/mcp.json" ;;
    qoder)          echo "$proj/.qoder/mcp.json" ;;
    kiro)           echo "$proj/.kiro/mcp.json" ;;
    antigravity)    echo "$proj/.antigravity/mcp.json" ;;
    minimax)        echo "$proj/.minimax/mcp.json" ;;
    workbuddy)      echo "$HOME/.workbuddy/mcp.json" ;;   # no documented project path
  esac
}
mcp_style_for() {
  # opencode uses {mcp.harness2:{type:local,command:[...],cwd,environment:{...}}}
  # others share the {mcpServers.harness2:{command:"python",args:[...],cwd,env:{...}}} shape
  case "$1" in
    opencode) echo "opencode" ;;
    *)        echo "mcpServers" ;;
  esac
}
agent_notes() {
  case "$1" in
    cline) echo "Cline: open VS Code -> Cline panel -> MCP Servers to verify; or restart the CLI." ;;
    kiro)  echo "Kiro: also has native hooks/powers — you may wire post-commit directly; flag/drain stay the same." ;;
    workbuddy) echo "WorkBuddy: no documented MCP surface — prefer the git hook + scheduler layers only." ;;
    qoder) echo "Qoder: confirm whether your build reads project (.qoder/) or user-global MCP config." ;;
    antigravity) echo "Antigravity: may keep MCP under a different key — verify against its current docs." ;;
    minimax) echo "MiniMax Code: local stdio block; confirm key name in MiniMax docs if different." ;;
    trae)  echo "Trae: project-scoped .trae/mcp.json is commitable; share with your team." ;;
  esac
}

cmd_list() {
  echo "Supported agents:"
  for a in $AGENTS; do
    printf "  %-14s -> %s   (%s)\n" "$a" "$(mcp_target_for "$a" "<project>")" "$(mcp_style_for "$a")"
  done
}

# ------------------------------------------------------------------ main
if [ "${1:-}" = "--list" ] || [ -z "${1:-}" ]; then
  if [ "${1:-}" = "--list" ]; then cmd_list; fi
  usage; exit 0
fi

AGENT="$1"; PROJECT="${2:-.}"
# Normalize to MSYS form so bash mkdir/cd and git work regardless of whether
# the caller (PowerShell/cmd) passed a Windows path (C:\...) or already-MSYS.
PROJECT=$(to_msys_path "$PROJECT")

# opt-out
if is_disabled "$PROJECT"; then
  echo "harness2-loop is disabled in $PROJECT (HARNESS2_LOOP_OFF found). Remove that file to enable."
  exit 0
fi

REPO_WIN=$(to_windows_path "$HARNESS2_REPO")
RUNS_WIN="$REPO_WIN/runs"
DRAIN_PY="$HARNESS2_REPO/.Agnes Code/plugins/harness2-loop/scripts/drain_requeue.py"

echo "== harness2-loop quickstart for $AGENT =="
echo "   project   : $PROJECT"
echo "   harness2  : $HARNESS2_REPO"
echo ""

# ---- [1] git hook
echo "[1/3] git post-commit hook ..."
install_git_hook "$PROJECT"

# ---- [2] MCP config
echo "[2/3] writing $AGENT MCP config ..."
TARGET=$(mcp_target_for "$AGENT" "$PROJECT")
STYLE=$(mcp_style_for "$AGENT")
KEYPATH="mcp.harness2"
[ "$STYLE" = "mcpServers" ] && KEYPATH="mcpServers.harness2"
write_mcp_json "$TARGET" "$KEYPATH" "$STYLE" "$REPO_WIN" "$RUNS_WIN"
agent_notes "$AGENT"

# ---- [3] scheduler
echo "[3/3] scheduler (off-session drain, every 60 min) ..."
install_scheduler "$DRAIN_PY"

echo ""
echo "✔ quickstart for $AGENT done."
echo "From now on, ZERO manual steps:"
echo "  • any git commit in $PROJECT  ->  writes a pending flag"
echo "  • $AGENT open                ->  it drains via harness2_requeue"
echo "  • $AGENT closed              ->  the 60-min scheduler drains it"
[ -n "$(agent_notes "$AGENT")" ] && echo ""
echo ""
echo "Uninstall:  rm \"$PROJECT/.git/hooks/post-commit\"   &&   delete the harness2 key in $(mcp_target_for "$AGENT" "$PROJECT")"
