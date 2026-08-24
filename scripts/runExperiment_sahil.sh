#!/bin/bash
# runExperiment_sahil.sh - FQ-PIE 25x harness for local path /home/sahil/Desktop/wireless-FQPIE-NEST
# Based on scripts/runExperiment.sh (lean version) with /home/deepa/nest replaced by local REPO_ROOT
# Usage: sudo bash scripts/runExperiment_sahil.sh  (must be root for NeST)

set -e  # optional: exit on error; comment out if you prefer original set +e behavior

REPO_ROOT="/home/sahil/Desktop/wireless-FQPIE-NEST"
SCRIPTS_DIR="$REPO_ROOT/scripts"
NEST_PYTHON="$REPO_ROOT/nest/.venv/bin/python"

KEYS=("cwnd" "rtt" "dev_rtt" "ssthresh" "rto" "delivery_rate" "pacing_rate")
KEYS1=("bytes" "packets" "drops" "overlimits" "requeues" "backlog" "qlen" "count" "lastcount" "ldelay" "drop_next" "maxpacket" "drop_overlimit")
COOLDOWN_SEC=3

# Run the experiment 25 times (comment says 5 times in original, loop is 1..25)
for i in {1..25}
do
    echo "Running experiment iteration $i..."

    cd "$REPO_ROOT"
    # Run single dumbbell experiment via orchestrator
    # sudo bash -c "ulimit -n 65535 && env \"PATH=\$PATH\" $SCRIPTS_DIR/run-scenarios.sh $SCRIPTS_DIR/dumbbell.py"
    sudo bash -c "ulimit -n 65535 && env PATH=\"$REPO_ROOT/nest/.venv/bin:\$PATH\" $SCRIPTS_DIR/run-scenarios.sh $SCRIPTS_DIR/dumbbell.py"
    # Alternative pulse-wave: sudo bash -c "ulimit -n 65535 && env \"PATH=\$PATH\" $SCRIPTS_DIR/runPulseWave.sh $SCRIPTS_DIR/pulseWave.py"

    # Explicitly clean up any orphan NeST namespaces/processes between runs
    sudo ip -all netns delete 2>/dev/null || true
    sudo pkill -f netperf 2>/dev/null || true
    sudo pkill -f iperf3 2>/dev/null || true

    OUTPUT_FOLDER="$REPO_ROOT/fq_pie_dat_files"
    mkdir -p "$OUTPUT_FOLDER"
    chmod 777 "$OUTPUT_FOLDER"
    cd "$OUTPUT_FOLDER"
    mkdir -p netperf_sender ping netperf_receiver

    sudo chmod 777 "$REPO_ROOT/results" 2>/dev/null || true
    # Results are filed by run-scenarios.sh into results/<scenario>/<qdisc>/
    cd "$REPO_ROOT/results/synchronous/fq_pie" 2>/dev/null || { echo "Results dir not found, skipping iteration $i"; continue; }
    # Other scenarios (uncomment to use):
    #cd "$REPO_ROOT/results/staggered/fq_pie"
    #cd "$REPO_ROOT/results/rtt-fairness/fq_pie"
    #cd "$REPO_ROOT/results/pulsewave/fq_pie"
    #cd "$REPO_ROOT/results/udp-background/fq_pie"

    OUTPUT_DIR=$(ls -dt synchronous_*dump 2>/dev/null | head -n 1)
    #OUTPUT_DIR=$(ls -dt staggered_*dump | head -n 1)
    #OUTPUT_DIR=$(ls -dt rtt-fairness_*dump | head -n 1)
    #OUTPUT_DIR=$(ls -dt pulsewave_*dump | head -n 1)
    #OUTPUT_DIR=$(ls -dt udp-background_*dump | head -n 1)
    #OUTPUT_DIR=$(ls -dt fq_pie_$i | head -n 1)

    if [[ -d $OUTPUT_DIR ]]; then
        RENAMED_DIR="$REPO_ROOT/results/synchronous/fq_pie/fq_pie_$i"
        #RENAMED_DIR="$REPO_ROOT/results/staggered/fq_pie/fq_pie_$i"
        #RENAMED_DIR="$REPO_ROOT/results/rtt-fairness/fq_pie/fq_pie_$i"
        #RENAMED_DIR="$REPO_ROOT/results/pulsewave/fq_pie/fq_pie_$i"
        #RENAMED_DIR="$REPO_ROOT/results/udp-background/fq_pie/fq_pie_$i"

        sudo mv "$OUTPUT_DIR" "$RENAMED_DIR"
        echo "Renamed directory $OUTPUT_DIR to $RENAMED_DIR"
        cd "$REPO_ROOT"

        # Process sending_rate from iperf3.json
        JSON_INPUT="${RENAMED_DIR}/iperf3.json"
        DAT_OUTPUT="${OUTPUT_FOLDER}/netperf_sender/netperf${i}.dat"
        [[ -f $JSON_INPUT ]] && python3 "$SCRIPTS_DIR/netperf_ping.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k sending_rate

        # Process receiving_rate from iperfServer.json
        JSON_INPUT="${RENAMED_DIR}/iperf3Server.json"
        DAT_OUTPUT="${OUTPUT_FOLDER}/netperf_receiver/iperf3Server${i}.dat"
        [[ -f $JSON_INPUT ]] && python3 "$SCRIPTS_DIR/netperf_ping.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k receiving_rate

        # Process rtt from ping.json
        JSON_INPUT="${RENAMED_DIR}/ping.json"
        DAT_OUTPUT="${OUTPUT_FOLDER}/ping/ping${i}.dat"
        [[ -f $JSON_INPUT ]] && python3 "$SCRIPTS_DIR/netperf_ping.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k rtt

        for KEY in "${KEYS[@]}"; do
            JSON_INPUT="${RENAMED_DIR}/ss.json"
            DAT_OUTPUT="${OUTPUT_FOLDER}/ss_${KEY}${i}.dat"
            [[ -f $JSON_INPUT ]] && python3 "$SCRIPTS_DIR/SS_TC.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k "$KEY"
        done

        for KEY1 in "${KEYS1[@]}"; do
            JSON_INPUT="${RENAMED_DIR}/tc.json"
            DAT_OUTPUT="${OUTPUT_FOLDER}/tc_${KEY1}${i}.dat"
            [[ -f $JSON_INPUT ]] && python3 "$SCRIPTS_DIR/SS_TC.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k "$KEY1"
        done
    else
        echo "Output directory not found!"
    fi
    echo "Iteration $i completed."
    echo "-----------------------------------"
    echo "Cooling down for ${COOLDOWN_SEC}s..."
    sleep "$COOLDOWN_SEC"
done

cd "$REPO_ROOT/fq_pie_dat_files"
# Create folders for KEYS (SS files)
for KEY in "${KEYS[@]}"; do
    mkdir -p "$KEY"
done
for KEY1 in "${KEYS1[@]}"; do
    mkdir -p "$KEY1"
done

# Move SS files to their respective folders
for KEY in "${KEYS[@]}"; do
    echo "Looking for files matching pattern *ss_${KEY}*.dat"
    if ls *"ss_${KEY}"*.dat 1>/dev/null 2>&1; then
        mv *"ss_${KEY}"*.dat "${KEY}/"
        echo "Moved ss_${KEY}*.dat files to $KEY/"
    else
        echo "No files found for key: $KEY"
    fi
done

# Move TC files to their respective folders
for KEY1 in "${KEYS1[@]}"; do
    echo "Looking for files matching pattern *tc_${KEY1}*.dat"
    if ls *"tc_${KEY1}"*.dat 1>/dev/null 2>&1; then
        mv *"tc_${KEY1}"*.dat "$KEY1/"
        echo "Moved *tc_${KEY1}*.dat files to $KEY1/"
    else
        echo "No files found for key: $KEY1"
    fi
done

echo "Files have been organized into folders by keys."
echo "All iterations completed."

# Ensure the working directory is correct
cd "$REPO_ROOT"
mkdir -p comparison
FOLDER_PATH="$REPO_ROOT/fq_pie_dat_files"

# Find all subdirectories in FOLDER_PATH and process them
find "$FOLDER_PATH" -type d | while read -r SUBDIR; do
    BASENAME=$(basename "$SUBDIR")
    OUTPUT_FILE="$REPO_ROOT/comparison/fq_pie_${BASENAME}.dat"
    rm -f "$OUTPUT_FILE"
    python3 "$SCRIPTS_DIR/averagedat.py" -i "$SUBDIR" -o "$OUTPUT_FILE"
    if [[ "$BASENAME" == *"ldelay"* || "$BASENAME" == *"qdelay"* ]]; then
        if [ -f "$OUTPUT_FILE" ]; then
            awk '{if (NF >= 2) print $1, $2/1000; else print $0}' "$OUTPUT_FILE" > "${OUTPUT_FILE}.tmp" \
                && mv "${OUTPUT_FILE}.tmp" "$OUTPUT_FILE"
            echo "[Converted] $OUTPUT_FILE values converted from us to ms."
        fi
    fi
    echo "Processed directory $SUBDIR and saved results to $OUTPUT_FILE"
done

# Create symlinks for bulk_plot.py compatibility (single_plots + cmp_defs suffix)
# single_plots expects throughput.dat, qdelay.dat, cwnd.dat etc. in comparison/
COMP="$REPO_ROOT/comparison"
declare -A MAP=( ["throughput.dat"]="fq_pie_netperf_receiver.dat" ["qdelay.dat"]="fq_pie_ldelay.dat" ["queueSize.dat"]="fq_pie_qlen.dat" ["cwnd.dat"]="fq_pie_cwnd.dat" ["rtt.dat"]="fq_pie_rtt.dat" ["count.dat"]="fq_pie_count.dat" ["dropnext.dat"]="fq_pie_drop_next.dat" ["qdrops.dat"]="fq_pie_drops.dat" ["inflight.dat"]="fq_pie_packets.dat" ["linkutil.dat"]="fq_pie_bytes.dat" ["pdrop.dat"]="fq_pie_drops.dat" )
for dst in "${!MAP[@]}"; do
    src="${MAP[$dst]}"
    if [[ -f "$COMP/$src" && ! -e "$COMP/$dst" ]]; then ln -sf "$src" "$COMP/$dst"; fi
    # cmp suffix variant: qdelay_fq_pie.dat etc. -> fq_pie_qdelay.dat
    suffix="${dst%.dat}_fq_pie.dat"
    if [[ -f "$COMP/$src" && ! -e "$COMP/$suffix" ]]; then ln -sf "$src" "$COMP/$suffix"; fi
done
# additional cmp prefixes: pdrop, qdrops, linkutil, queueSize need aliases
for src in fq_pie_drops.dat fq_pie_ldelay.dat fq_pie_bytes.dat fq_pie_qlen.dat fq_pie_drop_next.dat fq_pie_count.dat; do
    base="${src#fq_pie_}"; base="${base%.dat}"
    # map actual base to cmp prefix
    case "$base" in
        drops) for p in pdrop qdrops; do [[ -f "$COMP/$src" && ! -e "$COMP/${p}_fq_pie.dat" ]] && ln -sf "$src" "$COMP/${p}_fq_pie.dat"; done ;;
        ldelay) for p in qdelay pieqdelay; do [[ -f "$COMP/$src" && ! -e "$COMP/${p}_fq_pie.dat" ]] && ln -sf "$src" "$COMP/${p}_fq_pie.dat"; done ;;
        bytes) [[ -f "$COMP/$src" && ! -e "$COMP/linkutil_fq_pie.dat" ]] && ln -sf "$src" "$COMP/linkutil_fq_pie.dat" ;;
        qlen) for p in queueSize qsize; do [[ -f "$COMP/$src" && ! -e "$COMP/${p}_fq_pie.dat" ]] && ln -sf "$src" "$COMP/${p}_fq_pie.dat"; done ;;
        drop_next) for p in dropnext; do [[ -f "$COMP/$src" && ! -e "$COMP/${p}_fq_pie.dat" ]] && ln -sf "$src" "$COMP/${p}_fq_pie.dat"; done ;;
        netperf_receiver) [[ -f "$COMP/$src" && ! -e "$COMP/throughput_fq_pie.dat" ]] && ln -sf "$src" "$COMP/throughput_fq_pie.dat" ;;
    esac
done
# suffix copies for all fq_pie_*.dat -> *_fq_pie.dat (generic fallback for bulk_plot)
for f in "$COMP"/fq_pie_*.dat; do
    [[ -e "$f" ]] || continue
    b=$(basename "$f" .dat | sed 's/fq_pie_//')
    suf="$COMP/${b}_fq_pie.dat"
    [[ -e "$suf" ]] || ln -sf "$(basename "$f")" "$suf"
done

echo "Done. Results in $REPO_ROOT/fq_pie_dat_files and averaged in $REPO_ROOT/comparison (symlinks for bulk_plot added)"
