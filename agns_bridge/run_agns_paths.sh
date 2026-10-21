#!/usr/bin/env bash
# Desktop runner for the Agnes + Harness^2 experiment. Linux/macOS.
# Usage:
#   ./agns_bridge/run_agns_paths.sh a      # Path A: start the OpenAI-compatible bridge (foreground)
#   ./agns_bridge/run_agns_paths.sh b      # Path B: run the no-credential Agnes substrate demo
#   ./agns_paths.sh all                    # run B, then A
set -euo pipefail

# Resolve repo root (two levels up from agnes_bridge/)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Ensure an editable install exists (no-op if already installed).
if ! python -c "import harness2" 2>/dev/null; then
  echo "Installing harness2 in editable mode..."
  python -m pip install -e . || { echo "pip install failed; create a venv first"; exit 1; }
fi

cmd="${1:-all}"

run_path_b() {
  echo "=== Path B: Agnes substrate, deterministic demo (no model credentials) ==="
  python -m harness2.cli.agns_demo --output runs/agns_demo --k 2 --mode both
}

run_path_a() {
  echo "=== Path A: Agnes OpenAI-compatible bridge ==="
  echo "Fill .agns_bridge.env with your Agnes endpoint, then start the bridge:"
  if [[ -f .agns_bridge.env ]]; then
    set -a; source .agns_bridge.env; set +a
  fi
  if [[ -z "${AGNES_API_URL:-}" ]]; then
    echo "AGNES_API_URL not set; run the bridge anyway (it will 503 until you set it)."
  fi
  echo "Open a SECOND shell and wire harness2 at the bridge:"
  echo "  export OPENAI_BASE_URL=http://${AGNES_PROXY_HOST:-127.0.0.1}:${AGNES_PROXY_PORT:-8620}/v1"
  echo "  export HARNESS2_SOLVER_MODEL=openai/${AGNES_MODEL:-agnes}"
  echo "  python -m harness2.cli.run_sweep --bench jb --substrate oc --k 1 --mode parallel"
  exec python -m agnes_bridge.agnes_openai_proxy
}

case "$cmd" in
  b) run_path_b ;;
  a) run_path_a ;;
  all) run_path_b; echo; run_path_a ;;
  *) echo "Usage: $0 {a|b|all}"; exit 2 ;;
esac
