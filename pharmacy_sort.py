#!/usr/bin/env python3
"""
pharmacy_sort.py
TECHIN 517 Final Project — Pharmacy Logistics Sorting Assistant

Detects medication objects with YOLO-World and sorts them into designated
rack slots using the MoveIt2 pick-and-place pipeline from Lab 4.

Object → Slot mapping:
    pill_bottle   (orange Costco cylinder) → Slot A
    medicine_tube (small white/red tube)   → Slot B
    medicine_box  (Liposic eye gel box)    → Slot C

Coordinate system: robot base_link frame (meters).
Fill in SLOT_POSES and PICK_Z after recording them in the lab.

Prerequisites:
    ros2 launch soa_moveit_config soa_moveit_bringup.launch.py
    ros2 run soa_functions move_to_pose_server
    ros2 run soa_functions gripper_server
    ros2 launch yolo_bringup yolo-world.launch.py  # for YOLO-World detection

Run (YOLO mode — detects and sorts automatically):
    ros2 run soa_apps pharmacy_sort --ros-args -p mode:=yolo

Run (manual test — sort one object at a known position):
    ros2 run soa_apps pharmacy_sort \
        --ros-args -p mode:=manual \
                   -p target_class:=pill_bottle \
                   -p target_x:=0.25 -p target_y:=0.05 -p target_z:=0.03
"""

import csv
import os
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from geometry_msgs.msg import Pose
from soa_interfaces.action import Gripper, MoveToPose

# ---------------------------------------------------------------------------
# Workspace configuration — fill these in after recording poses in the lab
# ---------------------------------------------------------------------------

# Z-height of the table surface where objects sit (meters above base_link).
# Measure this with save_pose.py while the gripper fingertips touch the table.
TABLE_Z = 0.03

# How far above TABLE_Z to approach before descending to pick
APPROACH_OFFSET = 0.12

# How far to lift the object after grasping
LIFT_OFFSET = 0.15

# Home pose — arm rests here while waiting and between picks.
# Orientation (qx, qy, qz, qw) = gripper pointing straight down.
HOME = dict(x=0.18, y=0.0, z=0.28, qx=0.0, qy=0.707, qz=0.0, qw=0.707)

# Destination rack slots — (x, y, z) in base_link frame.
# Record each slot's position with save_pose.py during your lab visit.
# z should be just above the slot opening so the object drops in cleanly.
SLOT_POSES = {
    "pill_bottle":   dict(x=0.30, y=-0.12, z=TABLE_Z + 0.02),  # Slot A — LEFT
    "medicine_tube": dict(x=0.30, y= 0.00, z=TABLE_Z + 0.02),  # Slot B — CENTER
    "medicine_box":  dict(x=0.30, y= 0.12, z=TABLE_Z + 0.02),  # Slot C — RIGHT
}

# Gripper positions
GRIPPER_OPEN   = 1.7453   # fully open
GRIPPER_CLOSED = 0.45     # firm grip — adjust so it holds without crushing

# YOLO-World text classes — must match what the model receives.
# These map the text class names back to our internal keys.
YOLO_CLASS_MAP = {
    "pill bottle":    "pill_bottle",
    "medicine bottle": "pill_bottle",
    "medicine tube":  "medicine_tube",
    "cylindrical medicine": "medicine_tube",
    "medicine box":   "medicine_box",
    "eye gel":        "medicine_box",
    "eye gel box":    "medicine_box",
    "liposic":        "medicine_box",
}

# ---------------------------------------------------------------------------
# Trial logging — writes a CSV row for each trial (quantitative evaluation)
# ---------------------------------------------------------------------------

LOG_PATH = os.path.expanduser("~/techin517_trials.csv")
LOG_FIELDS = [
    "trial_num", "state_label", "object_class",
    "success", "completion_time_s", "failure_mode", "notes",
]


def _init_log():
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=LOG_FIELDS).writeheader()


def log_trial(trial_num: int, state_label: str, object_class: str,
              success: bool, elapsed: float, failure_mode: str = "", notes: str = ""):
    _init_log()
    with open(LOG_PATH, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=LOG_FIELDS).writerow({
            "trial_num":         trial_num,
            "state_label":       state_label,
            "object_class":      object_class,
            "success":           int(success),
            "completion_time_s": f"{elapsed:.2f}",
            "failure_mode":      failure_mode,
            "notes":             notes,
        })
    status = "SUCCESS" if success else f"FAIL ({failure_mode})"
    print(f"[Trial {trial_num}] {state_label} | {object_class} | {status} | {elapsed:.1f}s")


# ---------------------------------------------------------------------------
# Pose helper
# ---------------------------------------------------------------------------

def _pose(x, y, z, qx=0.0, qy=0.707, qz=0.0, qw=0.707) -> Pose:
    """Build a geometry_msgs/Pose pointing the gripper downward by default."""
    p = Pose()
    p.position.x = float(x)
    p.position.y = float(y)
    p.position.z = float(z)
    p.orientation.x = float(qx)
    p.orientation.y = float(qy)
    p.orientation.z = float(qz)
    p.orientation.w = float(qw)
    return p


# ---------------------------------------------------------------------------
# Main ROS2 node
# ---------------------------------------------------------------------------

class PharmacySort(Node):

    def __init__(self):
        super().__init__("pharmacy_sort")

        self.declare_parameter("mode",         "manual")   # "manual" | "yolo"
        self.declare_parameter("state_label",  "baseline") # for trial logging
        self.declare_parameter("trial_num",    1)
        self.declare_parameter("target_class", "pill_bottle")
        self.declare_parameter("target_x",     0.25)
        self.declare_parameter("target_y",     0.05)
        self.declare_parameter("target_z",     TABLE_Z)

        self._pose_client    = ActionClient(self, MoveToPose, "move_to_pose")
        self._gripper_client = ActionClient(self, Gripper,    "gripper_command")
        self._pick_done      = False

    # ------------------------------------------------------------------
    # Action client helpers (same MoveIt2 pattern as Lab 4)
    # ------------------------------------------------------------------

    def _exec_pose(self, pose: Pose) -> bool:
        goal = MoveToPose.Goal()
        goal.target_pose = pose
        self._pose_client.wait_for_server()
        f = self._pose_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, f)
        h = f.result()
        if not h.accepted:
            return False
        rf = h.get_result_async()
        rclpy.spin_until_future_complete(self, rf)
        return rf.result().result.success

    def _exec_gripper(self, pos: float) -> bool:
        goal = Gripper.Goal()
        goal.target_position = pos
        self._gripper_client.wait_for_server()
        f = self._gripper_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, f)
        h = f.result()
        if not h.accepted:
            return False
        rf = h.get_result_async()
        rclpy.spin_until_future_complete(self, rf)
        return rf.result().result.success

    # ------------------------------------------------------------------
    # Pick-and-sort sequence
    # ------------------------------------------------------------------

    def sort_object(self, object_class: str, pick_x: float, pick_y: float,
                    pick_z: float = TABLE_Z,
                    trial_num: int = 0, state_label: str = "baseline") -> bool:
        """
        Full pick-and-sort cycle for one object:
          home → above_pick → open → pick → grasp → lift → above_slot → release → home

        Returns True on success, False on any step failure.
        Logs a trial row to ~/techin517_trials.csv automatically.
        """
        if object_class not in SLOT_POSES:
            self.get_logger().error(
                f"Unknown object class '{object_class}'. "
                f"Valid: {list(SLOT_POSES.keys())}"
            )
            return False

        slot = SLOT_POSES[object_class]
        self.get_logger().info(
            f"Sorting '{object_class}': pick=({pick_x:.3f},{pick_y:.3f},{pick_z:.3f}) "
            f"→ slot=({slot['x']:.3f},{slot['y']:.3f},{slot['z']:.3f})"
        )

        start_time = time.time()
        failure_mode = ""

        steps = [
            # Step name          Action
            ("home",             lambda: self._exec_pose(_pose(**HOME))),
            ("above_pick",       lambda: self._exec_pose(_pose(pick_x, pick_y, pick_z + APPROACH_OFFSET))),
            ("open_gripper",     lambda: self._exec_gripper(GRIPPER_OPEN)),
            ("descend_to_pick",  lambda: self._exec_pose(_pose(pick_x, pick_y, pick_z))),
            ("close_gripper",    lambda: self._exec_gripper(GRIPPER_CLOSED)),
            ("lift",             lambda: self._exec_pose(_pose(pick_x, pick_y, pick_z + LIFT_OFFSET))),
            ("above_slot",       lambda: self._exec_pose(_pose(slot["x"], slot["y"], slot["z"] + APPROACH_OFFSET))),
            ("descend_to_slot",  lambda: self._exec_pose(_pose(**slot))),
            ("release",          lambda: self._exec_gripper(GRIPPER_OPEN)),
            ("retract",          lambda: self._exec_pose(_pose(slot["x"], slot["y"], slot["z"] + APPROACH_OFFSET))),
            ("home",             lambda: self._exec_pose(_pose(**HOME))),
        ]

        for step_name, action in steps:
            self.get_logger().info(f"  step: {step_name}")
            if not action():
                failure_mode = f"failed_at_{step_name}"
                self.get_logger().error(f"Step '{step_name}' failed — aborting")
                log_trial(trial_num, state_label, object_class, False,
                          time.time() - start_time, failure_mode)
                return False

        elapsed = time.time() - start_time
        log_trial(trial_num, state_label, object_class, True, elapsed)
        return True

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def run_manual(self):
        """Sort one object at the position given by ROS parameters."""
        cls   = self.get_parameter("target_class").get_parameter_value().string_value
        x     = self.get_parameter("target_x").get_parameter_value().double_value
        y     = self.get_parameter("target_y").get_parameter_value().double_value
        z     = self.get_parameter("target_z").get_parameter_value().double_value
        trial = self.get_parameter("trial_num").get_parameter_value().integer_value
        state = self.get_parameter("state_label").get_parameter_value().string_value
        self.sort_object(cls, x, y, z, trial_num=trial, state_label=state)

    def run_yolo(self):
        """Subscribe to YOLO-World detections and sort each detected object."""
        try:
            from yolo_msgs.msg import DetectionArray
        except ImportError:
            self.get_logger().error(
                "yolo_msgs not found — build and source yolo_ros first."
            )
            return

        state = self.get_parameter("state_label").get_parameter_value().string_value
        self._trial_count = self.get_parameter("trial_num").get_parameter_value().integer_value

        self.get_logger().info("Waiting for YOLO-World detections on /yolo/detections_3d ...")

        def _on_detection(msg: "DetectionArray"):
            if self._pick_done:
                return
            for det in msg.detections:
                raw_class = det.class_name.lower().strip()
                object_class = YOLO_CLASS_MAP.get(raw_class)
                if object_class is None:
                    continue  # not a target object

                pt = det.bbox3d.center.position
                self.get_logger().info(
                    f"Detected '{raw_class}' → '{object_class}' "
                    f"at ({pt.x:.3f}, {pt.y:.3f}, {pt.z:.3f})"
                )
                self._pick_done = True  # one pick at a time

                success = self.sort_object(
                    object_class, pt.x, pt.y, pt.z,
                    trial_num=self._trial_count, state_label=state,
                )
                self._trial_count += 1
                self._pick_done = False  # ready for next object
                return

        self.create_subscription(DetectionArray, "/yolo/detections_3d", _on_detection, 10)
        rclpy.spin(self)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args=None):
    rclpy.init(args=args)
    node = PharmacySort()

    mode = node.get_parameter("mode").get_parameter_value().string_value
    node.get_logger().info(f"pharmacy_sort starting in '{mode}' mode")

    try:
        if mode == "yolo":
            node.run_yolo()
        else:
            node.run_manual()
    except KeyboardInterrupt:
        pass

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
