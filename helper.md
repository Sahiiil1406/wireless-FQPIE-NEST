1.
Fix runExperiment_sahil.sh

Add this variable near the top, after SCRIPTS_DIR:

NEST_PYTHON="$REPO_ROOT/nest/.venv/bin/python"

So the beginning becomes:

REPO_ROOT="/home/sahil/Desktop/wireless-FQPIE-NEST"
SCRIPTS_DIR="$REPO_ROOT/scripts"
NEST_PYTHON="$REPO_ROOT/nest/.venv/bin/python"

Then replace this:

sudo bash -c "ulimit -n 65535 && env \"PATH=\$PATH\" $SCRIPTS_DIR/run-scenarios.sh $SCRIPTS_DIR/dumbbell.py"

with:

sudo bash -c "ulimit -n 65535 && env PATH=\"$REPO_ROOT/nest/.venv/bin:\$PATH\" $SCRIPTS_DIR/run-scenarios.sh $SCRIPTS_DIR/dumbbell.py"

2.