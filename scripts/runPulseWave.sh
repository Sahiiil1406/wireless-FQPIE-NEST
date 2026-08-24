#!/usr/bin/env bash
#
# run_scenarios.sh
#
# Runs the NeST dumbbell script (dumbbell.py) across multiple flow-timing 
# scenarios, each carrying a UDP background flow, once per qdisc, and files 
# the resulting NeST dump directories into:
#
#   results/<scenario>/<qdisc>/
#
# Scenarios:
#   synchronous  - all flows start at the same time
#   staggered    - flows start 100ms apart
#   pulsewave    - bottleneck bandwidth toggles (100Mbps <-> 50Mbps every 10s)
#   rtt-fairness - flows start together but have different RTTs
#
# Usage:
#   sudo ./run_scenarios.sh 
#
# Must be run as root, since NeST requires root privileges.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (NeST requires root privileges)." >&2
    exit 1
fi

SCRIPT="${1:-pulseWave.py}"
if [[ ! -f "$SCRIPT" ]]; then
    echo "Cannot find the NeST script at '$SCRIPT'." >&2
    echo "Usage: sudo $0 [path-to-script.py]" >&2
    exit 1
fi

RESULTS_DIR="results"
QDISCS=("fq_pie")
SCENARIOS=("pulsewave")

# Settings shared by every scenario
DURATION=100
UDP_RATE="100mbit"

# Per-scenario overrides
declare -A SCENARIO_ARGS=(
   # [synchronous]="-n 100 --start-gap 0"
   # [staggered]="-n 100 --start-gap 100"
    [pulsewave]="-n 75 --start-gap 0 --pulsebw --high-bw 100mbit --low-bw 50mbit --pulse-interval 10"
   # [rtt-fairness]="-n 100 --start-gap 0 --tcp-rtts 20,40,60,80,100 --udp-rtts 40"
   # [udp-background]="-n 50 -k 5 --start-gap 0"
)

mkdir -p "$RESULTS_DIR"

for scenario in "${SCENARIOS[@]}"; do
    for qdisc in "${QDISCS[@]}"; do
        exp_name="${scenario}_${qdisc}"
        echo "=============================================="
        echo "Scenario: $scenario | Qdisc: $qdisc"
        echo "=============================================="

        python3 "$SCRIPT" \
            --duration "$DURATION" \
            --udp-rates "$UDP_RATE" \
            --qdisc "$qdisc" \
            --experiment-name "$exp_name" \
            ${SCENARIO_ARGS[$scenario]}

        # Locate the dump directory created for this run
        dump_dir=$(find . -maxdepth 1 -type d -name "${exp_name}(*)_dump" | sort | tail -n 1)

        if [[ -z "$dump_dir" ]]; then
            echo "Warning: no dump directory found for '$exp_name'; skipping move." >&2
            continue
        fi

        dest="${RESULTS_DIR}/${scenario}/${qdisc}"
        mkdir -p "$dest"
        mv "$dump_dir" "$dest/"
        echo "Moved '$dump_dir' -> '$dest/'"
        echo
    done
done

chmod -R 777 "$RESULTS_DIR"
echo "All scenarios complete. Results are under '${RESULTS_DIR}/'."
