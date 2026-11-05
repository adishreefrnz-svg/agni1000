"""Camera preview helper supporting the Raspberry Pi CSI and USB sources."""

from __future__ import annotations

import argparse

import cv2

from main import open_capture, parse_source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="csi", help="Use 'csi', a USB camera index, or a video file")
    args = parser.parse_args()
    source = parse_source(args.source)
    capture = open_capture(source)
    try:
        print("Camera preview ready. Press q in the window to exit.")
        while True:
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError("Camera did not provide a frame")
            cv2.imshow("FireRescueAI camera preview", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
