#!/bin/sh
# harness2-loop universal trigger (git post-commit)
# Works for ANY agent that uses git: opencode / antigravity / workbuddy / qoder /
# trae / cline / kiro / minimax code / agnes / claude / cursor / ...
#
# Installed to <project>/.git/hooks/post-commit. On every commit, writes a
# pending_re.json flag. Drained by MCP harness2_requeue (agent in-session) or
# a scheduled drain_requeue.py.
#
# Python is used ONLY when a working interpreter is found; otherwise it falls
# back to pure-shell JSON writing (no python required). This matters on
# Windows where `python` can be the Microsoft Store alias that errors out.
#
# Env overrides:
#   HARNESS2_LOOP_FLAG_DIR   dir to write pending_re.json into
#   HARNESS2_LOOP_BENCH      default bench (default demo)
#   HARNESS2_LOOP_MODE       default mode (default parallel)

set -u

# --- find a python that actually works (guard against the MS Store alias) ---
PYBIN=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import json" >/dev/null 2>&1; then
    PYBIN="$cand"
    break
  fi
done

# --- where to write the flag ---
FLAG_DIR="${HARNESS2_LOOP_FLAG_DIR:-$HOME/.Agnes Code/plugins/harness2-loop/.state}"
BENCH="${HARNESS2_LOOP_BENCH:-demo}"
MODE="${HARNESS2_LOOP_MODE:-parallel}"
mkdir -p "$FLAG_DIR" 2>/dev/null || {
  FLAG_DIR="$PWD/.Agnes Code/plugins/harness2-loop/.state"
  mkdir -p "$FLAG_DIR" 2>/dev/null || FLAG_DIR="$PWD/.state"
}

TS=$(date +%s)
ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
MSG=$(git log -1 --pretty=%s 2>/dev/null || echo "")
# minimal JSON-safe escaping for the subject (strip quotes/backslashes)
MSG=${MSG//\"/ }; MSG=${MSG//\\/ }

if [ -n "$PYBIN" ]; then
  "$PYBIN" - "$SHA" "$BRANCH" "$MSG" "$TS" "$ISO" "$BENCH" "$MODE" <<'PY'
import json, sys, os
sha, branch, msg, ts, iso, bench, mode = sys.argv[1:8]
flag = {
    "signal": "commit", "ts": float(ts), "iso": iso,
    "sha": sha, "branch": branch, "subject": msg,
    "source": "git.post-commit-hook",
    "recipe": "recipes/harness2-any-project.yaml",
    "params": {"bench": bench, "k": 1, "mode": mode,
               "substrate": "ags", "seed": 0,
               "dry_run": "false", "model": "agnes"},
    "runs_namespace": "continuous",
}
state = os.environ.get("HARNESS2_LOOP_FLAG_DIR") or os.path.expanduser(
    "~/.Agnes Code/plugins/harness2-loop/.state")
os.makedirs(state, exist_ok=True)
with open(os.path.join(state, "pending_re.json"), "w") as f:
    json.dump(flag, f, indent=2, ensure_ascii=False)
print("[harness2-loop] commit flag written")
PY
else
  cat > "$FLAG_DIR/pending_re.json" <<EOF
{
  "signal": "commit",
  "ts": $TS,
  "iso": "$ISO",
  "sha": "$SHA",
  "branch": "$BRANCH",
  "subject": "$MSG",
  "source": "git.post-commit-hook",
  "recipe": "recipes/harness2-any-project.yaml",
  "params": {"bench":"$BENCH","k":1,"mode":"$MODE","substrate":"ags","seed":0,"dry_run":"false","model":"agnes"},
  "runs_namespace": "continuous"
}
EOF
  echo "[harness2-loop] commit flag written (pure shell)"
fi

# Never block git
exit 0
