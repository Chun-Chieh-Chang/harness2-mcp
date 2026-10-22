#!/bin/sh
# Install the harness2-loop universal git trigger into a project's git hooks.
# Usage:
#   sh install.sh                       # install into the current project
#   sh install.sh /path/to/your-project # install into a specific project
#
# What it does:
#   - copies post-commit.sh into <project>/.git/hooks/post-commit
#   - makes it executable
#   - the hook writes a pending_re.json flag on every commit; the flag is
#     drained by MCP harness2_requeue (agent in-session) or by a scheduled
#     drain_requeue.py.
#
# This works for ANY agent (opencode / antigravity / workbuddy / qoder /
# trae / cline / kiro / minimax code / ...) because they all use git.

set -u
HERE=$(cd "$(dirname "$0")" && pwd)
TARGET="${1:-$PWD}"

# walk up to find the .git dir
GITDIR=""
d="$TARGET"
while [ -n "$d" ] && [ "$d" != "/" ]; do
  if [ -d "$d/.git" ] && [ -d "$d/.git/hooks" ]; then GITDIR="$d/.git"; break; fi
  # git worktrees: .git is a file pointing to the real dir
  if [ -f "$d/.git" ]; then
    real=$(cat "$d/.git" | sed 's/^gitdir: *//')
    case "$real" in
      /*) [ -d "$real" ] && { GITDIR="$real"; break; } ;;
      *)  [ -d "$d/$real" ] && { GITDIR="$d/$real"; break; } ;;
    esac
  fi
  d=$(dirname "$d")
done

if [ -z "$GITDIR" ]; then
  echo "ERROR: no .git found under $TARGET. Run this from a git project." >&2
  exit 1
fi

HOOKS="$GITDIR/hooks"
cp "$HERE/post-commit.sh" "$HOOKS/post-commit"
chmod +x "$HOOKS/post-commit"

# optionally export a stable flag dir to the hook via a wrapper env file
echo "[harness2-loop] installed universal git trigger -> $HOOKS/post-commit"
echo ""
echo "Every 'git commit' in this project now writes a pending_re.json flag."
echo "Drain it by (pick one):"
echo "  - in any MCP agent:  call the 'harness2_requeue' MCP tool"
echo "  - off-session:        python .../scripts/drain_requeue.py   (or a scheduler)"
echo ""
echo "Override the flag dir / bench / mode via env before committing:"
echo "  HARNESS2_LOOP_FLAG_DIR=... HARNESS2_LOOP_BENCH=demo HARNESS2_LOOP_MODE=parallel git commit -m '...'"
echo ""
echo "Uninstall: rm '$HOOKS/post-commit'"
