# CAN Enabled Unified Radar Tracker

## 1. Project Overview

This project is a real-time radar tracking application enhanced with live CAN bus data. It interfaces with a radar sensor, processes the incoming data through an advanced tracking pipeline, and fuses it with real-time vehicle data (like speed) read from a CAN bus. This provides a more accurate and context-aware tracking solution.

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
*   **Real-time Fusion:** The CAN data is interpolated, synchronized with the radar frames, and integrated directly into the `FHistFrame` object to provide the tracker with the vehicle's state (e.g., speed) at the exact moment of the radar measurement.

### General

* **Comprehensive Data Logging:** Saves raw radar data, processed track history, decoded CAN logs, and console output for post-processing and debugging.
* **Modular Architecture:** The radar processing, CAN handling, and GUI are separated into distinct modules for better maintainability.

## 3. System Architecture (Live Mode)

The application consists of three main components running in parallel to ensure high performance and prevent hardware conflicts:

1.  **Main/Radar Process (PyQt5 `QThread`):**
    * Runs the PyQt5 GUI for live visualization.
    * Runs the `RadarWorker` in a `QThread`.
    * The `RadarWorker` configures and reads from the **radar** sensor.
    * It reads the latest CAN data from a `Manager.dict()` (shared memory).
    * It interpolates the CAN data to match the radar timestamp.
    * **NEW:** It integrates the interpolated CAN data (e.g., vehicle speed) directly into the `FHistFrame` object, which is then passed to the core `RadarTracker` algorithm.

2.  **CAN Process (Multiprocessing `Process`):**
    * A single, separate process that has exclusive control of the **CAN hardware**.
    * This process runs the high-performance `can_logger_app`.
    * **CANReader (Thread):** A dedicated thread *within* this process creates the `can.Bus` object, calls `.recv()`, and calls `.shutdown()`. This is crucial for avoiding `QObject` timer errors on Windows.
    * **Worker Pool (Processes):** Decodes raw CAN messages.
    * **LogWriter (Thread):** Writes all decoded signals to `can_log.json`.
    * **Live Data Sharing:** The worker pool simultaneously updates the `Manager.dict()` with the latest signal values for the main radar process to consume.

This architecture solves the Windows-specific hardware and threading conflicts by ensuring only one process accesses the CAN bus, and that the `can.Bus` object is created, used, and destroyed all within the same thread.

## 5. Hardware Setup and Recommendations

For the best experience in **Live Mode**, please follow these hardware recommendations.

### Recommended Hardware

*   **On Linux (including Raspberry Pi):**
    *   **Hardware:** **PCAN-USB Adapter**.
    *   **Interface:** **SocketCAN**.
    *   **Reasoning:** The `socketcan` interface is natively supported by the Linux kernel, making it extremely stable and reliable. The necessary drivers are typically pre-installed. When the application prompts for an interface, choose **PEAK (pcan)**, and it will automatically use the `socketcan` backend.

*   **On Windows:**
    *   **Hardware:** **PCAN-USB Adapter** or **Kvaser CAN Adapter**.
    *   **Interface:** **PCAN-Basic** or **Kvaser CANlib**.
    *   **Reasoning:** Both PCAN and Kvaser are fully supported on Windows. Ensure you have the correct drivers installed for your chosen device.

### Kvaser Hardware Support

*   **Windows:** Kvaser hardware is fully supported on Windows. The application's architecture has been specifically designed to handle the driver interactions correctly.

*   **Linux (Use With Caution):** Using Kvaser on Linux is **not recommended**. There is a known, recurring incompatibility between `python-can` and Kvaser's proprietary Linux drivers (`canlib`). This can lead to runtime crashes (e.g., `NameError: name 'canGetNumberOfChannels' is not defined`), even if the drivers appear to be installed correctly. For Linux, a PCAN adapter using the native `socketcan` interface is the most reliable option.

For details on installing drivers, see the **Installation and Setup** section.

## 6. Data Logging

### Prerequisites

*   Python 3.10 or newer.

**Note:** The following hardware and drivers are only required for **Live Mode**.

*   **Radar Hardware:** A compatible radar sensor.
*   **CAN Hardware:** A PCAN-USB or Kvaser adapter is recommended.
*   **Drivers (Windows):** Install the appropriate drivers for your CAN hardware (e.g., [PCAN-Basic](https://www.peak-system.com/PCAN-Basic.239.0.html?&L=1) or Kvaser drivers).
*   **Drivers (Linux):** For PEAK hardware, install `can-utils`:
    ```bash
    sudo apt update
    sudo apt install can-utils
    ```

### Raspberry Pi Specifics

For Raspberry Pi deployments, the application includes GPIO-based controls:

* **Start Switch:** Connect a physical switch between **GPIO 17** (as defined by `BUTTON_PIN` in `config.py`) and a ground pin. The application will wait for this switch to be turned **ON** to begin execution.
* **Onboard LED Feedback:** The Raspberry Pi's onboard activity LED (`led0`) is used for status indications:
    * The LED stays **continuously ON** to indicate successful application startup and that logging has commenced.
    * The LED turns **OFF** upon shutdown to confirm that the application has received a shutdown signal and is terminating cleanly.
* **Switch-OFF Shutdown:** Turning the start switch **OFF** will trigger a graceful shutdown of the application.

**Note:** Controlling the onboard LED and accessing GPIO pins requires the `RPi.GPIO` library (automatically installed with project dependencies) and running the script with `sudo` privileges.

### Package Management

This project uses `uv` for fast package management, but `pip` can also be used.

**Using `uv` (Recommended):**

```bash
# Create a virtual environment
uv venv

# Activate the environment
source .venv/bin/activate

# Install dependencies
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
### CAN Configuration

*   **Hardware Selection (Interactive):** In Live Mode, the application will first prompt you to select your CAN hardware: `PEAK (pcan)` or `Kvaser`. The correct `python-can` backend is then configured automatically based on your choice and operating system.
*   **DBC File:** Place your CAN database file (e.g., `VCU.dbc`) in the `input/` directory.
*   **Signal List:** The list of signals to be logged and used by the tracker is defined in `input/master_sigList.txt`.

### Linux Specifics

If you are using a PEAK (PCAN) adapter on Linux, the application uses the `socketcan` backend. You must bring the interface up manually before running the script:

```bash
# Replace can0 if your interface has a different name
sudo ip link set can0 up type can bitrate 500000
```

## 6. Data Logging

All output data from a single session is saved into a unique, timestamped directory to prevent overwriting and to keep logs organized.

*   **Output Directory:** `output/YYYYMMDD_HHMMSS/`
*   **CAN Log:** `can_log_YYYY-MM-DD_HH-MM-SS.json` - A JSON Lines file containing all decoded CAN signals.
*   **Radar Log:** `radar_log.json` - A log of the raw data frames from the radar sensor.
*   **Track History:** `track_history.json` - The final, processed tracking data.
*   **Console Log:** `console_log.json` - A JSON file containing all the console output from the application, useful for debugging.

Upon shutdown, the CAN logger will print a **Data Logging Summary** to the console. This report details which signals from the monitoring list were successfully logged and which (if any) were never seen on the bus. This is useful for verifying that the CAN interface is working as expected.

## 7. Usage

1.  **Activate your virtual environment:**
    ```bash
    source .venv/bin/activate
    ```

2.  **Run the application:**
    ```bash
    python main.py
    ```

3.  **Select Mode:** The script will first prompt you to choose between `(1) Live Tracking` or `(2) Playback from File`.

4.  **Select CAN Interface (Live Mode Only):** If you selected Live Tracking, you will then be prompted to choose your CAN hardware.

*   **On Raspberry Pi (Live Mode):** After the initial prompts, the application will wait for the physical switch (connected to GPIO 17) to be turned **ON** to start the radar tracking and CAN logging. To stop the application, turn the switch **OFF**.
*   **On Windows/other systems (Live Mode):** The application will start immediately after mode selection. To stop the application, close the visualization window or press `Ctrl+C` in the console.

In all cases, the application is designed to shut down gracefully. This ensures that all data is saved correctly and that a final diagnostic report for the CAN logger is printed to the console.

8. Testing
A unit test is available to perform a sanity check on the CAN service integration. This test mocks the CAN hardware and can be run without any connected devices.

Bash

python -m unittest tests/test_can_service.py