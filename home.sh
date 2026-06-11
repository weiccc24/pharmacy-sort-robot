#!/bin/bash
# Reset follower arm to home position between trials
source ~/techin517/ros2_ws/install/setup.bash

ros2 topic pub --once /follower/arm_fwd_controller/commands \
    std_msgs/msg/Float64MultiArray \
    "{data: [-0.0782, -1.8715, 1.5432, -1.7334, -1.6644]}"

ros2 topic pub --once /follower/gripper_fwd_controller/commands \
    std_msgs/msg/Float64MultiArray \
    "{data: [0.0]}"

echo "Arm homed."
