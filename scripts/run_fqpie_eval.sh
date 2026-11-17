#!/usr/bin/env bash
#
# run_fqpie_eval.sh - root wrapper for scripts/fqpie_eval.py
#
# Runs the canonical FQ-PIE sweep:
#   5 traffic scenarios x 8 cases x 4 targets x 4 iterations, TCP CUBIC.
#   Scenarios: synchronous, staggered, rtt_fairness, pulse_wave, udp_background.
# NeST needs root, so use sudo -E. Results go to wirelesss_final/.
#
# Examples:
#   sudo -E bash scripts/run_fqpie_eval.sh --dry-run
#   sudo -E bash scripts/run_fqpie_eval.sh
#   sudo -E bash scripts/run_fqpie_eval.sh --only bw10mbit
#   sudo -E bash scripts/run_fqpie_eval.sh --scenarios staggered udp_background
#   sudo -E bash scripts/run_fqpie_eval.sh --no-plots          # data only
#   sudo -E bash scripts/run_fqpie_eval.sh --targets "5 10 15 30"
#   sudo -E bash scripts/run_fqpie_eval.sh --repeat 1 --duration 40 --only bw100mbit
#   nest/.venv/bin/python scripts/fqpie_eval.py --plot-only
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NEST_PYTHON="$PROJECT_ROOT/nest/.venv/bin/python"
OUTPUT_ROOT="$PROJECT_ROOT/wirelesss_final"

cd "$PROJECT_ROOT"

if [[ ! -x "$NEST_PYTHON" ]]; then
    echo "NeST virtualenv python not found at: $NEST_PYTHON" >&2
    echo "Build NeST first (see installation.md) or set up nest/.venv." >&2
    exit 1
fi

# NeST / 100-flow experiments need a large file-descriptor limit.
ulimit -n 65535 2>/dev/null || true

"$NEST_PYTHON" "$SCRIPT_DIR/fqpie_eval.py" --output-root "$OUTPUT_ROOT" "$@"
RC=$?

# Results are written as root; hand them back to the invoking user so that
# plotting / browsing does not need sudo afterwards.
if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
    chown -R "$SUDO_USER:$SUDO_USER" "$OUTPUT_ROOT" 2>/dev/null || true
fi

exit "$RC"
