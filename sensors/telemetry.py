"""Publish read-only Raspberry Pi sensor observations as a local JSON file."""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sensors.gps import parse_nmea_lat_lon

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output_recordings" / "telemetry.json"
LOGGER = logging.getLogger("fire_rescue.telemetry")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TelemetryStore:
    """Write the latest sensor observations atomically for the dashboard to read."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {
            "updated_at": utc_now(),
            "notice": "Sensor observations are unverified and require human review.",
            "sensors": {
                name: {"status": "starting", "updated_at": None, "data": None, "error": None}
                for name in ("gps", "mpu6050", "radar")
            },
        }
        self._write()

    def update(self, name: str, status: str, data: dict[str, Any] | None = None, error: str | None = None) -> None:
        with self.lock:
            self.state["updated_at"] = utc_now()
            self.state["sensors"][name] = {
                "status": status,
                "updated_at": utc_now(),
                "data": data,
                "error": error,
            }
            self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as file:
                temporary_path = file.name
                json.dump(self.state, file, ensure_ascii=True, indent=2)
                file.write("\n")
            os.replace(temporary_path, self.path)
        except OSError:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
            raise


def read_mpu(stop: threading.Event, store: TelemetryStore, address: int) -> None:
    from mpu6050 import mpu6050

    sensor = mpu6050(address)
    LOGGER.info("MPU6050 initialized at I2C address 0x%02x", address)
    while not stop.is_set():
        data = {
            "accelerometer_g": sensor.get_accel_data(),
            "gyroscope_dps": sensor.get_gyro_data(),
            "temperature_c": sensor.get_temp(),
        }
        store.update("mpu6050", "connected", data)
        stop.wait(0.2)


def read_gps(stop: threading.Event, store: TelemetryStore, port: str, baud: int) -> None:
    import serial

    with serial.Serial(port, baudrate=baud, timeout=1) as device:
        store.update("gps", "connected", {"latitude": None, "longitude": None, "fix": False})
        LOGGER.info("GPS serial input opened on %s", port)
        while not stop.is_set():
            sentence = device.readline().decode("ascii", errors="replace").strip()
            if not sentence.startswith(("$GPRMC", "$GNRMC")):
                continue
            latitude, longitude = parse_nmea_lat_lon(sentence.split(","))
            store.update(
                "gps",
                "connected" if latitude is not None else "no_fix",
                {"latitude": latitude, "longitude": longitude, "fix": latitude is not None},
            )


def read_radar(stop: threading.Event, store: TelemetryStore, port: str, baud: int) -> None:
    import serial

    with serial.Serial(port, baudrate=baud, timeout=1) as device:
        store.update("radar", "connected", {"raw_message": None})
        LOGGER.info("Radar serial input opened on %s", port)
        while not stop.is_set():
            message = device.readline().decode("utf-8", errors="replace").strip()
            if message:
                store.update("radar", "connected", {"raw_message": message})


def run_service(
    output: Path,
    gps_port: str,
    radar_port: str,
    gps_baud: int,
    radar_baud: int,
    mpu_address: int,
) -> None:
    store = TelemetryStore(output)
    stop = threading.Event()
    workers: list[tuple[str, Callable[[], None]]] = [
        ("mpu6050", lambda: read_mpu(stop, store, mpu_address)),
        ("gps", lambda: read_gps(stop, store, gps_port, gps_baud)),
        ("radar", lambda: read_radar(stop, store, radar_port, radar_baud)),
    ]

    def run_worker(name: str, worker: Callable[[], None]) -> None:
        try:
            worker()
        except Exception as exc:
            store.update(name, "error", error=str(exc))
            LOGGER.exception("%s sensor stopped", name)

    threads = [
        threading.Thread(target=run_worker, args=(name, worker), name=name, daemon=True)
        for name, worker in workers
    ]
    for thread in threads:
        thread.start()
    LOGGER.info("Telemetry publisher running; press Ctrl+C to stop.")
    try:
        while not stop.wait(1):
            pass
    except KeyboardInterrupt:
        LOGGER.info("Stopping telemetry publisher.")
        stop.set()
        for thread in threads:
            thread.join(timeout=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSON path read by the dashboard")
    parser.add_argument("--gps-port", default="/dev/serial0", help="GPS UART or USB serial device")
    parser.add_argument("--radar-port", default="/dev/ttyAMA1", help="SEN0395 UART or USB serial device")
    parser.add_argument("--gps-baud", type=int, default=9600)
    parser.add_argument("--radar-baud", type=int, default=115200)
    parser.add_argument("--mpu-address", type=lambda value: int(value, 0), default=0x68)
    parser.add_argument("--verbose", action="store_true", help="Log sensor status at INFO level")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(threadName)s: %(message)s",
    )
    run_service(args.output, args.gps_port, args.radar_port, args.gps_baud, args.radar_baud, args.mpu_address)


if __name__ == "__main__":
    main()
