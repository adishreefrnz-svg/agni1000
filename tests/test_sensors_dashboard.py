import json
from pathlib import Path

import pytest

from sensors.gps import parse_nmea_lat_lon
from sensors.sensor_fusion import build_review_summary
from sensors.telemetry import TelemetryStore
from sensors.tracking import estimate_object_gps
from web.dashboard import load_status


def test_parse_valid_rmc_nmea_coordinates_and_equator_zero():
    latitude, longitude = parse_nmea_lat_lon(
        "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W".split(",")
    )
    assert latitude == 48.1173
    assert longitude == 11.516667
    assert parse_nmea_lat_lon("$GPRMC,123519,A,0000.000,N,00000.000,E".split(",")) == (0.0, 0.0)


def test_reject_void_or_malformed_rmc_sentence():
    assert parse_nmea_lat_lon("$GPRMC,123519,V,4807.038,N,01131.000,E".split(",")) == (None, None)
    assert parse_nmea_lat_lon(["$GPRMC", "time", "A", "bad", "N", "01131.000", "E"]) == (None, None)
    assert parse_nmea_lat_lon(["$GPRMC", "time", "A", "4807.038", "E", "01131.000", "N"]) == (None, None)


def test_telemetry_store_writes_real_sensor_state(tmp_path: Path):
    output = tmp_path / "telemetry.json"
    store = TelemetryStore(output)
    store.update("gps", "connected", {"latitude": 0.0, "longitude": 0.0, "fix": True})
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["sensors"]["gps"]["data"]["fix"] is True
    assert payload["sensors"]["radar"]["status"] == "starting"


def test_dashboard_reads_only_existing_logs_and_sensor_state(tmp_path: Path):
    csv_path = tmp_path / "detections.csv"
    csv_path.write_text(
        "timestamp_utc,frame,track_id,confidence,x1,y1,x2,y2\n"
        "2026-01-01T00:00:00+00:00,1,7,0.9,1,2,3,4\n",
        encoding="utf-8",
    )
    screenshot_dir = tmp_path / "screenshots"
    screenshot_dir.mkdir()
    (screenshot_dir / "frame_000001.jpg").touch()
    telemetry_path = tmp_path / "telemetry.json"
    telemetry_path.write_text(
        json.dumps({"sensors": {"gps": {"status": "no_fix", "data": None}}}),
        encoding="utf-8",
    )
    status = load_status(csv_path, screenshot_dir, telemetry_path)
    assert status["detections"]["count"] == 1
    assert status["detections"]["track_ids"] == 1
    assert status["screenshots"] == ["frame_000001.jpg"]
    assert status["sensors"]["gps"]["status"] == "no_fix"
    assert status["sensors"]["mpu6050"]["status"] == "not_started"


def test_sensor_summary_does_not_invent_sensor_values(tmp_path: Path):
    summary = build_review_summary(tmp_path / "missing.json", tmp_path / "missing.csv")
    assert summary["telemetry_available"] is False
    assert summary["telemetry"] is None
    assert summary["detection_rows"] == 0
    assert "no cross-sensor confirmation" in summary["notice"]


def test_object_estimate_requires_measured_bearing():
    latitude, longitude = estimate_object_gps(0, 0, 100, 90)
    assert latitude == 0
    assert longitude == pytest.approx(0.000898, abs=1e-6)
    with pytest.raises(ValueError):
        estimate_object_gps(0, 0, -1, 90)
