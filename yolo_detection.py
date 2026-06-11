"""
Pharmacy Logistics Sorting Assistant — YOLO Object Detection Demo
TECHIN 517 Mid-Project Demo

Runs YOLOv8 on a live webcam feed to detect medication objects.
Uses YOLO-World for open-vocabulary detection (can detect any object by name).

Setup:
    pip install ultralytics

Usage:
    # Standard YOLOv8 — detects "bottle" (pill bottle) automatically:
    python3 yolo_detection.py

    # YOLO-World — detects custom objects by name:
    python3 yolo_detection.py --world --classes "pill bottle" "medicine case" "small box"

    # Save demo video:
    python3 yolo_detection.py --save demo_yolo.mp4

    # Use a specific camera (e.g. index 1 or 2):
    python3 yolo_detection.py --camera 1
"""

import argparse
import time

import cv2


# Standard COCO classes we care about for pharmacy sorting.
# "bottle" (39) will confidently fire on the orange pill bottle.
PHARMACY_CLASSES = {
    39: "pill bottle",   # COCO "bottle"
    76: "scissors",      # ignore — listed so we can filter
}
KEEP_COCO_IDS = {39}     # only show detections for these class IDs


def load_model(use_world: bool, custom_classes: list[str]):
    from ultralytics import YOLO

    if use_world:
        print("[YOLO] Loading YOLO-World model (yolov8s-world)...")
        model = YOLO("yolov8s-worldv2.pt")
        # Set the custom vocabulary — detects exactly what you name
        model.set_classes(custom_classes)
        print(f"[YOLO] Detecting: {custom_classes}")
    else:
        print("[YOLO] Loading YOLOv8n (standard COCO)...")
        model = YOLO("yolov8n.pt")
        print("[YOLO] Detecting: pill bottle (COCO class 39)")

    return model


def run_detection(model, camera_idx: int, use_world: bool, save_path: str):
    cap = cv2.VideoCapture(camera_idx)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,  720)

    if not cap.isOpened():
        print(f"[Error] Cannot open camera {camera_idx}")
        return

    writer = None
    if save_path:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(save_path, fourcc, 30.0, (1280, 720))
        print(f"[YOLO] Saving to {save_path}")

    fps_timer = time.time()
    frame_count = 0
    fps = 0.0

    print("[YOLO] Running — press Q to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.resize(frame, (1280, 720))

        # Run inference (conf=0.35 is a good threshold for live demo)
        results = model(frame, conf=0.35, verbose=False)[0]

        # Draw detections
        object_count = 0
        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf   = float(box.conf[0])

            # For standard YOLO, only show pharmacy-relevant classes
            if not use_world and cls_id not in KEEP_COCO_IDS:
                continue

            object_count += 1
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            # Label
            if use_world:
                label = f"{results.names[cls_id]} {conf:.0%}"
            else:
                label = f"{PHARMACY_CLASSES.get(cls_id, results.names[cls_id])} {conf:.0%}"

            # Color: green for high confidence, yellow for medium
            color = (0, 220, 0) if conf >= 0.6 else (0, 200, 200)

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.drawMarker(frame, (cx, cy), color, cv2.MARKER_CROSS, 20, 2)

            # Label background
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

            # Print centroid to terminal (useful for showing IK target in demo)
            print(f"  → {label}  centroid=({cx}, {cy})", end="\r")

        # HUD
        h, w = frame.shape[:2]
        cv2.putText(frame, f"Objects detected: {object_count}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        mode = "YOLO-World" if use_world else "YOLOv8 COCO"
        cv2.putText(frame, f"Mode: {mode}", (10, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        cv2.putText(frame, "TECHIN517 | Pharmacy Sorting", (10, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1)

        # FPS
        frame_count += 1
        elapsed = time.time() - fps_timer
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            frame_count = 0
            fps_timer = time.time()
        cv2.putText(frame, f"FPS: {fps:.1f}", (w - 110, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        cv2.imshow("TECHIN517 Pharmacy YOLO Demo", frame)
        if writer:
            writer.write(frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    if writer:
        writer.release()
    cv2.destroyAllWindows()
    print()


def main():
    parser = argparse.ArgumentParser(description="Pharmacy YOLO Detection Demo")
    parser.add_argument("--camera",  type=int, default=0,
                        help="Camera index (default 0 = built-in webcam)")
    parser.add_argument("--world",   action="store_true",
                        help="Use YOLO-World for open-vocabulary detection")
    parser.add_argument("--classes", nargs="+",
                        default=["pill bottle", "medicine tube", "medicine box", "eye gel box"],
                        help="Objects to detect (YOLO-World mode only)")
    parser.add_argument("--save",    type=str, default="",
                        help="Save output to this .mp4 file")
    args = parser.parse_args()

    try:
        model = load_model(args.world, args.classes)
    except Exception as e:
        print(f"[Error] Could not load model: {e}")
        print("Make sure ultralytics is installed: pip install ultralytics")
        return

    run_detection(model, args.camera, args.world, args.save)


if __name__ == "__main__":
    main()
