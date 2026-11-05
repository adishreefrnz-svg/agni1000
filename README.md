# FireRescueAI

FireRescueAI is a camera-based fire-rescue **research prototype** for Raspberry Pi. It records camera-based person-detection observations and can publish raw GPS, MPU6050, and DFRobot SEN0395 readings to a local, read-only review dashboard.

**Safety boundary:** detections and sensor values are unverified observations and require human review. This is not a flight-control, navigation, dispatch, or emergency-response system. It does not confirm that a person is present or alive, identify a rescue target, or assess whether anyone is safe or in danger. RGB footage must not be interpreted as detecting people through smoke, darkness, heat, or other obscurants. The SEN0395 feed is displayed as raw serial text only; no human-presence conclusion is derived from it. Do not use this prototype to trigger a flight or emergency action.

## Project layout

```text
FireRescue/
|-- main.py                       # YOLO/ByteTrack camera processing
|-- dashboard.py                  # Backwards-compatible dashboard launcher
|-- web/
|   `-- dashboard.py               # Local read-only web dashboard and JSON API
|-- sensors/
|   |-- camera.py                  # CSI/USB camera preview utility
|   |-- gps.py                     # RMC NMEA parsing and standalone reader
|   |-- mpu.py                     # MPU6050 standalone reader
|   |-- radar.py                   # SEN0395 raw UART reader
|   |-- telemetry.py               # Reads sensors and publishes telemetry.json
|   |-- sensor_fusion.py           # Read-only summary; does not fuse/verify sensors
|   `-- tracking.py                # Optional geometry helper; requires measured bearing
|-- tests/                         # Synthetic and prerecorded-style tests
|-- sample_videos/                 # Optional research footage
|-- screenshots/                   # Images saved from the camera preview
|-- output_recordings/             # CSV, annotated video, and telemetry JSON
|-- requirements.txt               # Python packages
`-- yolo11n.pt                     # Optional local model weights; not committed
```

Generated output is kept under `output_recordings/` and `screenshots/`. The `output_recordings/website` mock app was removed: it displayed invented GPS, radar, and person data and enabled Flask debug mode on every network interface. Use the actual-data dashboard described below instead.

## Raspberry Pi target and prerequisites

Target hardware: Raspberry Pi 4 Model B, Raspberry Pi OS Bookworm (64-bit recommended), and the 5MP CSI Camera Module v1.3. The application code is compatible with Python 3.11+; Bookworm's system Python is useful because Picamera2 is supplied as a Raspberry Pi OS package.

Connect the CSI camera with the Pi powered off and follow the board/camera manufacturer's connector and safety instructions. Confirm the camera before starting Python:

```bash
rpicam-hello --timeout 2000
```

Enable I2C and the UART hardware for the GPS/radar in `sudo raspi-config`. For the UART, disable the login shell over serial while enabling the serial port hardware. Reboot after changing interfaces. Verify the MPU6050 appears on I2C bus 1:

```bash
sudo i2cdetect -y 1
```

Use the sensor manufacturers' wiring and voltage instructions. GPS and radar need separate serial interfaces; do not connect both to the same UART. Device names vary by Pi configuration and USB adapter. Inspect available devices and pass the correct paths with `--gps-port` and `--radar-port`:

```bash
ls -l /dev/serial* /dev/ttyAMA* /dev/ttyUSB* 2>/dev/null
```

The SEN0395 output depends on its configured UART mode/firmware. This project intentionally forwards each received line as raw text and does not parse a target, distance, bearing, or person classification from it.

## Install on the Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-venv python3-picamera2 python3-opencv python3-smbus i2c-tools
cd ~/FireRescue
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`--system-site-packages` is needed for the OS-provided Picamera2 and camera bindings. The requirements also install Ultralytics and its PyTorch backend, which can be resource-intensive on a Pi 4. Use a 64-bit OS and enough free storage/memory. If pip reports that no compatible PyTorch wheel is available for the Pi's OS/Python architecture, stop there and use a PyTorch build explicitly supported for that OS; do not substitute an unverified wheel. The dashboard and sensor publisher can still be tested independently, but camera inference requires a working Ultralytics/PyTorch installation and model weights.

The first inference run may download model data if the requested weights are not present. The repository's local `yolo11n.pt` may be used if copied to the Pi; otherwise provide a model path with `--model` and ensure the Pi can access it.

## Start the project

Run each long-lived process in a separate terminal, from the project directory, after activating `.venv`.

### 1. Publish live sensor observations

```bash
python -m sensors.telemetry --gps-port /dev/serial0 --radar-port /dev/ttyAMA1 --verbose
```

Change the device paths to match the actual wiring. The defaults are examples, not guaranteed Pi 4 assignments. The service writes the latest readings and connection/error status to `output_recordings/telemetry.json`. GPS stays in `no_fix` until a valid NMEA fix arrives. The MPU6050 address defaults to `0x68`; override it, for example, with `--mpu-address 0x69` if the device is configured at that address. Sensor errors are logged and surfaced on the dashboard.

### 2. Run camera detection

Headless mode is suitable when the Pi is accessed over the network:

```bash
python main.py --source csi --no-display --csv --record
```

For a local preview window, remove `--no-display`; press `q` to stop or `s` to save a screenshot. For a USB webcam use `--source 0`; for prerecorded footage use `--source sample_videos/your_clip.mp4`.

The detector uses COCO person class `0` and persistent ByteTrack IDs. CSV rows are written to `output_recordings/detections.csv`; optional annotated video is written to `output_recordings/annotated_output.mp4`. The detections are not verified people counts. On a Pi 4, inference speed depends on the model, cooling, power supply, and input resolution.

### 3. Run the website on a trusted local Wi-Fi network

```bash
python -m web.dashboard --host 0.0.0.0 --port 8765
hostname -I
```

From another device on the same trusted network, open `http://<PI-IP-ADDRESS>:8765`. The dashboard automatically refreshes and reads the CSV, screenshots, and `telemetry.json`; it has no flight controls. Its JSON status endpoint is `/api/status`, and `/healthz` is a simple process check.

The server has no login or TLS and is for a trusted local network only. Do not expose port 8765 to the public internet, add router port forwarding, or use an untrusted Wi-Fi network. To run it only on the Pi itself, omit `--host 0.0.0.0` (the default is `127.0.0.1`). Stop each process with Ctrl+C.

The legacy command `python dashboard.py` still launches the same website. The dashboard uses only Python's standard library; Flask is not required.

## Standalone sensor utilities

```bash
python -m sensors.camera --source csi
python -m sensors.gps
python -m sensors.mpu
python -m sensors.radar
python -m sensors.sensor_fusion
```

The last command prints a read-only summary of files that actually exist. It does not perform sensor fusion or make a hazard assessment. `sensors/tracking.py` contains a generic coordinate estimate helper that requires both a measured distance and measured bearing; the current SEN0395 serial reader does not supply or consume those values.

## Tests and local development

Run focused tests without camera, I2C, GPS, or radar hardware:

```bash
python -m pytest -q
```

The tests use synthetic frames and temporary files. They validate person-class filtering, persistent ByteTrack arguments, output CSV writing, valid/invalid NMEA fixes, telemetry JSON, and dashboard data loading. A passing test run does not certify performance on the Pi or validate physical sensor wiring.

## Research review notes

Record false positives, missed detections, and tracking ID switches against the original footage. Treat every detection row and sensor reading as an observation requiring human review. Do not infer safety, entrapment, death, presence through smoke, or a rescue location from these outputs.
