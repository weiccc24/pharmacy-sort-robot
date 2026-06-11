#!/bin/bash
# Run one evaluation trial with a live timer.
# Press ENTER as soon as the task completes to record the time.
# The action cancels immediately — no need to wait out the 30s timeout.
#
# Usage:  ~/techin517/run_trial.sh <trial_number> <state_label>
# States: baseline | ambient_variance | geometry_shift

TRIAL=$1
STATE=$2
CSV=~/techin517/final_project/results/trials_raw.csv

if [[ -z "$TRIAL" || -z "$STATE" ]]; then
    echo "Usage: $0 <trial_number> <state_label>"
    echo "  state_label: baseline | ambient_variance | geometry_shift"
    exit 1
fi

if [[ "$STATE" != "baseline" && "$STATE" != "ambient_variance" && "$STATE" != "geometry_shift" ]]; then
    echo "Invalid state: $STATE"
    echo "Must be: baseline | ambient_variance | geometry_shift"
    exit 1
fi

source ~/techin517/ros2_ws/install/setup.bash

# Create CSV with header if it doesn't exist yet
if [[ ! -f "$CSV" ]]; then
    echo "trial_number,state_label,success,completion_time_s,failure_mode,notes" > "$CSV"
    echo "Created $CSV"
fi

echo ""
echo "==========================================="
echo " Trial $TRIAL  |  State: $STATE"
echo "==========================================="
echo " Checklist:"
echo "   [ ] Pill bottle on tape mark"
echo "   [ ] Arm at home position  (run ~/techin517/home.sh if needed)"
echo "   [ ] Bringup + rosetta client running"
echo ""
read -p " Press ENTER to start the trial... "

# Start action in background so we can show a live timer
ros2 action send_goal /run_policy \
    rosetta_interfaces/action/RunPolicy \
    "{prompt: 'pick up orange pill bottle and place in box'}" &
ACTION_PID=$!

START_MS=$(date +%s%3N)

echo ""
echo " >>> TRIAL RUNNING <<<"
echo " Press ENTER the moment the bottle lands in the bin = SUCCESS."
echo " If the arm fails, wait for the 30s timeout = FAIL."
echo ""

# Show live timer; exit loop on ENTER (success) or action timeout (fail)
USER_STOPPED=false
while kill -0 $ACTION_PID 2>/dev/null; do
    NOW_MS=$(date +%s%3N)
    ELAPSED_MS=$((NOW_MS - START_MS))
    ELAPSED_S=$(awk "BEGIN {printf \"%.1f\", $ELAPSED_MS / 1000}")
    printf "\r  Elapsed: ${ELAPSED_S}s   (press ENTER = success)  "
    if read -t 0.2 -r; then
        USER_STOPPED=true
        break
    fi
done

END_MS=$(date +%s%3N)
kill $ACTION_PID 2>/dev/null
wait $ACTION_PID 2>/dev/null

ELAPSED_MS=$((END_MS - START_MS))
ELAPSED_S=$(awk "BEGIN {printf \"%.1f\", $ELAPSED_MS / 1000}")

echo ""
echo "--- Stopped at ${ELAPSED_S}s ---"
echo ""

if [[ "$USER_STOPPED" == "true" ]]; then
    SUCCESS=1
    FAILURE_MODE=""
    echo ">>> SUCCESS <<<"
else
    SUCCESS=0
    ELAPSED_S=""
    echo ">>> FAIL (timeout) <<<"
    echo "Failure modes: missed_grasp | dropped | timeout | wrong_position | other"
    read -p "Failure mode (default: timeout): " FAILURE_MODE
    FAILURE_MODE=${FAILURE_MODE:-timeout}
fi

read -p "Notes (ENTER to skip): " NOTES

echo "${TRIAL},${STATE},${SUCCESS},${ELAPSED_S},${FAILURE_MODE},${NOTES}" >> "$CSV"
echo ""
echo "Logged: trial=$TRIAL  state=$STATE  success=$SUCCESS  time=${ELAPSED_S}s"

# Wait for cancel to propagate, then command arm to home to stop any residual motion
sleep 2
~/techin517/home.sh

echo "Next: reset bottle → run next trial"
