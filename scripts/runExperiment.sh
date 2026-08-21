#!/bin/bash
KEYS=("cwnd" "rtt" "dev_rtt" "ssthresh" "rto" "delivery_rate" "pacing_rate")
KEYS1=("bytes" "packets" "drops" "overlimits" "requeues" "backlog" "qlen" "count" "lastcount" "ldelay" "drop_next" "maxpacket" "drop_overlimit")
COOLDOWN_SEC=3
# Run the experiment 5 times
for i in {1..25}
do
    echo "Running experiment iteration $i..."
    
    #sudo ~/venv/bin/python3 fq_codel-point-to-point.py
    cd /home/deepa/nest/
    #sudo bash -c "ulimit -n 65535 && echo -n 'Active Open File Limit: ' && ulimit -n"
    #sudo env "PATH=$PATH" ./run-scenarios.sh dumbbell.py
    sudo bash -c "ulimit -n 65535 && env "PATH=$PATH" ./run-scenarios.sh dumbbell.py"
    #sudo bash -c "ulimit -n 65535 && env "PATH=$PATH" ./runPulseWave.sh pulseWave.py"
    # Explicitly clean up any orphan NeST namespaces/processes between runs
    sudo ip -all netns delete 2>/dev/null || true
    sudo pkill -f netperf 2>/dev/null || true
    sudo pkill -f iperf3 2>/dev/null || true
    OUTPUT_FOLDER="fq_codelpp_dat_files"
    mkdir -p "$OUTPUT_FOLDER"
    chmod 777 "$OUTPUT_FOLDER"
    cd /home/deepa/nest/fq_codelpp_dat_files
    mkdir -p netperf_sender ping netperf_receiver

    sudo chmod 777 /home/deepa/nest/results
    cd /home/deepa/nest/results/synchronous/fq_codel
    #cd /home/deepa/nest/results/staggered/fq_codel
    #cd /home/deepa/nest/results/rtt-fairness/fq_codel
    #cd /home/deepa/nest/results/pulsewave/fq_codel
    #cd /home/deepa/nest/results/udp-background/fq_codel

    OUTPUT_DIR=$(ls -dt synchronous_*dump | head -n 1)
    #OUTPUT_DIR=$(ls -dt staggered_*dump | head -n 1)
    #OUTPUT_DIR=$(ls -dt rtt-fairness_*dump | head -n 1)
    #OUTPUT_DIR=$(ls -dt pulsewave_*dump | head -n 1)
    #OUTPUT_DIR=$(ls -dt udp-background_*dump | head -n 1)
    #OUTPUT_DIR=$(ls -dt fq_codelpp_$i | head -n 1)


    if [[ -d $OUTPUT_DIR ]]; then
        #RENAMED_DIR="fq_codelpp_$i"
        RENAMED_DIR="/home/deepa/nest/results/synchronous/fq_codel/fq_codelpp_$i"
        #RENAMED_DIR="/home/deepa/nest/results/staggered/fq_codel/fq_codelpp_$i"
        #RENAMED_DIR="/home/deepa/nest/results/rtt-fairness/fq_codel/fq_codelpp_$i"
        #RENAMED_DIR="/home/deepa/nest/results/pulsewave/fq_codel/fq_codelpp_$i"
        #RENAMED_DIR="/home/deepa/nest/results/udp-background/fq_codel/fq_codelpp_$i"

        #rm -rf $RENAMED_DIR
        sudo mv "$OUTPUT_DIR" "$RENAMED_DIR"
        echo "Renamed directory $OUTPUT_DIR to $RENAMED_DIR"
        cd /home/deepa/nest
        # Process sending_rate from iperf3.json
        JSON_INPUT="${RENAMED_DIR}/iperf3.json"
        #JSON_INPUT="${RENAMED_DIR}/netperf.json"
        DAT_OUTPUT="${OUTPUT_FOLDER}/netperf_sender/netperf${i}.dat"
        [[ -f $JSON_INPUT ]] && ./netperf_ping.py -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k sending_rate

        # Process receiving_rate from iperfServer.json
        JSON_INPUT="${RENAMED_DIR}/iperf3Server.json"
        DAT_OUTPUT="${OUTPUT_FOLDER}/netperf_receiver/iperf3Server${i}.dat"
        [[ -f $JSON_INPUT ]] && ./netperf_ping.py -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k receiving_rate

        # Process rtt from ping.json
        JSON_INPUT="${RENAMED_DIR}/ping.json"
        DAT_OUTPUT="${OUTPUT_FOLDER}/ping/ping${i}.dat"
        [[ -f $JSON_INPUT ]] && ./netperf_ping.py -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k rtt

        for KEY in "${KEYS[@]}"; do
            JSON_INPUT="${RENAMED_DIR}/ss.json"
            DAT_OUTPUT="${OUTPUT_FOLDER}/ss_${KEY}${i}.dat"
            [[ -f $JSON_INPUT ]] && ./SS_TC.py -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k "$KEY"
        done

        for KEY1 in "${KEYS1[@]}"; do
            JSON_INPUT="${RENAMED_DIR}/tc.json"
            DAT_OUTPUT="${OUTPUT_FOLDER}/tc_${KEY1}${i}.dat"
            [[ -f $JSON_INPUT ]] && ./SS_TC.py -i "$JSON_INPUT" -o "$DAT_OUTPUT" -k "$KEY1"
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

cd /home/deepa/nest/fq_codelpp_dat_files
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
        echo "Moved *tc_${KEY}*.dat files to $KEY/"
    else
        echo "No files found for key: $KEY"
    fi
done

echo "Files have been organized into folders by keys."
echo "All iterations completed."

# Ensure the working directory is correct
cd /home/deepa/nest

# Create the comparison directory if it doesn't exist
mkdir -p comparison

# Define the folder path containing the nested dat files
FOLDER_PATH="/home/deepa/nest/fq_codelpp_dat_files"

# Find all subdirectories in FOLDER_PATH and process them
find "$FOLDER_PATH" -type d | while read -r SUBDIR; do
    # Extract the base name of the subdirectory (e.g., cwnd)
    BASENAME=$(basename "$SUBDIR")

    # Construct the output file name
    OUTPUT_FILE="./comparison/fq_codelpp_${BASENAME}.dat"

    rm $OUTPUT_FILE
    # Run the averagedat.py script with the directory and output file
    ./averagedat.py -i "$SUBDIR" -o "$OUTPUT_FILE"
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
