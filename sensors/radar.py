"""Read raw UART messages from a DFRobot SEN0395 radar module."""

from __future__ import annotations


def read_radar_data(serial_port: str = "/dev/ttyAMA1", baud_rate: int = 115200) -> None:
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("Radar serial reading requires pyserial; install project requirements.") from exc

    print(f"Opening SEN0395 serial input on {serial_port} at {baud_rate} baud...")
    try:
        with serial.Serial(serial_port, baudrate=baud_rate, timeout=1) as device:
            print("Connected. Raw messages are not interpreted as person or emergency detections.")
            print("Press Ctrl+C to stop.")
            while True:
                message = device.readline().decode("utf-8", errors="replace").strip()
                if message:
                    print(f"SEN0395 raw message: {message}")
    except KeyboardInterrupt:
        print("SEN0395 reader stopped.")
    except (OSError, serial.SerialException) as exc:
        raise RuntimeError(f"Could not read SEN0395 serial port {serial_port}: {exc}") from exc


if __name__ == "__main__":
    read_radar_data()
