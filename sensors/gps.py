"""GPS NMEA parsing and optional serial console reader."""

from __future__ import annotations


def _coordinate(raw: str, direction: str, degree_digits: int) -> float:
    degrees = int(raw[:degree_digits])
    minutes = float(raw[degree_digits:])
    if not 0 <= minutes < 60:
        raise ValueError("NMEA minutes must be in [0, 60)")
    value = degrees + minutes / 60.0
    if direction in {"S", "W"}:
        value = -value
    elif direction not in {"N", "E"}:
        raise ValueError("Invalid NMEA direction")
    return value


def parse_nmea_lat_lon(parts: list[str]) -> tuple[float | None, float | None]:
    """Return decimal coordinates from a valid GPRMC/GNRMC sentence."""
    try:
        if len(parts) < 7 or not parts[0].endswith("RMC") or parts[2] != "A":
            return None, None
        if parts[4] not in {"N", "S"} or parts[6] not in {"E", "W"}:
            return None, None
        latitude = _coordinate(parts[3], parts[4], 2)
        longitude = _coordinate(parts[5], parts[6], 3)
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return None, None
        return round(latitude, 6), round(longitude, 6)
    except (ValueError, IndexError):
        return None, None


def read_gps_data(serial_port: str = "/dev/serial0", baud_rate: int = 9600) -> None:
    """Print valid GPS fixes from an NMEA serial stream; does not control a vehicle."""
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("GPS serial reading requires pyserial; install project requirements.") from exc

    print(f"Connecting to GPS on {serial_port} at {baud_rate} baud...")
    try:
        with serial.Serial(serial_port, baudrate=baud_rate, timeout=1) as device:
            print("Connected. Waiting for a valid satellite fix; press Ctrl+C to stop.")
            while True:
                line = device.readline().decode("ascii", errors="replace").strip()
                if line.startswith(("$GPRMC", "$GNRMC")):
                    latitude, longitude = parse_nmea_lat_lon(line.split(","))
                    if latitude is None or longitude is None:
                        print("No valid GPS fix yet.")
                    else:
                        print(f"GPS observation: latitude={latitude}, longitude={longitude}")
    except KeyboardInterrupt:
        print("GPS reader stopped.")
    except (OSError, serial.SerialException) as exc:
        raise RuntimeError(f"Could not read GPS serial port {serial_port}: {exc}") from exc


if __name__ == "__main__":
    read_gps_data()
