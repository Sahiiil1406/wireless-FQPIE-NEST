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

SCRIPT="${1:-fq-codel-point-to-point-dynamic.py}"
if [[ ! -f "$SCRIPT" ]]; then
    echo "Cannot find the NeST script at '$SCRIPT'." >&2
    echo "Usage: sudo $0 [path-to-script.py]" >&2
    exit 1
fi

RESULTS_DIR="results"
#QDISCS=("fq_codel" "codel","fq_pie")
QDISCS=("fq_pie")
#SCENARIOS=("synchronous" "staggered" "pulsewave" "rtt-fairness" "udp-background")
SCENARIOS=("synchronous")

# Settings shared by every scenario: 3 TCP flows + 1 UDP background flow.
DURATION=100
UDP_RATE="100mbit"

# Per-scenario overrides. Same RTTs for "synchronous"/"staggered" so that
# only the start-time behaviour differs between them; "rtt-fairness" keeps
# a synchronous start but gives each TCP flow a different RTT.
declare -A SCENARIO_ARGS=(
    #[synchronous]="-n 100 --start-gap 0"
    [synchronous]="-n 20 --start-gap 0"
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

        python3 "$SCRIPT" \
            --duration "$DURATION" \
            --udp-rates "$UDP_RATE" \
            --qdisc "$qdisc" \
            --experiment-name "$exp_name" \
            ${SCENARIO_ARGS[$scenario]}

        # Locate the dump directory this run just created, e.g.
        # "synchronous_fq_codel(12-07-2026-21:30:27)_dump"
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