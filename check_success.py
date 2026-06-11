#!/usr/bin/env python3
"""
Automated success checker for pharmacy sorting trials.

Grabs one frame from the overhead RealSense camera (via ROS2 topic),
runs YOLO to find the pill bottle, and checks if it is inside the
pre-calibrated bin ROI.

One-time calibration (run before trials):
    python3 final_project/check_success.py --calibrate

Normal use (called by run_trial.sh — exits 0=success, 1=fail):
    python3 final_project/check_success.py

Debug mode (shows annotated frame):
    python3 final_project/check_success.py --debug
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np

ROI_FILE = os.path.join(os.path.dirname(__file__), "bin_roi.json")
CAMERA_TOPIC = "/static_camera/overhead_cam/color/image_raw/compressed"
YOLO_MODEL = os.path.expanduser("~/techin517/yolov8n.pt")
CONF_THRESH = 0.35


# ---------------------------------------------------------------------------
# Camera: grab one frame from the ROS2 compressed image topic
# ---------------------------------------------------------------------------

def grab_frame(timeout_sec: float = 5.0):
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import CompressedImage

    class _Grabber(Node):
        def __init__(self):
            super().__init__("_success_grabber")
            self.frame = None
            self.create_subscription(CompressedImage, CAMERA_TOPIC, self._cb, 1)

        def _cb(self, msg):
            arr = np.frombuffer(msg.data, np.uint8)
            self.frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    rclpy.init()
    node = _Grabber()
    deadline = node.get_clock().now().nanoseconds / 1e9 + timeout_sec
    while node.frame is None:
        rclpy.spin_once(node, timeout_sec=0.1)
        if node.get_clock().now().nanoseconds / 1e9 > deadline:
            node.destroy_node()
            rclpy.shutdown()
            raise RuntimeError(f"Timed out waiting for frame on {CAMERA_TOPIC}")
    frame = node.frame.copy()
    node.destroy_node()
    rclpy.shutdown()
    return frame


# ---------------------------------------------------------------------------
# YOLO: detect pill bottle, return list of (cx, cy, conf) tuples
# ---------------------------------------------------------------------------

def detect_bottle(frame):
    from ultralytics import YOLO
    model = YOLO(YOLO_MODEL)
    results = model(frame, conf=CONF_THRESH, verbose=False)[0]
    detections = []
    for box in results.boxes:
        cls_id = int(box.cls[0])
        if cls_id != 39:          # COCO class 39 = bottle
            continue
        conf = float(box.conf[0])
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        detections.append((cx, cy, conf, (x1, y1, x2, y2)))
    return detections


# ---------------------------------------------------------------------------
# ROI helpers
# ---------------------------------------------------------------------------

def load_roi():
    if not os.path.exists(ROI_FILE):
        print(f"[check_success] No ROI file found at {ROI_FILE}")
        print("Run with --calibrate first: python3 final_project/check_success.py --calibrate")
        sys.exit(2)
    with open(ROI_FILE) as f:
        d = json.load(f)
    return d["x"], d["y"], d["w"], d["h"]


def point_in_roi(cx, cy, x, y, w, h):
    return x <= cx <= x + w and y <= cy <= y + h


# ---------------------------------------------------------------------------
# Calibration: interactive ROI selection
# ---------------------------------------------------------------------------

def calibrate():
    print("Calibration: place the pill bottle INSIDE the bin, then run this.")
    print("Grabbing frame from overhead camera...")
    frame = grab_frame()

    print("Draw a rectangle around the bin opening, then press ENTER or SPACE to confirm.")
    print("Press C to cancel and redraw.")
    roi = cv2.selectROI("Select BIN region — press ENTER to confirm", frame,
                        fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()

    x, y, w, h = [int(v) for v in roi]
    if w == 0 or h == 0:
        print("No ROI selected. Calibration cancelled.")
        sys.exit(1)

    data = {"x": x, "y": y, "w": w, "h": h}
    with open(ROI_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Saved bin ROI: {data}")
    print(f"ROI file: {ROI_FILE}")

    # Show confirmation
    preview = frame.copy()
    cv2.rectangle(preview, (x, y), (x + w, y + h), (0, 255, 0), 2)
    cv2.putText(preview, "BIN ROI", (x, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.imshow("Calibrated bin ROI — press any key", preview)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------

def check(debug: bool = False) -> bool:
    rx, ry, rw, rh = load_roi()

    print("[check_success] Grabbing frame...")
    frame = grab_frame()

    print("[check_success] Running YOLO detection...")
    detections = detect_bottle(frame)

    success = False
    for cx, cy, conf, bbox in detections:
        in_bin = point_in_roi(cx, cy, rx, ry, rw, rh)
        print(f"  bottle detected at ({cx},{cy}) conf={conf:.0%} in_bin={in_bin}")
        if in_bin:
            success = True

    if not detections:
        print("  no bottle detected in frame")

    if debug:
        vis = frame.copy()
        # Draw bin ROI
        cv2.rectangle(vis, (rx, ry), (rx + rw, ry + rh), (0, 255, 0), 2)
        cv2.putText(vis, "BIN", (rx, ry - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        # Draw detections
        for cx, cy, conf, (x1, y1, x2, y2) in detections:
            color = (0, 200, 0) if point_in_roi(cx, cy, rx, ry, rw, rh) else (0, 0, 255)
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
            cv2.putText(vis, f"{conf:.0%}", (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        label = "SUCCESS" if success else "FAIL"
        color = (0, 200, 0) if success else (0, 0, 255)
        cv2.putText(vis, label, (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3)
        cv2.imshow("Success check — press any key", vis)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return success


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true",
                        help="Interactive bin ROI calibration (run once before trials)")
    parser.add_argument("--debug", action="store_true",
                        help="Show annotated frame after check")
    args = parser.parse_args()

    if args.calibrate:
        calibrate()
        return

    success = check(debug=args.debug)
    print(f"[check_success] Result: {'SUCCESS' if success else 'FAIL'}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
