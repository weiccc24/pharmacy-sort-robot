#!/bin/bash
# One-time setup before starting evaluation trials.
# Run this once per session (or whenever you move the bin).

source ~/techin517/ros2_ws/install/setup.bash

echo ""
echo "=== Trial Setup ==="
echo ""
echo "Step 1: Place the pill bottle INSIDE the bin."
echo "        The overhead camera must be running (bringup must be up)."
echo ""
read -p "Press ENTER to open the bin ROI calibration window..."

python3 ~/techin517/final_project/check_success.py --calibrate

echo ""
echo "Step 2: Test the success check (place bottle in bin first)."
read -p "Press ENTER to run a test check..."
python3 ~/techin517/final_project/check_success.py --debug

echo ""
echo "Setup complete. Start trials with:"
echo "  ~/techin517/run_trial.sh 1 baseline"
