"""MPU6050 sensor console reader for research telemetry only."""

from __future__ import annotations

import time


def get_drone_telemetry(i2c_address: int = 0x68) -> None:
    try:
        from mpu6050 import mpu6050
    except ImportError as exc:
        raise RuntimeError("MPU6050 reading requires mpu6050-raspberrypi; install project requirements.") from exc

    print(f"Initializing MPU6050 at I2C address {i2c_address:#04x}...")
    try:
        sensor = mpu6050(i2c_address)
        print("MPU6050 connected. Press Ctrl+C to stop.")
        while True:
            accel = sensor.get_accel_data()
            gyro = sensor.get_gyro_data()
            temperature = sensor.get_temp()
            print(
                "MPU6050 observation: "
                f"accel_g=({accel['x']:.2f}, {accel['y']:.2f}, {accel['z']:.2f}), "
                f"gyro_dps=({gyro['x']:.2f}, {gyro['y']:.2f}, {gyro['z']:.2f}), "
                f"temperature_c={temperature:.1f}"
            )
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("MPU6050 reader stopped.")
    except OSError as exc:
        raise RuntimeError(f"MPU6050 I2C communication failed: {exc}") from exc


if __name__ == "__main__":
    get_drone_telemetry()
