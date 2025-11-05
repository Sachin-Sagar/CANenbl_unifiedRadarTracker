# CAN Enabled Unified Radar Tracker

## 1. Project Overview

This project is a real-time radar tracking application enhanced with live CAN bus data. It interfaces with a radar sensor, processes the incoming data through an advanced tracking pipeline, and fuses it with real-time vehicle data (like speed, torque, and gear) read from a CAN bus. This provides a more accurate and context-aware tracking solution.

The application can be run in two modes:

* **Live Mode:** Connects directly to radar hardware and a CAN interface for real-time tracking, visualization, and logging.
* **Playback Mode:** Processes pre-recorded radar and CAN data from log files for testing, validation, and algorithm development.

## 2. Features

### Radar Tracking

* **Advanced Tracking Algorithm:** Uses an Interacting Multiple Model (IMM) filter combined with a Joint Probabilistic Data Association (JPDA) algorithm for robust tracking of multiple objects.
* **Ego-Motion Estimation:** Employs RANSAC to estimate the ego vehicle's motion, enabling better distinction between moving and stationary objects.
* **Clutter Rejection:** Implements a dual-box filtering system (static and dynamic) to reject stationary clutter (e.g., guardrails) while tracking legitimate stationary targets (e.g., stopped vehicles).
* **Live Visualization:** Displays the radar's point cloud and tracked objects in real-time using PyQt5 and pyqtgraph.

### CAN Integration

* **High-Performance CAN Pipeline:** Utilizes a multiprocessing, shared-memory pipeline to reliably log signals from high-speed and low-speed CAN messages without data loss.
* **Simultaneous Logging & Live-Share:** A single CAN process both logs all decoded signals to a `can_log.json` file and shares the latest signal values to the live radar tracker via a shared memory dictionary.
* **DBC-Based Decoding:** Uses an industry-standard `.dbc` file to decode raw CAN messages into physical values.
* **Multi-Interface Support:** Supports both PEAK (PCAN) and Kvaser hardware. The application prompts the user to choose an interface at startup and dynamically configures the correct backend (`pcan`, `socketcan`, or `kvaser`) for the host OS (Windows/Linux).
* **Real-time Fusion:** The CAN data is interpolated, synchronized with the radar frames, and integrated directly into the `FHistFrame` object to provide the tracker with the vehicle's state.
* **Race Condition Fix for Live CAN Data:** A `multiprocessing.Event` is used to synchronize the CAN logger and radar tracker, ensuring the tracker waits for the first CAN message to be processed before beginning its main loop.
* **Robust Data Integrity:** Solved a critical data corruption bug by ensuring all CAN signals (like torque) are cast to native Python `float` types before being shared between processes, preventing pickling errors.
* **Vehicle Dynamics Model:** The tracker's ego-motion estimator now correctly uses live CAN data (torque, gear, and road grade) to calculate the vehicle's longitudinal acceleration, providing a more accurate physics-based state prediction.

## 3. System Architecture (Live Mode)

The application consists of three main components running in parallel to ensure high performance and prevent hardware conflicts:

1.  **Main/Radar Process (PyQt5 `QThread`):**
    * Runs the PyQt5 GUI for live visualization.
    * Runs the `RadarWorker` in a `QThread`.
    * The `RadarWorker` configures and reads from the **radar** sensor.
    * It reads the latest CAN data from a `Manager.dict()` (shared memory).
    * It interpolates the CAN data to match the radar timestamp.
    * It integrates the interpolated CAN data (e.g., vehicle speed, torque) directly into the `FHistFrame` object, which is then passed to the core `RadarTracker` algorithm.

2.  **CAN Process (Multiprocessing `Process`):**
    * A single, separate process that has exclusive control of the **CAN hardware**.
    * This process runs the high-performance `can_logger_app`.
    * **CANReader (Thread):** A dedicated thread *within* this process creates the `can.Bus` object, calls `.recv()`, and calls `.shutdown()`. This is crucial for avoiding `QObject` timer errors on Windows.
    * **Worker Pool (Processes):** Decodes raw CAN messages.
    * **LogWriter (Thread):** Writes all decoded signals to `can_log.json`.
    * **Live Data Sharing:** The worker pool simultaneously updates the `Manager.dict()` with the latest signal values for the main radar process to consume.

This architecture solves the Windows-specific hardware and threading conflicts by ensuring only one process accesses the CAN bus, and that the `can.Bus` object is created, used, and destroyed all within the same thread.

## 4. Installation and Setup

### Prerequisites

* Python 3.10 or newer.
* **Radar Hardware:** A compatible radar sensor (for Live Mode).
* **CAN Hardware:** A PCAN-USB or Kvaser adapter (for Live Mode).

### Package Management

This project uses `uv` for fast package management, but `pip` can also be used.

**Using `uv` (Recommended):**

```bash
# Create a virtual environment
uv venv

# Activate the environment
source .venv/bin/activate

# Install dependencies (from uv.lock if present, or requirements.txt)
uv pip install -r requirements.txt
Using pip:

Bash

# Create a virtual environment
python -m venv .venv

# Activate the environment
# Windows
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
Driver Installation
Windows: Install the appropriate drivers for your CAN hardware (e.g., PCAN-Basic or Kvaser drivers).

Linux (for PEAK/SocketCAN): Install can-utils and ensure the peak_usb kernel module is loaded.

Bash

sudo apt update
sudo apt install can-utils
Before running the application, you must bring the interface up:

Bash

# Replace can0 if your interface has a different name
sudo ip link set can0 up type can bitrate 500000
5. Hardware & CAN Configuration
Hardware Recommendations
On Linux (including Raspberry Pi):

Hardware: PCAN-USB Adapter.

Interface: SocketCAN.

Reasoning: The socketcan interface is natively supported by the Linux kernel, making it extremely stable and reliable. When the application prompts for an interface, choose PEAK (pcan), and it will automatically use the socketcan backend.

On Windows:

Hardware: PCAN-USB Adapter or Kvaser CAN Adapter.

Interface: PCAN-Basic or Kvaser CANlib.

Reasoning: Both PCAN and Kvaser are fully supported on Windows.

Kvaser Hardware Support
Windows: Kvaser hardware is fully supported.

Linux (Use With Caution): Using Kvaser on Linux is not recommended. There is a known incompatibility between python-can and Kvaser's proprietary Linux drivers (canlib) that can lead to runtime crashes.

CAN Configuration
Hardware Selection (Interactive): In Live Mode, the application will first prompt you to select your CAN hardware: PEAK (pcan), Kvaser, or No CAN. The correct python-can backend is then configured automatically. Selecting No CAN will bypass all CAN initialization.

DBC File: Place your CAN database file (e.g., VCU.dbc) in the input/ directory.

Signal List: Define the signals to be logged and used by the tracker in input/master_sigList.txt.

Raspberry Pi Specifics
Start Switch: Connect a physical switch between GPIO 17 and a ground pin. The application will wait for this switch to be turned ON to begin execution.

Onboard LED Feedback: The Raspberry Pi's onboard activity LED (led0) is used for status:

Solid ON: Application is running and logging.

OFF: Application is shut down.

Switch-OFF Shutdown: Turning the start switch OFF will trigger a graceful shutdown.

Note: This functionality requires RPi.GPIO and sudo privileges.

6. Data Logging
All output data from a single session is saved into a unique, timestamped directory to prevent overwriting and to keep logs organized.

Output Directory: output/YYYYMMDD_HHMMSS/

CAN Log: can_log_YYYY-MM-DD_HH-MM-SS.json - A JSON Lines file containing all decoded CAN signals.

Radar Log: radar_log.json - A log of the raw data frames from the radar sensor.

Track History: track_history.json - The final, processed tracking data, including fused CAN signals.

Console Log: console_log.json / console_log.txt - Logs of the console output for debugging.

Upon shutdown, the CAN logger will print a Data Logging Summary to the console. This report details which signals from the monitoring list were successfully logged and which (if any) were never seen on the bus.

7. Usage
Activate your virtual environment:

Bash

source .venv/bin/activate
Run the application (with sudo if on RPi for GPIOs):

Bash

# On RPi:
sudo python main.py

# On Windows/PC:
python main.py
Select Mode: Choose between (1) Live Tracking or (2) Playback from File.

Select CAN Interface (Live Mode Only): If you selected Live Tracking, you will then be prompted to choose your CAN hardware.

On Raspberry Pi (Live Mode): The application will wait for the physical switch to be turned ON to start. To stop, turn the switch OFF.

On Windows/other systems (Live Mode): The application will start immediately. To stop, close the visualization window or press Ctrl+C in the console.

8. Testing
A unit test is available to perform a sanity check on the CAN service integration. This test mocks the CAN hardware and can be run without any connected devices.

Bash

python -m unittest tests/test_can_service.py