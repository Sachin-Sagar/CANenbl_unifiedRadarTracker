# CAN Enabled Unified Radar Tracker

## 1. Project Overview

This project is a real-time radar tracking application that fuses sensor data with live vehicle data from a CAN bus. It interfaces with a radar sensor, processes the incoming point cloud through an advanced tracking pipeline, and enriches the tracking data with real-time vehicle signals like speed, torque, and gear state.

The application is designed for high performance and reliability, featuring a multi-process architecture to handle radar processing and CAN logging simultaneously without conflicts.

**Modes of Operation:**
*   **Live Mode:** Connects to a radar sensor and a CAN interface for real-time tracking and visualization.
*   **Playback Mode:** Replays pre-recorded data for testing and algorithm validation.
*   **No CAN Mode:** Runs the live radar tracker without requiring a CAN interface.

## 2. Installation

### Prerequisites
*   Python 3.10 or newer
*   **For Live Mode:**
    *   A compatible radar sensor
    *   A PCAN-USB or Kvaser CAN adapter

### Setup
This project uses `uv` for fast dependency management, but standard `pip` also works.

1.  **Create and activate a virtual environment:**
    ```bash
    # Using uv (recommended)
    uv venv
    source .venv/bin/activate

    # Or using standard venv
    python -m venv .venv
    source .venv/bin/activate # (On Windows: .venv\Scripts\Activate.ps1)
    ```

2.  **Install dependencies:**
    ```bash
    # Using uv
    uv pip install -r requirements.txt

    # Or using pip
    pip install -r requirements.txt
    ```

3.  **Install Hardware Drivers:**
    *   **Windows:** Install the appropriate drivers for your CAN hardware (e.g., PCAN-Basic or Kvaser drivers).
    *   **Linux (for PCAN):** Install `can-utils`. The required kernel modules are typically included in modern distributions.
        ```bash
        sudo apt update && sudo apt install can-utils
        ```

## 3. Configuration

### CAN Configuration
1.  **DBC File:** Place your CAN database file (e.g., `vehicle.dbc`) in the `input/` directory.
2.  **Signal List:** Edit `input/master_sigList.txt` to specify which signals you want to log and use in the tracker.

### Radar Configuration
*   **COM Port (Live Mode):** The application automatically searches for the correct serial port. If you need to override this, you can modify the port selection logic in `src/radar_tracker/main_live.py`.
*   **Radar Profile:** The radar configuration profile (`.cfg`) is located in the `configs/` directory.

## 4. How to Run

1.  **Activate your virtual environment:**
    ```bash
    source .venv/bin/activate
    ```

2.  **(Linux Only) Bring the CAN interface up:**
    Before starting the application, you must enable the `socketcan` interface.
    ```bash
    # Replace can0 if your interface has a different name
    sudo ip link set can0 up type can bitrate 500000
    ```

3.  **Run the application:**
    ```bash
    python main.py
    ```

4.  **Follow the prompts:**
    *   **Select Mode:** Choose between `Live Tracking` or `Playback from File`.
    *   **Select CAN Interface (Live Mode):** If you chose Live Mode, you will be prompted to select your hardware: `PEAK (pcan)`, `Kvaser`, or `No CAN`. The application will handle the rest.

5.  **To Stop:**
    *   Press `Ctrl+C` in the console or close the visualization window.

## 5. Key Features

### High-Performance Tracking
*   **IMM-JPDA Algorithm:** Uses an Interacting Multiple Model (IMM) filter and Joint Probabilistic Data Association (JPDA) for robust tracking of multiple, maneuvering targets.
*   **Ego-Motion Estimation:** Employs RANSAC to estimate the ego vehicle's motion, enabling superior classification of moving vs. stationary objects.
*   **Clutter Rejection:** A dual-box (static and dynamic) filtering system intelligently rejects stationary clutter like guardrails while correctly tracking stopped vehicles.

### Robust CAN Integration
*   **Multi-Process Architecture:** A dedicated process manages the CAN hardware, preventing resource conflicts and ensuring no data is lost. This process simultaneously logs all signals to a file while sharing live data with the radar tracker.
*   **Dynamic Interface Selection:** Automatically configures the correct `python-can` backend based on user selection (PEAK/Kvaser) and OS (Windows/Linux).
*   **Data Integrity:** All numeric data shared between processes is cast to standard Python `float` types, preventing the data corruption that can occur with `numpy` types in multiprocessing.
*   **Synchronization:** A `multiprocessing.Event` ensures the radar tracker waits for the CAN logger to be ready, solving a critical race condition and guaranteeing that CAN data is available from the very first frame.
*   **Full Data Integration:** The tracker's vehicle dynamics model now correctly uses live CAN torque, gear, and road grade signals to calculate a physics-based acceleration, which is correctly logged in the final output.

### Data Logging
*   **Organized Output:** All logs from a session (CAN, radar, track history, console) are saved into a single, timestamped directory (e.g., `output/YYYYMMDD_HHMMSS/`).
*   **Comprehensive Logs:** Includes a JSON Lines file for CAN signals, a raw radar log, the final track history with fused data, and console logs for debugging.

## 6. Hardware Recommendations

*   **On Linux (Recommended):**
    *   **Hardware:** PCAN-USB Adapter
    *   **Interface:** `SocketCAN`
    *   **Reasoning:** `socketcan` is integrated into the Linux kernel, offering the best stability. When prompted, choose `PEAK (pcan)`, and the application will automatically use the `socketcan` backend.

*   **On Windows:**
    *   **Hardware:** PCAN-USB or Kvaser Adapter
    *   **Reasoning:** Both are well-supported on Windows.

*   **Kvaser on Linux (Use with Caution):** Not recommended due to known driver incompatibilities between `python-can` and Kvaser's proprietary `canlib` on Linux, which can cause runtime crashes.

## 7. Testing

A unit test is available to perform a sanity check on the CAN service without requiring any connected hardware.

```bash
python -m unittest tests/test_can_service.py
```
