#!/usr/bin/env bash
# harness2-loop ZERO-TOUCH installer.
#
# Run ONCE. After this, you never run a quickstart again:
#   * EVERY git project (repo-wide, via global hook template dir) writes a
#     pending flag on commit — no per-project install, no agent involved.
#   * ONE scheduler drains the flag off-session every 60 minutes.
#   * Any AI agent (or no agent) can drain it in-session via harness2_requeue.
#
# Cost / blast radius:
#   * git global config gains: core.hooksTemplateDir + harness2.loop.* keys.
#   * A git hook template is copied to <repo>/.Agnes Code/.../hooks-template/.
#   * To disable: bash <this> --uninstall
#
# Opt-out per project: create a file named HARNESS2_LOOP_OFF in the project.

set -u
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=/dev/null
. "$HERE/common.sh"

GLOBAL_HOOKS="$HOME/.harness2-loop-hooks"
DRAIN_PY="$HARNESS2_REPO/.Agnes Code/plugins/harness2-loop/scripts/drain_requeue.py"

# ------------------------------------------------------------------ hook template
HOOK_TEMPLATE="$GLOBAL_HOOKS/post-commit"

make_hook_template() {
  mkdir -p "$GLOBAL_HOOKS"
  # The template body is the SAME logic as adapters/git/post-commit.sh. We copy
  # it so zero-touch users don't depend on the harness2 repo staying mounted.
  if [ -f "$HARNESS2_REPO/multi-agent/adapters/git/post-commit.sh" ]; then
    cp "$HARNESS2_REPO/multi-agent/adapters/git/post-commit.sh" "$HOOK_TEMPLATE"
    chmod +x "$HOOK_TEMPLATE" 2>/dev/null || true
    echo "      hook template installed: $HOOK_TEMPLATE"
  else
    echo "      WARN: could not find adapters/git/post-commit.sh under $HARNESS2_REPO"
    echo "            — generating a minimal template instead."
    cat > "$HOOK_TEMPLATE" <<'EOS'
#!/bin/sh
# minimal harness2-loop flag writer (zero-touch)
set -u
FLAG_DIR="${HARNESS2_LOOP_FLAG_DIR:-$HOME/.Agnes Code/plugins/harness2-loop/.state}"
[ -f "$0/../HARNESS2_LOOP_OFF" ] && exit 0   # project opt-out via marker next to hook? (best-effort)
mkdir -p "$FLAG_DIR" 2>/dev/null || { FLAG_DIR="$PWD/.state"; mkdir -p "$FLAG_DIR"; }
TS=$(date +%s); ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SHA=$(git rev-parse HEAD 2>/dev/null || echo unknown)
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
MSG=$(git log -1 --pretty=%s 2>/dev/null || echo "")
MSG=${MSG//\"/ }; MSG=${MSG//\\/ }
cat > "$FLAG_DIR/pending_re.json" <<EOF
{ "signal": "commit", "ts": $TS, "iso": "$ISO", "sha": "$SHA",
  "branch": "$BRANCH", "subject": "$MSG",
  "source": "git.post-commit-hook",
  "recipe": "recipes/harness2-any-project.yaml",
  "params": {"bench":"demo","k":1,"mode":"parallel","substrate":"ags","seed":0,"dry_run":"false","model":"agnes"},
  "runs_namespace": "continuous" }
EOF
exit 0
EOS
  fi
}

install_global() {
  echo "Configuring git global (one-time) ..."
  make_hook_template
  git config --global core.hooksTemplateDir "$GLOBAL_HOOKS"
  echo "      core.hooksTemplateDir -> $GLOBAL_HOOKS"
  # tag every repo as harness2-managed so we can uninstall cleanly later
  echo "Install this on ALL git repos? (global template dir applies to every 'git init'). Say 'y'."
  read -r ans
  if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
    : # global already set; new repos auto-inherit. Existing repos need one re-init or manual hook copy.
    echo "      New repos auto-inherit. For EXISTING repos, run: "
    echo "        for d in */.git; do cp \"$GLOBAL_HOOKS/post-commit\" \"${d%/*}/post-commit\"; done   (adjust as needed)"
  fi
}

# ------------------------------------------------------------------ main
case "${1:-}" in
  --uninstall)
    echo "Uninstalling zero-touch ..."
    git config --global --unset core.hooksTemplateDir 2>/dev/null || echo "      (no global hook template to remove)"
    if command -v schtasks >/dev/null 2>&1; then
      schtasks /Delete /TN harness2-loop-drain /F >/dev/null 2>&1 && echo "      removed Task Scheduler entry" || echo "      (no Task Scheduler entry)"
    fi
    if command -v crontab >/dev/null 2>&1; then
      crontab -l 2>/dev/null | grep -vF "$DRAIN_PY" | crontab - 2>/dev/null && echo "      removed cron entry" || echo "      (no cron entry)"
    fi
    rm -rf "$GLOBAL_HOOKS" 2>/dev/null || true
    echo "✔ zero-touch removed. Project opt-out files (HARNESS2_LOOP_OFF) are unaffected."
    exit 0
    ;;
  --help|-h|"")
    cat <<'TXT'
harness2-loop zero-touch installer
  bash zero-touch-setup.sh            # install (git global + scheduler)
  bash zero-touch-setup.sh --uninstall# remove everything
Per-project opt-out: create a file named HARNESS2_LOOP_OFF in that project.
TXT
    exit 0
    ;;
esac

install_global

echo ""
echo "[scheduler] registering off-session drain ..."
install_scheduler "$DRAIN_PY"

echo ""
echo "✔ ZERO-TOUCH ready."
echo "   • git commit in ANY repo now writes a pending flag automatically."
echo "   • In-session: any MCP agent (incl. opencode/Cline/…) drains via harness2_requeue."
echo "   • Off-session: the 60-minute scheduler drains."
echo "   • To opt a project out:  touch <project>/HARNESS2_LOOP_OFF"
echo "   • To fully remove:       bash $(basename "$0") --uninstall"
