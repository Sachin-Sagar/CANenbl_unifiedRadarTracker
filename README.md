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
*   **Dual Pipeline Processing:** The CAN logger uses a dual-pipeline architecture to process high-frequency (e.g., 10ms) and low-frequency (e.g., 100ms) signals in parallel. This ensures that time-sensitive, high-frequency data is not delayed by bursts of low-frequency messages, significantly improving real-time performance.
*   **Multi-Process Architecture:** A dedicated process manages the CAN hardware, preventing resource conflicts and ensuring no data is lost. This process simultaneously logs all signals to a file while sharing live data with the radar tracker.
*   **Dynamic Interface Selection:** Automatically afigures the correct `python-can` backend based on user selection (PEAK/Kvaser) and OS (Windows/Linux).
*   **Data Integrity:** All numeric data shared between processes is cast to standard Python `float` types, preventing the data corruption that can occur with `numpy` types in multiprocessing.
*   **Synchronization:** A `multiprocessing.Event` ensures the radar tracker waits for the CAN logger to be ready, solving a critical race condition and guaranteeing that CAN data is available from the very first frame.
*   **Process Health Monitoring:** The CAN logger process includes periodic health checks that log the status of its internal threads and worker processes at the `DEBUG` level, providing visibility for troubleshooting.
*   **Full Data Integration:** The tracker's vehicle dynamics model now correctly uses live CAN torque, gear, and road grade signals to calculate a physics-based acceleration, which is correctly logged in the final output.
*   **Reliable CAN Data Decoding:** Resolved an issue where decoded CAN signal values in `can_log.json` were static due to an indentation error in the processing logic. The decoding now functions correctly for every message.
*   **Clean Debug Logging:** Eliminated debug message spam in `can_logger_console.log` by ensuring that debug messages are only generated for CAN messages that are actively being processed and are relevant to the configured signal list.

### Data Logging
*   **Organized Output:** All logs from a session (CAN, radar, track history, console) are saved into a single, timestamped directory (e.g., `output/YYYYMMDD_HHMMSS/`).
*   **Categorized Console Logs:** To simplify debugging, all console output is split into three distinct files within the `output/YYYYMMDD_HHMMSS/console_out/` directory:
    *   `can_processing.log`: Logs related to the CAN bus, decoding, and data sharing.
    *   `radar_processing.log`: Logs related to radar configuration, data parsing, and hardware communication.
    *   `tracking.log`: Logs related to the core tracking algorithm, including track creation, updates, and state estimation.
*   **Comprehensive Data:** Includes a JSON Lines file for raw CAN signals, a raw radar log, and the final track history with fused data.

## 6. Hardware Recommendations

*   **On Linux (Recommended):**
    *   **Hardware:** PCAN-USB Adapter
    *   **Interface:** `SocketCAN`
    *   **Reasoning:** `socketcan` is integrated into the Linux kernel, offering the best stability. When prompted, choose `PEAK (pcan)`, and the application will automatically use the `socketcan` backend.

*   **On Windows:**
    *   **Hardware:** PCAN-USB or Kvaser Adapter
    *   **Reasoning:** Both are well-supported on Windows.

*   **Kvaser on Linux (Use with Caution):** Not recommended due to known driver incompatibilities between `python-can` and Kvaser's proprietary `canlib` on Linux, which can cause runtime crashes.

## 7. System Architecture

The application uses a multi-process architecture to ensure stability and performance, especially on Windows.

1.  **Main/Radar Process (Main Thread + QThread):**
    *   Runs the main `main.py` script.
    *   Launches the CAN Process.
    *   Launches the `RadarWorker` in a `QThread` to handle real-time radar data processing.
    *   The `RadarWorker` reads live CAN data from a shared dictionary, interpolates it, and runs the tracking algorithm.

2.  **CAN Process (`multiprocessing.Process`):**
    *   This process has exclusive control of the CAN hardware.
    *   It runs the `can_logger_app`, which contains:
        *   A dedicated **CANReader Thread** that manages the `can.interface.Bus` object to prevent Qt threading errors.
        *   A pool of worker sub-processes to decode CAN messages.
        *   A **LogWriter Thread** that writes all decoded signals to `can_log.json`.
        *   A mechanism to write the latest signal values into a shared dictionary for the Main/Radar Process.

This design isolates the hardware-specific CAN operations from the main application, preventing resource conflicts and solving cross-platform threading issues.

## 8. Troubleshooting and Known Issues

*   **`AttributeError` on Startup (Windows with Kvaser):**
    *   **Symptom:** The application fails to start the CAN logger process with an `AttributeError: 'NoneType' object has no attribute 'DEBUG_PRINTING'`.
    *   **Cause:** This is a `multiprocessing` issue on Windows where relative imports within the `can_logger_app` fail to load modules correctly in the spawned child process, causing the `config` object to be `None`. A typo in a debug flag name also contributed.
    *   **Solution:** All relative imports within the `can_logger_app` have been converted to absolute imports, and the configuration variable name has been corrected. This ensures modules are loaded reliably.

*   **Kvaser on Linux Fails to Initialize:**
    *   **Symptom:** The application crashes with a `NameError: name 'canGetNumberOfChannels' is not defined` when using Kvaser hardware on Linux.
    *   **Cause:** This is due to a known incompatibility between the `python-can` library and Kvaser's proprietary Linux drivers.
    *   **Solution:** Use PCAN hardware with the `SocketCAN` interface on Linux. It is more stable and integrated directly into the Linux kernel. When prompted, select `PEAK (pcan)`.

*   **`QObject` Timer Errors on Shutdown (Windows):**
    *   **Symptom:** The application crashes on exit with `QObject::~QObject: Timers cannot be stopped from another thread`.
    *   **Cause:** The `python-can` `pcan` backend uses Qt. This error occurs if the `can.Bus` object is created in a different thread from where it is used and destroyed.
    *   **Solution:** The application's architecture now ensures the CAN bus object's entire lifecycle is handled within a single, dedicated thread inside the `CAN Process`, which has resolved this issue.

*   **`PermissionError: [WinError 5] Access is denied` on Startup (Windows):**
    *   **Symptom:** The application fails to start the CAN logger process.
    *   **Cause:** A `multiprocessing` issue on Windows where non-picklable resources (like hardware handles) are inherited by child processes, causing a crash.
    *   **Solution:** All hardware-related modules are now imported within the `if __name__ == '__main__':` block in `main.py`, preventing this issue.

*   **Unnecessary Wait in "No CAN" Mode:**
    *   **Symptom:** In "No CAN" mode, the application would pause for 10 seconds, appearing to wait for a CAN logger that was not active.
    *   **Cause:** The `RadarWorker` was waiting for a `can_logger_ready` event that would never be triggered in this mode.
    *   **Solution:** The application now passes a `None` value for the event when "No CAN" mode is selected, causing the `RadarWorker` to correctly bypass the waiting period.

*   **Data Corruption in Log Files (`track_history.json`, `can_log.json`):**
    *   **Symptom:** Numeric values in the JSON log files appear as massive, incorrect numbers.
    *   **Cause:** Passing non-standard numeric types (like `numpy.float64` or C-style `doubles`) between processes or to the `json.dumps()` function can cause corruption.
    *   **Solution:** The entire data pipeline now explicitly casts all numeric values to a standard Python `float()` at every stage: when sharing data between processes, when interpolating values, and before writing to a JSON file. This ensures data integrity.

## 9. Changelog

This section highlights recent key improvements and bug fixes.

*   **CAN Data Integrity:**
    *   **Fix (Part 19):** Resolved a critical bug where the `can_log.json` file was being corrupted. The issue was caused by writing C-style `double` data types directly to JSON. The fix involves casting the value to a standard Python `float` before serialization.
    *   **Fix (Part 18):** Addressed data corruption in the final `track_history.json` caused by `numpy.interp` returning a `numpy.float64`. The interpolated value is now cast to a standard Python `float`.
    *   **Fix (Part 17):** Corrected a data corruption issue that occurred when passing CAN signal timestamps (`numpy.float64`) between processes. All parts of the signal (value and timestamp) are now cast to `float` before being put in the shared dictionary.

*   **Algorithm and Data Fusion:**
    *   **Fix (Part 17):** The `estimatedAcceleration_mps2` is now correctly calculated and logged. The ego-motion estimator now returns the final, corrected value from its EKF.
    *   **Feature (Part 16):** The `EstimatedGrade_Est_Deg` (road grade) signal is now fully integrated into the vehicle dynamics model.
    *   **Fix (Part 15):** The `ETS_MOT_ShaftTorque_Est_Nm` (torque) signal is now correctly used by the tracking algorithm, and the calculated acceleration is properly saved.

*   **System Stability and Usability:**
    *   **Feature (Part 14):** Added a "No CAN" mode to allow the radar tracker to run without any CAN hardware.
    *   **Fix (Part 13):** Implemented a `multiprocessing.Event` to synchronize the radar and CAN processes, fixing a race condition where the tracker would start before CAN data was available.
    *   **Refactor (Part 12):** Overhauled the logging system to be centralized and more reliable, ensuring all logs are saved correctly to a timestamped directory.

## 10. Testing

A unit test is available to perform a sanity check on the CAN service without requiring any connected hardware.

```bash
python -m unittest tests/test_can_service.py
```
