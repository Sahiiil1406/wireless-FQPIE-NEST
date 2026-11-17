#!/usr/bin/env bash
#
# run_fqpie_eval_rootless.sh - run the FQ-PIE sweep without sudo.
#
# NeST needs root to create network namespaces.  If you cannot use sudo you can
# still run the suite inside an unprivileged user namespace: the kernel then
# gives this process CAP_NET_ADMIN over its own network namespace, which is all
# NeST needs.  The only extra requirement is that /run/netns is writable, so we
# mount a private tmpfs there for the lifetime of the run.
#
# Usage (identical flags to scripts/run_fqpie_eval.sh):
#   bash scripts/run_fqpie_eval_rootless.sh --dry-run
#   bash scripts/run_fqpie_eval_rootless.sh --only bw10mbit
#   bash scripts/run_fqpie_eval_rootless.sh --only bw100mbit --repeat 3
#   bash scripts/run_fqpie_eval_rootless.sh --only bw10mbit --targets "200 300 450"
#
# Results are written to wirelesss_final/ exactly as with the sudo wrapper.
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NEST_PYTHON="$PROJECT_ROOT/nest/.venv/bin/python"
OUTPUT_ROOT="$PROJECT_ROOT/wirelesss_final"

if [[ ! -x "$NEST_PYTHON" ]]; then
    echo "NeST virtualenv python not found at: $NEST_PYTHON" >&2
    exit 1
fi

if ! unshare -Ur true 2>/dev/null; then
    echo "Unprivileged user namespaces are not available on this host." >&2
    echo "Use the sudo wrapper instead: sudo -E bash scripts/run_fqpie_eval.sh ..." >&2
    exit 1
fi

# Re-exec inside a user + mount + network namespace.  Inside it we are uid 0
# and own the network namespace, so NeST's `ip netns`/`tc` calls succeed.
exec unshare -Urmn bash -c '
set -uo pipefail
mount -t tmpfs tmpfs /run/netns
ulimit -n 65535 2>/dev/null || true
cd "$1"
exec "$2" "$3/fqpie_eval.py" --output-root "$4" "${@:5}"
' _ "$PROJECT_ROOT" "$NEST_PYTHON" "$SCRIPT_DIR" "$OUTPUT_ROOT" "$@"
