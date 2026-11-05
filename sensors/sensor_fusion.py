"""Read-only summary of real telemetry and detection log files; no data fusion claims."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_review_summary(telemetry_path: Path, detections_path: Path) -> dict:
    telemetry = None
    if telemetry_path.is_file():
        with telemetry_path.open(encoding="utf-8") as file:
            telemetry = json.load(file)

    detection_rows = 0
    if detections_path.is_file():
        with detections_path.open(encoding="utf-8", newline="") as file:
            detection_rows = sum(1 for _ in csv.DictReader(file))

    return {
        "notice": "Unverified observations only; no cross-sensor confirmation or emergency assessment is performed.",
        "telemetry_available": telemetry is not None,
        "telemetry": telemetry,
        "detection_log_available": detections_path.is_file(),
        "detection_rows": detection_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telemetry", type=Path, default=ROOT / "output_recordings" / "telemetry.json")
    parser.add_argument("--csv", type=Path, default=ROOT / "output_recordings" / "detections.csv")
    args = parser.parse_args()
    print(json.dumps(build_review_summary(args.telemetry, args.csv), indent=2))


if __name__ == "__main__":
    main()
