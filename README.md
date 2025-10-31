# CAN Enabled Unified Radar Tracker

## 1. Project Overview

This project is a real-time radar tracking application enhanced with live CAN bus data. It interfaces with a radar sensor, processes the incoming data through an advanced tracking pipeline, and fuses it with real-time vehicle data (like speed) read from a CAN bus. This provides a more accurate and context-aware tracking solution.

The application can be run in two modes:

*   **Live Mode:** Connects directly to radar hardware and a CAN interface for real-time tracking and visualization.
*   **Playback Mode:** Processes pre-recorded radar and CAN data from log files for testing, validation, and algorithm development.

## 2. Features

### Radar Tracking

*   **Advanced Tracking Algorithm:** Uses an Interacting Multiple Model (IMM) filter combined with a Joint Probabilistic Data Association (JPDA) algorithm for robust tracking of multiple objects.
*   **Ego-Motion Estimation:** Employs RANSAC to estimate the ego vehicle's motion, enabling better distinction between moving and stationary objects.
*   **Clutter Rejection:** Implements a dual-box filtering system (static and dynamic) to reject stationary clutter (e.g., guardrails) while tracking legitimate stationary targets (e.g., stopped vehicles).
*   **Live Visualization:** Displays the radar's point cloud and tracked objects in real-time using PyQt5 and pyqtgraph.

### CAN Integration

*   **High-Performance CAN Logging:** Utilizes a multiprocessing, shared-memory pipeline to reliably log signals from high-speed and low-speed CAN messages without data loss.
*   **DBC-Based Decoding:** Uses an industry-standard `.dbc` file to decode raw CAN messages into physical values.
*   **Cross-Platform:** Automatically detects the host OS (Windows or Linux) and selects the correct CAN backend (`pcan` or `socketcan`).
*   **Real-time Fusion:** The CAN data is interpolated and synchronized with the radar frames to provide the tracker with the vehicle's state at the exact moment of the radar measurement.

### General

*   **Comprehensive Data Logging:** Saves raw radar data, processed track history, and console output for post-processing and debugging.
*   **Modular Architecture:** The radar processing, CAN handling, and GUI are separated into distinct modules for better maintainability.

## 3. System Architecture

The application consists of three main components running in parallel:

1.  **Main Application (GUI Thread):** The main thread runs the PyQt5 application, which provides the live visualization of the radar data and tracks.

2.  **RadarWorker (QThread):** A dedicated thread responsible for:
    *   Configuring and reading data from the radar sensor.
    *   Running the core tracking algorithm (`RadarTracker`).
    *   Fetching interpolated CAN data from the `LiveCANManager`.
    *   Passing the fused data to the GUI for display.

3.  **LiveCANManager (Multiprocessing):** A separate process that acts as a background data service for CAN information. It has its own internal pipeline:
    *   **CANReader (Thread):** Polls the CAN hardware for new messages.
    *   **Worker Pool (Processes):** A pool of worker processes decodes the raw CAN messages using the DBC file.
    *   **Data Buffer:** The decoded data is placed in a shared buffer, where it is read by the `RadarWorker`.

This architecture ensures that the high-frequency, I/O-bound tasks of reading from the radar and the CAN bus do not block the GUI or each other, leading to a responsive and high-performance system.

## 4. Installation and Setup

### Prerequisites

*   Python 3.10 or newer.
*   **Radar Hardware:** A compatible radar sensor.
*   **CAN Hardware:** A PCAN-USB adapter is recommended.
*   **Drivers (Windows):** Install the [PCAN-Basic drivers](https://www.peak-system.com/PCAN-Basic.239.0.html?&L=1).
*   **Drivers (Linux):** Install `can-utils`:
    ```bash
    sudo apt update
    sudo apt install can-utils
    ```

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
```

**Using `pip`:**

```bash
# Create a virtual environment
python -m venv .venv

# Activate the environment
# Windows
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## 5. Configuration

### Radar Configuration

*   **Sensor Profile:** The radar sensor's operating parameters are defined in `configs/profile_80_m_40mpsec_bsdevm_16tracks_dyClutter.cfg`.
*   **COM Port:** For live mode, you may need to edit `src/radar_tracker/main_live.py` and set the `CLI_COMPORT_NUM` variable to match your radar's serial port.

### CAN Configuration

*   **Hardware Settings:** The CAN interface (`pcan` or `socketcan`), channel, and bitrate are configured in the root `config.py` file. The application will auto-detect the OS, but you can modify these settings if needed.
*   **DBC File:** Place your CAN database file (e.g., `VCU.dbc`) in the `input/` directory.
*   **Signal List:** The list of signals to be logged and used by the tracker is defined in `input/master_sigList.txt`. The format is `CAN_ID,Signal_Name,CycleTime`.

## 6. Usage

1.  **Activate your virtual environment:**
    ```bash
    source .venv/bin/activate
    ```

2.  **(Linux Only) Bring up the CAN interface:**
    ```bash
    sudo ip link set can0 up type can bitrate 500000
    ```

3.  **Run the application:**
    ```bash
    python main.py
    ```

4.  **Select a mode:** The script will prompt you to choose between **(1) Live Tracking** or **(2) Playback from File**.

## 7. Testing

A unit test is available to perform a sanity check on the CAN service integration. This test mocks the CAN hardware and can be run without any connected devices.

```bash
python -m unittest tests/test_can_service.py
```


use: sudo ip link set can0 up type can bitrate 500000
after connecting peak