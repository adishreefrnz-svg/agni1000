"""FireRescueAI camera-based fire-rescue research prototype.

This project detects and tracks people in RGB video for research review only.
It does not control a drone, navigate autonomously, or validate emergencies.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, TextIO

import cv2


@dataclass(frozen=True)
class Detection:
    """One unverified person detection in a frame."""

    track_id: int | None
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int


def parse_source(source: str) -> int | str:
    """Return a camera index, CSI camera selector, or prerecorded path."""
    if source.strip().lower() in {"csi", "picamera2"}:
        return "csi"
    try:
        return int(source)
    except ValueError:
        return source


def load_model(model_path: str) -> Any:
    """Load Ultralytics lazily so capture utilities remain easy to test."""
    try:
        from ultralytics import YOLO

        return YOLO(model_path)
    except Exception as exc:  # Ultralytics can raise several model/backend errors.
        raise RuntimeError(f"Could not load YOLO model '{model_path}': {exc}") from exc


class Picamera2Capture:
    """Adapt Picamera2 frames to the OpenCV capture interface used by the app."""

    def __init__(self) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                "CSI camera support requires Picamera2. Install it with "
                "'sudo apt install python3-picamera2' and create the venv with "
                "'--system-site-packages'."
            ) from exc
        self.camera = Picamera2()
        config = self.camera.create_video_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        self.camera.configure(config)
        self.camera.start()

    def read(self) -> tuple[bool, Any]:
        frame = self.camera.capture_array()
        return True, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def release(self) -> None:
        self.camera.stop()
        self.camera.close()


def open_capture(source: int | str) -> Any:
    if source == "csi":
        return Picamera2Capture()
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        capture.release()
        description = f"camera {source}" if isinstance(source, int) else f"video file '{source}'"
        raise RuntimeError(f"Could not open {description}. Check permissions and the path.")
    return capture


def extract_person_detections(results: Iterable[Any]) -> list[Detection]:
    """Convert an Ultralytics result into person-only, displayable detections."""
    detections: list[Detection] = []
    for result in results:
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue
        coordinates = boxes.xyxy.cpu().tolist() if hasattr(boxes.xyxy, "cpu") else boxes.xyxy.tolist()
        confidences = boxes.conf.cpu().tolist() if hasattr(boxes.conf, "cpu") else boxes.conf.tolist()
        classes = boxes.cls.cpu().tolist() if hasattr(boxes.cls, "cpu") else boxes.cls.tolist()
        ids = getattr(boxes, "id", None)
        track_ids = ids.cpu().tolist() if ids is not None and hasattr(ids, "cpu") else (ids.tolist() if ids is not None else [])
        for index, (box, confidence, class_id) in enumerate(zip(coordinates, confidences, classes)):
            if int(class_id) != 0:
                continue
            track_id = int(track_ids[index]) if index < len(track_ids) else None
            x1, y1, x2, y2 = (int(value) for value in box)
            detections.append(Detection(track_id, float(confidence), x1, y1, x2, y2))
    return detections


def draw_detections(frame: Any, detections: list[Detection]) -> Any:
    for detection in detections:
        cv2.rectangle(frame, (detection.x1, detection.y1), (detection.x2, detection.y2), (0, 180, 255), 2)
        identifier = f"ID {detection.track_id}" if detection.track_id is not None else "ID ?"
        label = f"{identifier} {detection.confidence:.2f}"
        cv2.putText(frame, label, (detection.x1, max(20, detection.y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 180, 255), 2)
    cv2.putText(frame, f"People: {len(detections)}", (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (50, 220, 80), 2)
    cv2.putText(frame, "UNVERIFIED - HUMAN REVIEW REQUIRED", (16, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 80, 255), 2)
    return frame


def write_detection_rows(writer: csv.writer, detections: list[Detection], timestamp: str, frame_number: int) -> None:
    for detection in detections:
        writer.writerow([timestamp, frame_number, detection.track_id or "", f"{detection.confidence:.4f}", detection.x1, detection.y1, detection.x2, detection.y2])


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FireRescueAI person detection and tracking research prototype")
    parser.add_argument("--source", default="0", help="Camera index, 'csi' for a Raspberry Pi CSI camera, or prerecorded video path")
    parser.add_argument("--model", default="yolo11n.pt", help="Ultralytics pretrained model weights")
    parser.add_argument("--conf", type=float, default=0.35, help="Minimum confidence threshold")
    parser.add_argument("--record", action="store_true", help="Record annotated output")
    parser.add_argument("--no-display", action="store_true", help="Run without an OpenCV preview window (useful on a headless Pi)")
    parser.add_argument("--csv", action="store_true", help="Write detection rows to detections.csv")
    parser.add_argument("--screenshot-dir", type=Path, default=Path("screenshots"), help="Directory for screenshots captured with the s key")
    parser.add_argument("--output-dir", type=Path, default=Path("output_recordings"), help="Directory for recordings and CSV logs")
    return parser


def run(source: int | str, model: Any, *, conf: float = 0.35, record: bool = False, csv_log: bool = False, screenshot_dir: Path = Path("screenshots"), output_dir: Path = Path("output_recordings"), capture: Any = None, display: bool = True) -> int:
    capture = capture or open_capture(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    writer = None
    video_writer = None
    csv_file: TextIO | None = None
    try:
        if csv_log:
            csv_file = (output_dir / "detections.csv").open("w", newline="", encoding="utf-8")
            writer = csv.writer(csv_file)
            writer.writerow(["timestamp_utc", "frame", "track_id", "confidence", "x1", "y1", "x2", "y2"])
        window_name = "FireRescueAI - research review"
        if display:
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        frame_number = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_number += 1
            if isinstance(source, int):
                frame = cv2.flip(frame, 1)
            results = model.track(frame, persist=True, tracker="bytetrack.yaml", classes=[0], conf=conf, verbose=False)
            detections = extract_person_detections(results)
            timestamp = datetime.now(timezone.utc).isoformat()
            if writer:
                write_detection_rows(writer, detections, timestamp, frame_number)
            annotated = draw_detections(frame, detections)
            if record:
                if video_writer is None:
                    height, width = annotated.shape[:2]
                    video_writer = cv2.VideoWriter(str(output_dir / "annotated_output.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 20.0, (width, height))
                video_writer.write(annotated)
            if display:
                cv2.imshow(window_name, annotated)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("s"):
                    filename = screenshot_dir / f"frame_{frame_number:06d}.jpg"
                    cv2.imwrite(str(filename), annotated)
                    print(f"Screenshot saved: {filename}")
        return 0
    finally:
        capture.release()
        if video_writer is not None:
            video_writer.release()
        if csv_file is not None:
            csv_file.close()
        if display:
            cv2.destroyAllWindows()


def main() -> int:
    args = create_parser().parse_args()
    if not 0.0 <= args.conf <= 1.0:
        print("Error: --conf must be between 0 and 1.", file=sys.stderr)
        return 2
    try:
        source = parse_source(args.source)
        if isinstance(source, str) and source != "csi" and not Path(source).is_file():
            raise FileNotFoundError(f"Video file not found: {source}")
        model = load_model(args.model)
        return run(source, model, conf=args.conf, record=args.record, csv_log=args.csv, screenshot_dir=args.screenshot_dir, output_dir=args.output_dir, display=not args.no_display)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Stopped by user.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
