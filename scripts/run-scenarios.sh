#!/usr/bin/env bash
#
# run_scenarios.sh
#
# Runs the NeST dumbbell script (fq-codel-point-to-point-dynamic.py) across
# three flow-timing scenarios, each carrying a UDP background flow, once per
# qdisc, and files the resulting NeST dump directories into:
#
#   results/<scenario>/<qdisc>/
#
# Scenarios:
#   synchronous  - all flows start at the same time
#   staggered    - flows start 1 second (1000ms) apart
#   rtt-fairness - flows start together but have different RTTs, to study
#                  RTT (un)fairness under the qdisc
#
# Every scenario also carries one UDP flow as background traffic.
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

# Resolve NeST venv python (fixes ModuleNotFoundError under sudo)
SCRIPT_DIR_RS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT_RS="$(cd "$SCRIPT_DIR_RS/.." && pwd)"
NEST_DIR_RS="$PROJECT_ROOT_RS/nest"
VENV_PYTHON="$NEST_DIR_RS/.venv/bin/python"
if [[ -x "$VENV_PYTHON" ]]; then
    PYTHON_BIN="${PYTHON_BIN:-$VENV_PYTHON}"
else
    PYTHON_BIN="${PYTHON_BIN:-python3}"
fi
# Also allow NEST_PYTHON env override (used by runExperiment.sh)
if [[ -n "${NEST_PYTHON:-}" && -x "$NEST_PYTHON" ]]; then
    PYTHON_BIN="$NEST_PYTHON"
fi
echo "Using Python: $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))"

SCRIPT="${1:-dumbbell.py}"
if [[ ! -f "$SCRIPT" ]]; then
    echo "Cannot find the NeST script at '$SCRIPT'." >&2
    echo "Usage: sudo $0 [path-to-script.py]" >&2
    exit 1
fi

# Allow caller to override RESULTS_DIR (e.g. /home/sahil/.../results or .../nest/results)
RESULTS_DIR="${RESULTS_DIR:-results}"
# Default to fq_pie with kernel lab defaults (limit 100, flows 2, target 15ms)
QDISCS=("fq_pie")
#SCENARIOS=("synchronous" "staggered" "pulsewave" "rtt-fairness" "udp-background")
SCENARIOS=("synchronous")

# Settings shared by every scenario: 100 TCP flows, 0 UDP (as in dumbbell.py defaults)
# Use FQ-PIE defaults: limit 100, flows 2, target 15ms (override via --qdisc-params if needed)
# Example custom target: --qdisc-params '{"target":"2ms"}'
DURATION=100
UDP_RATE="100mbit"
# Optional: override FQ-PIE target (leave empty for defaults).
# Can be passed from env, e.g. QDISC_PARAMS='{"target":"5ms"}' sudo -E ./run-scenarios.sh
# QDISC_PARAMS='{"target":"15ms"}'  # default
QDISC_PARAMS="${QDISC_PARAMS:-}"

# Per-scenario overrides. Same RTTs for "synchronous"/"staggered" so that
# only the start-time behaviour differs between them; "rtt-fairness" keeps
# a synchronous start but gives each TCP flow a different RTT.
declare -A SCENARIO_ARGS=(
    [synchronous]="-n 100 --start-gap 0"
    #[staggered]="-n 100 --start-gap 100"
    #[pulsewave]="-n 100 --start-gap 0 --pulsebw --high-bw 100mbit --low-bw 50mbit --pulse-interval 10"
    #[rtt-fairness]="-n 100 --start-gap 0 --tcp-rtts 20,20,20,30,40,40,40,50,60,60,60,70,80,90,100,100,100,110,120,120,130,140,150,160,170,180,190,200,200,200,210,210,220,220,230,230,240,240,250,250,250,260,260,270,270,280,280,290,300,300,300,310,320,320,330,340,340,350,360,360,370,380,390,400,400,400,410,420,420,430,440,450,460,470,480,490,500,500,510,520,530,540,540,550,560,560,560,570,580,590,600,610,620,630,640,650,660,680,700,720 --udp-rtts 40"  
    #[udp-background]="-n 50 -k 5 --start-gap 0"
)

mkdir -p "$RESULTS_DIR"

for scenario in "${SCENARIOS[@]}"; do
    for qdisc in "${QDISCS[@]}"; do
        exp_name="${scenario}_${qdisc}"
        echo "=============================================="
        echo "Scenario: $scenario | Qdisc: $qdisc"
        echo "=============================================="

        if [[ -n "${QDISC_PARAMS}" ]]; then
            "$PYTHON_BIN" "$SCRIPT" \
                --duration "$DURATION" \
                --udp-rates "$UDP_RATE" \
                --qdisc "$qdisc" \
                --qdisc-params "$QDISC_PARAMS" \
                --experiment-name "$exp_name" \
                ${SCENARIO_ARGS[$scenario]}
        else
            "$PYTHON_BIN" "$SCRIPT" \
                --duration "$DURATION" \
                --udp-rates "$UDP_RATE" \
                --qdisc "$qdisc" \
                --experiment-name "$exp_name" \
                ${SCENARIO_ARGS[$scenario]}
        fi

        # Locate the dump directory this run just created, e.g.
        # "synchronous_fq_pie(12-07-2026-21:30:27)_dump"
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
chmod 777 "$RESULTS_DIR"
echo "All scenarios complete. Results are under '${RESULTS_DIR}/'."