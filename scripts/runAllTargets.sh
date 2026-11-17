#!/bin/bash
# runAllTargets.sh - Run runExperiment.sh once per FQ-PIE target, archive avgs to finals/
#
# For each target in 1 2 5 10 15 30 50 (ms):
#   1. Calls scripts/runExperiment.sh with QDISC_PARAMS='{"target":"<t>ms"}'
#      (runExperiment.sh itself does 25 iterations of dumbbell.py, 100 TCP flows)
#   2. Moves whatever avg was generated (nest/comparison/fq_pie_*.dat)
#      into finals/target_<t>ms/
#   3. Cleans intermediates so the next target starts fresh.
#
# Usage:
#   sudo bash scripts/runAllTargets.sh
#   # custom list: TARGETS="1 5 15" sudo -E bash scripts/runAllTargets.sh
#   # keep raw dumps too: KEEP_RAW=1 sudo -E bash scripts/runAllTargets.sh
#   # resume after interrupt (default: auto-skips done targets + done iterations):
#   #   TARGETS="50" sudo -E bash scripts/runAllTargets.sh
#   # manual iteration range (eg 20 done -> run 21..25 only):
#   #   START_ITER=21 END_ITER=25 TARGETS="50" sudo -E bash scripts/runAllTargets.sh
#   # force full re-run from scratch:
#   #   RESUME=0 TARGETS="50" sudo -E bash scripts/runAllTargets.sh
#   # skip specific targets:
#   #   SKIP_TARGETS="30 50" sudo -E bash scripts/runAllTargets.sh
#
# Note: each target = full 25x run (~100s each), so 7 targets take many hours.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NEST_DIR="$PROJECT_ROOT/nest"
FINALS_DIR="$PROJECT_ROOT/finals"

# Space-separated target list (ms). Override via env: TARGETS="1 5 15"
TARGETS="${TARGETS:-50}"
# Set KEEP_RAW=1 to also archive nest/results + fq_pie_dat_files per target (uses lots of disk)
KEEP_RAW="${KEEP_RAW:-0}"
# Resume support:
#   RESUME=1 (default) -> skip targets already in finals/, and keep
#     nest/fq_pie_dat_files + nest/results so runExperiment.sh can resume
#     iterations (eg 19/25 done -> continues at 20, not from scratch).
#   RESUME=0 -> old behaviour: wipe intermediates and redo everything.
#   START_ITER/END_ITER are passed through to runExperiment.sh for manual
#     control, eg START_ITER=21 TARGETS="50" sudo -E bash scripts/runAllTargets.sh
#   SKIP_TARGETS="30 50" skips those targets entirely.
RESUME="${RESUME:-1}"
START_ITER="${START_ITER:-1}"
END_ITER="${END_ITER:-25}"
SKIP_TARGETS="${SKIP_TARGETS:-}"
export RESUME START_ITER END_ITER

mkdir -p "$FINALS_DIR"
chmod 777 "$FINALS_DIR" 2>/dev/null || true

echo "Targets (ms): $TARGETS"
echo "Finals dir: $FINALS_DIR"
echo "KEEP_RAW=$KEEP_RAW RESUME=$RESUME START_ITER=$START_ITER END_ITER=$END_ITER SKIP_TARGETS=[$SKIP_TARGETS]"
echo "-----------------------------------"

for T in $TARGETS; do
    echo "=================================================="
    echo " Target ${T}ms"
    echo "=================================================="
    # Skip list check
    if [[ " $SKIP_TARGETS " == *" $T "* ]]; then
        echo "Skipping target ${T}ms (in SKIP_TARGETS)."
        continue
    fi
    # Target-level resume: already archived in finals/ -> skip
    DEST="$FINALS_DIR/target_${T}ms"
    if [[ "$RESUME" == "1" && -d "$DEST" ]] && ls "$DEST"/fq_pie_*_target_"${T}"ms.dat 1>/dev/null 2>&1; then
        echo "Target ${T}ms already complete in $DEST/, skipping (RESUME=1). Use RESUME=0 to force re-run."
        continue
    fi
    if [[ "$RESUME" == "1" ]] && ls "$FINALS_DIR"/fq_pie_*_target_"${T}"ms.dat 1>/dev/null 2>&1; then
        echo "Target ${T}ms already complete in $FINALS_DIR/ (flat), skipping (RESUME=1)."
        # ensure subfolder exists for consistency
        mkdir -p "$DEST"
        continue
    fi
    export QDISC_PARAMS="{\"target\":\"${T}ms\"}"
    echo "QDISC_PARAMS=$QDISC_PARAMS"

    # Fresh intermediates for this target (needs sudo: previous files are root-owned)
    # With RESUME=1 we KEEP existing fq_pie_dat_files/results so iterations continue
    # (eg 19 done -> runExperiment.sh skips 1..19 and runs 20..25).
    if [[ "$RESUME" == "0" ]]; then
        echo "RESUME=0: wiping intermediates for fresh run."
        sudo rm -rf "$NEST_DIR/fq_pie_dat_files" "$NEST_DIR/comparison" 2>/dev/null || true
        sudo rm -rf "$NEST_DIR/results/synchronous" 2>/dev/null || true
    else
        # Resume mode: only clean comparison avg (regenerated at end), keep raw progress
        if ls "$NEST_DIR/fq_pie_dat_files"/netperf_sender/netperf*.dat 1>/dev/null 2>&1; then
            echo "RESUME=1: keeping existing $(ls "$NEST_DIR/fq_pie_dat_files"/netperf_sender/netperf*.dat 2>/dev/null | wc -l) completed iteration(s), continuing..."
        else
            echo "RESUME=1: no prior progress found, starting fresh for target ${T}ms."
            sudo rm -rf "$NEST_DIR/fq_pie_dat_files" "$NEST_DIR/comparison" 2>/dev/null || true
            # do NOT wipe results/synchronous blindly if other targets' results are there;
            # runExperiment.sh handles per-iteration dirs, so keep them
        fi
        sudo rm -rf "$NEST_DIR/comparison" 2>/dev/null || true
    fi

    # Run the full experiment once (25 iterations internally, resumes automatically)
    sudo env "PATH=$PATH" "QDISC_PARAMS=$QDISC_PARAMS" "RESUME=$RESUME" "START_ITER=$START_ITER" "END_ITER=$END_ITER" bash "$SCRIPT_DIR/runExperiment.sh"
    echo "runExperiment.sh finished for target ${T}ms (exit=$?)"

    # Archive whatever avg was generated, with target suffix for easy distinction:
    #   finals/target_<T>ms/fq_pie_<metric>_target_<T>ms.dat
    #   finals/fq_pie_<metric>_target_<T>ms.dat  (flat copy)
    DEST="$FINALS_DIR/target_${T}ms"
    mkdir -p "$DEST"
    if ls "$NEST_DIR/comparison"/fq_pie_*.dat 1>/dev/null 2>&1; then
        for SRC in "$NEST_DIR"/comparison/fq_pie_*.dat; do
            BASE="$(basename "$SRC" .dat)"
            NEW="${BASE}_target_${T}ms.dat"
            sudo cp "$SRC" "$DEST/$NEW"
            sudo cp "$SRC" "$FINALS_DIR/$NEW"
        done
        sudo rm -f "$NEST_DIR"/comparison/fq_pie_*.dat
        sudo chmod 777 "$DEST" "$FINALS_DIR" 2>/dev/null || true
        sudo chmod 777 "$DEST"/* "$FINALS_DIR"/*_target_*.dat 2>/dev/null || true
        echo "Saved avg .dat with suffix _target_${T}ms -> $DEST/ + $FINALS_DIR/:"
        ls "$DEST"
    else
        echo "WARNING: no avg files in $NEST_DIR/comparison for target ${T}ms"
    fi

    # Optionally archive raw data too, else clean for next target
    if [[ "$KEEP_RAW" == "1" ]]; then
        [[ -d "$NEST_DIR/fq_pie_dat_files" ]] && sudo mv "$NEST_DIR/fq_pie_dat_files" "$DEST/fq_pie_dat_files" 2>/dev/null || true
        [[ -d "$NEST_DIR/results" ]] && sudo mkdir -p "$DEST/results" && sudo mv "$NEST_DIR"/results/synchronous "$DEST/results/" 2>/dev/null || true
        sudo chmod -R 777 "$DEST" 2>/dev/null || true
        echo "Kept raw data under $DEST/"
    else
        sudo rm -rf "$NEST_DIR/fq_pie_dat_files" "$NEST_DIR/comparison" 2>/dev/null || true
        sudo rm -rf "$NEST_DIR/results/synchronous" 2>/dev/null || true
    fi

    # Cleanup orphans between targets
    sudo ip -all netns delete 2>/dev/null || true
    sudo pkill -f netperf 2>/dev/null || true
    sudo pkill -f iperf3 2>/dev/null || true

    echo "Target ${T}ms done -> $DEST/"
    echo "-----------------------------------"
done

echo "All targets complete. Finals:"
ls -R "$FINALS_DIR"
