#!/bin/sh
# Universal build-failure trigger (manual one-liner).
#
# Agents without user-defined event hooks (opencode / cline / kiro / minimax /
# workbuddy / qoder / antigravity / trae ...) still let you CATCH a failing
# build/test in the terminal. Run your build/test, and on failure call this.
# It writes the same pending_re.json flag the git post-commit hook writes.
#
# Usage:
#   (cargo test || sh record-build-failure.sh cargo test)
#   (npm test  || sh record-build-failure.sh npm test)
#
# Then drain via MCP harness2_requeue or a scheduled drain_requeue.py.
#
# Python is used only when a working interpreter is found (guard against the
# Windows Microsoft Store `python` alias); otherwise pure-shell JSON is written.
#
# Env overrides: HARNESS2_LOOP_FLAG_DIR / HARNESS2_LOOP_BENCH / HARNESS2_LOOP_MODE

set -u
CWD="$PWD"
BENCH="${HARNESS2_LOOP_BENCH:-demo}"
MODE="${HARNESS2_LOOP_MODE:-parallel}"

PYBIN=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import json" >/dev/null 2>&1; then
    PYBIN="$cand"; break
  fi
done

if [ -n "$PYBIN" ]; then
  exec "$PYBIN" - "$*" "$CWD" "${HARNESS2_LOOP_BENCH:-demo}" "${HARNESS2_LOOP_MODE:-parallel}" <<'PY'
import json, sys, os
cmd, cwd, bench, mode = sys.argv[1:5]
flag = {
    "signal": "build-failure", "ts": __import__("time").time(),
    "iso": __import__("datetime").datetime.utcnow().isoformat(timespec="seconds")+"Z",
    "command": cmd, "cwd": cwd, "source": "manual.build-failure",
    "recipe": "recipes/harness2-any-project.yaml",
    "params": {"bench": bench, "k": 1, "mode": mode,
               "substrate": "ags", "seed": 0, "dry_run": "false", "model": "agnes"},
    "runs_namespace": "continuous",
}
state = os.environ.get("HARNESS2_LOOP_FLAG_DIR") or os.path.expanduser(
    "~/.Agnes Code/plugins/harness2-loop/.state")
os.makedirs(state, exist_ok=True)
open(os.path.join(state, "pending_re.json"), "w").write(
    json.dumps(flag, indent=2, ensure_ascii=False))
print("[harness2-loop] build-failure flag written (%s)" % cmd)
PY
fi

# pure-shell fallback
FLAG_DIR="${HARNESS2_LOOP_FLAG_DIR:-$HOME/.Agnes Code/plugins/harness2-loop/.state}"
mkdir -p "$FLAG_DIR" 2>/dev/null || FLAG_DIR="$CWD/.state" && mkdir -p "$FLAG_DIR" 2>/dev/null
TS=$(date +%s); ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ); CMD="$*"
cat > "$FLAG_DIR/pending_re.json" <<EOF
{
  "signal": "build-failure",
  "ts": $TS, "iso": "$ISO",
  "command": "$CMD", "cwd": "$CWD",
  "source": "manual.build-failure",
  "recipe": "recipes/harness2-any-project.yaml",
  "params": {"bench":"$BENCH","k":1,"mode":"$MODE","substrate":"ags","seed":0,"dry_run":"false","model":"agnes"},
  "runs_namespace": "continuous"
}
EOF
echo "[harness2-loop] build-failure flag written ($CMD)"
exit 0
