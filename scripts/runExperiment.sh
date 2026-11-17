#!/bin/bash
KEYS=("cwnd" "rtt" "dev_rtt" "ssthresh" "rto" "delivery_rate" "pacing_rate")
KEYS1=("bytes" "packets" "drops" "overlimits" "requeues" "backlog" "qlen" "count" "lastcount" "ldelay" "drop_next" "maxpacket" "drop_overlimit")
COOLDOWN_SEC=3
# Auto-detect NEST_DIR from script location (portable, replaces hardcoded /home/deepa/nest)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NEST_DIR="$PROJECT_ROOT/nest"
# NeST venv python (fixes ModuleNotFoundError under sudo)
NEST_PYTHON="$NEST_DIR/.venv/bin/python"
if [[ ! -x "$NEST_PYTHON" ]]; then NEST_PYTHON="python3"; fi
# Use venv python via PYTHON_BIN for run-scenarios.sh
export NEST_PYTHON
export PYTHON_BIN="$NEST_PYTHON"
# Allow target override from env, e.g. QDISC_PARAMS='{"target":"5ms"}' sudo -E bash runExperiment.sh
QDISC_PARAMS="${QDISC_PARAMS:-}"
export QDISC_PARAMS

# Resume support (eg 20 done -> restart from 21 without losing progress):
#   RESUME=1 (default) skips iterations already completed (fq_pie_$i + dats exist).
#   START_ITER/END_ITER override the loop range, e.g. START_ITER=21 sudo -E bash runExperiment.sh
#   RESUME=0 forces a full re-run from scratch (old behaviour).
#   Examples:
#     sudo -E bash scripts/runExperiment.sh                      # auto-resume 1..25
#     START_ITER=21 sudo -E bash scripts/runExperiment.sh        # manual: run 21..25 only
#     RESUME=0 sudo -E bash scripts/runExperiment.sh             # wipe + redo all 25
START_ITER="${START_ITER:-1}"
END_ITER="${END_ITER:-25}"
RESUME="${RESUME:-1}"
export START_ITER END_ITER RESUME

# Run the experiment 25 times (fq_pie with defaults)
for i in $(seq "$START_ITER" "$END_ITER")
do
    echo "Running experiment iteration $i... (RESUME=$RESUME)"

    # --- Resume check: skip if this iteration already has results + dats ---
    if [[ "$RESUME" == "1" ]]; then
        EXISTING=""
        [[ -d "$PROJECT_ROOT/results/synchronous/fq_pie/fq_pie_$i" ]] && EXISTING="$PROJECT_ROOT/results/synchronous/fq_pie/fq_pie_$i"
        [[ -z "$EXISTING" && -d "$NEST_DIR/results/synchronous/fq_pie/fq_pie_$i" ]] && EXISTING="$NEST_DIR/results/synchronous/fq_pie/fq_pie_$i"
        if [[ -n "$EXISTING" && -f "$NEST_DIR/fq_pie_dat_files/netperf_sender/netperf${i}.dat" && -f "$NEST_DIR/fq_pie_dat_files/netperf_receiver/iperf3Server${i}.dat" ]]; then
            echo "Iteration $i already done ($EXISTING + dats exist), skipping (RESUME=1). Use RESUME=0 to force re-run."
            continue
        fi
        # Reuse existing renamed dir without re-running NeST if dats are missing
        # (falls through to extraction below via REUSE_DIR)
        REUSE_DIR="$EXISTING"
    else
        REUSE_DIR=""
    fi

    OUTPUT_FOLDER="fq_pie_dat_files"
    mkdir -p "$NEST_DIR/$OUTPUT_FOLDER" 2>/dev/null || true
    chmod 777 "$NEST_DIR/$OUTPUT_FOLDER" 2>/dev/null || true

    # If resuming and renamed dir already exists but dats are missing -> re-extract only, no re-run
    if [[ "$RESUME" == "1" && -n "${REUSE_DIR:-}" && -d "$REUSE_DIR" ]]; then
        if [[ ! -f "$NEST_DIR/$OUTPUT_FOLDER/netperf_sender/netperf${i}.dat" ]]; then
            echo "Reusing existing $REUSE_DIR without re-running NeST (re-extracting dats)..."
            RENAMED_DIR="$REUSE_DIR"
            cd "$NEST_DIR"
            OUTPUT_FOLDER="fq_pie_dat_files"
            mkdir -p "$OUTPUT_FOLDER"
            chmod 777 "$OUTPUT_FOLDER"
            cd "$NEST_DIR/fq_pie_dat_files"
            mkdir -p netperf_sender ping netperf_receiver
            # Process sending_rate from iperf3.json
            JSON_INPUT="${RENAMED_DIR}/iperf3.json"
            DAT_OUTPUT="${OUTPUT_FOLDER}/netperf_sender/netperf${i}.dat"
            [[ -f $JSON_INPUT ]] && "$NEST_PYTHON" "$SCRIPT_DIR/netperf_ping.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k sending_rate

            # Process receiving_rate from iperfServer.json
            JSON_INPUT="${RENAMED_DIR}/iperf3Server.json"
            DAT_OUTPUT="${OUTPUT_FOLDER}/netperf_receiver/iperf3Server${i}.dat"
            [[ -f $JSON_INPUT ]] && "$NEST_PYTHON" "$SCRIPT_DIR/netperf_ping.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k receiving_rate

            # Process rtt from ping.json
            JSON_INPUT="${RENAMED_DIR}/ping.json"
            DAT_OUTPUT="${OUTPUT_FOLDER}/ping/ping${i}.dat"
            [[ -f $JSON_INPUT ]] && "$NEST_PYTHON" "$SCRIPT_DIR/netperf_ping.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k rtt

            for KEY in "${KEYS[@]}"; do
                JSON_INPUT="${RENAMED_DIR}/ss.json"
                DAT_OUTPUT="${OUTPUT_FOLDER}/ss_${KEY}${i}.dat"
                [[ -f $JSON_INPUT ]] && "$NEST_PYTHON" "$SCRIPT_DIR/SS_TC.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k "$KEY"
            done

            for KEY1 in "${KEYS1[@]}"; do
                JSON_INPUT="${RENAMED_DIR}/tc.json"
                DAT_OUTPUT="${OUTPUT_FOLDER}/tc_${KEY1}${i}.dat"
                [[ -f $JSON_INPUT ]] && "$NEST_PYTHON" "$SCRIPT_DIR/SS_TC.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k "$KEY1"
            done
            echo "Iteration $i re-extracted from $REUSE_DIR."
            echo "-----------------------------------"
            echo "Cooling down for ${COOLDOWN_SEC}s..."
            sleep "$COOLDOWN_SEC"
            continue
        fi
    fi

    cd "$NEST_DIR"
    # NOTE: QDISC_PARAMS (JSON with double quotes) is passed via outer sudo env only.
    # It is inherited inside bash -c; repeating it quoted inside would break JSON parsing.
    sudo env "PATH=$PATH" "NEST_PYTHON=$NEST_PYTHON" "PYTHON_BIN=$NEST_PYTHON" "QDISC_PARAMS=$QDISC_PARAMS" bash -c 'ulimit -n 65535 && exec env "PATH=$PATH" "NEST_PYTHON=$NEST_PYTHON" "PYTHON_BIN=$PYTHON_BIN" ./../scripts/run-scenarios.sh ./../scripts/dumbbell.py'
    # Explicitly clean up any orphan NeST namespaces/processes between runs
    sudo ip -all netns delete 2>/dev/null || true
    sudo pkill -f netperf 2>/dev/null || true
    sudo pkill -f iperf3 2>/dev/null || true
    OUTPUT_FOLDER="fq_pie_dat_files"
    mkdir -p "$OUTPUT_FOLDER"
    chmod 777 "$OUTPUT_FOLDER"
    cd "$NEST_DIR/fq_pie_dat_files"
    mkdir -p netperf_sender ping netperf_receiver

    sudo chmod 777 "$NEST_DIR/results" 2>/dev/null || true
    sudo chmod 777 "$PROJECT_ROOT/results" 2>/dev/null || true
    # Handle both nest/results and project/results (symlinked)
    if [[ -d "$PROJECT_ROOT/results/synchronous/fq_pie" ]]; then
        cd "$PROJECT_ROOT/results/synchronous/fq_pie"
    else
        cd "$NEST_DIR/results/synchronous/fq_pie"
    fi

    OUTPUT_DIR=$(ls -dt synchronous_*dump 2>/dev/null | head -n 1)

    if [[ -d $OUTPUT_DIR ]]; then
        if [[ -d "$PROJECT_ROOT/results/synchronous/fq_pie" ]]; then
            RENAMED_DIR="$PROJECT_ROOT/results/synchronous/fq_pie/fq_pie_$i"
        else
            RENAMED_DIR="$NEST_DIR/results/synchronous/fq_pie/fq_pie_$i"
        fi

        sudo rm -rf "$RENAMED_DIR" 2>/dev/null || true
        sudo mv "$OUTPUT_DIR" "$RENAMED_DIR"
        echo "Renamed directory $OUTPUT_DIR to $RENAMED_DIR"
        cd "$NEST_DIR"
        # Process sending_rate from iperf3.json
        JSON_INPUT="${RENAMED_DIR}/iperf3.json"
        DAT_OUTPUT="${OUTPUT_FOLDER}/netperf_sender/netperf${i}.dat"
        [[ -f $JSON_INPUT ]] && "$NEST_PYTHON" "$SCRIPT_DIR/netperf_ping.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k sending_rate

        # Process receiving_rate from iperfServer.json
        JSON_INPUT="${RENAMED_DIR}/iperf3Server.json"
        DAT_OUTPUT="${OUTPUT_FOLDER}/netperf_receiver/iperf3Server${i}.dat"
        [[ -f $JSON_INPUT ]] && "$NEST_PYTHON" "$SCRIPT_DIR/netperf_ping.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k receiving_rate

        # Process rtt from ping.json
        JSON_INPUT="${RENAMED_DIR}/ping.json"
        DAT_OUTPUT="${OUTPUT_FOLDER}/ping/ping${i}.dat"
        [[ -f $JSON_INPUT ]] && "$NEST_PYTHON" "$SCRIPT_DIR/netperf_ping.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k rtt

        for KEY in "${KEYS[@]}"; do
            JSON_INPUT="${RENAMED_DIR}/ss.json"
            DAT_OUTPUT="${OUTPUT_FOLDER}/ss_${KEY}${i}.dat"
            [[ -f $JSON_INPUT ]] && "$NEST_PYTHON" "$SCRIPT_DIR/SS_TC.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k "$KEY"
        done

        for KEY1 in "${KEYS1[@]}"; do
            JSON_INPUT="${RENAMED_DIR}/tc.json"
            DAT_OUTPUT="${OUTPUT_FOLDER}/tc_${KEY1}${i}.dat"
            [[ -f $JSON_INPUT ]] && "$NEST_PYTHON" "$SCRIPT_DIR/SS_TC.py" -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k "$KEY1"
        done
    else
        echo "Output directory not found!"
    fi
    echo "Iteration $i completed."
    echo "-----------------------------------"
    # Cooldown before starting the next iteration
    echo "Cooling down for ${COOLDOWN_SEC}s..."
    sleep "$COOLDOWN_SEC"
done

cd "$NEST_DIR/fq_pie_dat_files"
# Create folders for KEYS (SS files)
for KEY in "${KEYS[@]}"; do
    mkdir -p "$KEY"  # Create folder if it doesn't exist
done

# Create folders for KEYS1 (TC files)
for KEY in "${KEYS1[@]}"; do
    mkdir -p "$KEY"  # Create folder if it doesn't exist
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
        echo "Moved *tc_${KEY1}*.dat files to $KEY/"
    else
        echo "No files found for key: $KEY"
    fi
done

echo "Files have been organized into folders by keys."
echo "All iterations completed."

# Ensure the working directory is correct
cd "$NEST_DIR"

# Create the comparison directory if it doesn't exist
mkdir -p comparison

# Define the folder path containing the nested dat files
FOLDER_PATH="$NEST_DIR/fq_pie_dat_files"

# Find all subdirectories in FOLDER_PATH and process them
find "$FOLDER_PATH" -type d | while read -r SUBDIR; do
    # Extract the base name of the subdirectory (e.g., cwnd)
    BASENAME=$(basename "$SUBDIR")

    # Construct the output file name
    OUTPUT_FILE="./comparison/fq_pie_${BASENAME}.dat"

    rm -f "$OUTPUT_FILE"
    # Run the averagedat.py script with the directory and output file
    "$NEST_PYTHON" "$SCRIPT_DIR/averagedat.py" -i "$SUBDIR" -o "$OUTPUT_FILE"
    # If processing 'ldelay' or 'qdelay', convert column 2 from microseconds (us) to milliseconds (ms)
    if [[ "$BASENAME" == *"ldelay"* || "$BASENAME" == *"qdelay"* ]]; then
        if [ -f "$OUTPUT_FILE" ]; then
            # Divide 2nd column by 1000 while preserving 1st column (time)
            awk '{if (NF >= 2) print $1, $2/1000; else print $0}' "$OUTPUT_FILE" > "${OUTPUT_FILE}.tmp" \
                && mv "${OUTPUT_FILE}.tmp" "$OUTPUT_FILE"
            echo "[Converted] $OUTPUT_FILE values converted from us to ms."
        fi
    fi
    echo "Processed directory $SUBDIR and saved results to $OUTPUT_FILE"
done
