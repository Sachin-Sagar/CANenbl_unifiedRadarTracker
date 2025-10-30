# GEMINI.md

## Project Overview

This project is a high-performance, real-time CAN signal logger. It's a command-line tool written in Python that connects to a CAN hardware interface, decodes messages using a DBC file, and saves specific signal data to a timestamped JSON Lines file.

The architecture is designed for high performance and reliability, using a multiprocessing, shared-memory pipeline to log signals from high-speed and low-speed messages simultaneously without data loss.

## Building and Running (PCAN / SocketCAN)

### 1. Prerequisites

* Python 3.10 or newer.
* **Hardware:** A **PCAN-USB** adapter.
* **Drivers (Windows):** Install the [PCAN-Basic drivers](https://www.peak-system.com/PCAN-Basic.239.0.html?&L=1).
* **Drivers (Linux):** Install `can-utils` (`sudo apt install can-utils`).

### 2. Setup

It is recommended to use a virtual environment.

```bash
# Create a new virtual environment
python -m venv .venv

# Activate it (Windows PowerShell)
.venv\Scripts\Activate.ps1

# On macOS/Linux:
source .venv/bin/activate
```

### 3. Install Dependencies

The project dependencies are managed by pyproject.toml.

```bash
# Install the packages listed in pyproject.toml
pip install -e .
```

### 4. Configuration

All hardware settings are now auto-configured in config.py and can_sniffer.py.

    The script detects the OS (Windows or Linux).

    On Windows, it uses the pcan interface.

    On Linux, it uses the socketcan interface with channel "can0".

Place your DBC file and signal list file in the `input/` directory.

### 5. Running the Application

**On Linux (e.g., Raspberry Pi)**

You must bring the CAN interface up manually first.

```bash
sudo ip link set can0 up type can bitrate 500000
python main.py
```

**On Windows**

```bash
python main.py
```

The logger will start and save data to the `output/` folder. To stop, press Ctrl+C.

## The Debugging Journey: From Kvaser Failure to PCAN Success

This project was originally developed for Kvaser hardware, but significant issues were encountered when migrating to a Linux (Raspberry Pi) environment. This document outlines the debugging process that led to a successful hardware migration.

### Part 1: Failure of the Kvaser Proprietary Driver

The initial attempt to run the Kvaser-configured application on a Raspberry Pi failed, even after the Kvaser linuxcan drivers (mhydra v8.50.312) and canlib (v5.50) were installed.

*   **Initial Error:** The application immediately crashed with `FATAL ERROR: Function canIoCtl failed - Error in parameter [Error Code -1]`.
*   **Core Diagnosis:** We ran two key tests:
    *   **Kvaser's `listChannels` Tool:** This C-based example program succeeded, proving the hardware, kernel driver (mhydra), and canlib library were installed correctly.
    *   **Minimal Python Script:** A simple `can.interface.Bus(...)` script failed with the same `canIoCtl` error.
*   **Conclusion:** The problem was not the application code or the drivers themselves, but a low-level incompatibility between the `python-can` (v4.6.1) library's `kvaser` backend and the specific `canlib` version on the Pi.

### Part 2: Successful Migration to PCAN/SocketCAN

With the Kvaser proprietary stack deemed unworkable, we migrated to the standard Linux SocketCAN interface.

*   **Hypothesis 1: Use Kvaser with SocketCAN.**
    *   **Test:** We checked if the standard `kvaser_usb` SocketCAN driver was available.
    *   **Result:** `modprobe: FATAL: Module kvaser_usb not found.` This path was a dead end. The Pi's kernel did not include this driver.
*   **Hypothesis 2: Change hardware to one with known, working SocketCAN drivers.**
    *   **Test:** We checked if the standard driver for PCAN (`peak_usb`) was available.
    *   **Result:** `lsmod | grep peak_usb` succeeded, showing the driver was already loaded in the kernel. This confirmed PCAN was a viable path.
*   **Implementation:** The code was modified to support PCAN.
    *   `config.py` and `can_sniffer.py` were updated to use `platform.system()` to auto-detect the OS.
    *   **Windows:** Uses `CAN_INTERFACE = "pcan"`.
    *   **Linux:** Uses `CAN_INTERFACE = "socketcan"`.
*   **Final Errors & Solutions:**
    *   **Error:** `TypeError: expected str, bytes or os.PathLike object, not int`
        *   **Fix:** Changed `CAN_CHANNEL` in `config.py` from `0` to `"can0"` for the Linux/SocketCAN configuration.
    *   **Error:** `OSError: [Errno 100] Network is down`
        *   **Fix:** Added a mandatory step for Linux users to run `sudo ip link set can0 up type can bitrate 500000` before starting the script.

### Final Conclusion

The migration was 100% successful. The application is now fully functional on both Windows and Raspberry Pi (Linux) using PCAN hardware. The original driver incompatibility was completely bypassed by moving to the stable, kernel-integrated SocketCAN interface (`peak_usb`).

## Development Conventions

*   The project uses a modular structure, with clear separation of concerns between the different components of the pipeline.
*   Configuration is centralized in `config.py`.
*   The `main.py` script orchestrates the entire pipeline.
*   The project uses `multiprocessing` to take advantage of multiple CPU cores.
*   Shared memory is used to efficiently transfer data between processes.
*   The `pyproject.toml` file defines the project dependencies.
*   The code is well-commented, and the `README.md` file provides a good overview of the project.

## Merge Progress

This section tracks the progress of merging the `Read_CAN_RT_strip` and `Unified-radar-tracker` projects.

### Phase 1: Project Scaffolding (Completed)

*   [x] Created `src` directory.
*   [x] Copied `Unified-radar-tracker/src` to `src/radar_tracker`.
*   [x] Copied `Read_CAN_RT_strip` python files to `src/can_logger_app`.
*   [x] Created `src/can_service` and copied essential CAN files.
*   [x] Copied configuration files (`configs`, `config.py`, `input`).
*   [x] Created `__init__.py` files.
*   [x] Created `main.py`.
*   [x] Merged dependencies into `requirements.txt`.

### Phase 2: Refactor can_logger into can_service (Completed)

*   [x] Created `src/can_service/live_can_manager.py`.
*   [x] Modified `src/can_service/data_processor.py` to use an output queue.
*   [x] Implemented the `LiveCANManager` class.

### Phase 3: Integrate can_service into radar_tracker (Completed)

*   [x] **Task 3.1: Add Interpolation Helper**
    *   [x] Add `interp_with_extrap` function to a utility file in `src/radar_tracker/tracking/utils`.
*   [x] **Task 3.2: Modify the RadarWorker (`main_live.py`)**
    *   [x] `__init__`: Import and create `LiveCANManager`.
    *   [x] `run` (start-up): Call `can_manager.start()`.
    *   [x] `run` (main loop):
        *   [x] Get latest CAN data from `can_manager`.
        *   [x] Interpolate CAN data to match radar frame timestamp.
        *   [x] Pass interpolated data to `tracker.process_frame()`.
    *   [x] `stop`: Call `can_manager.stop()`.
    *   [x] Update imports in `main_live.py` to be relative.

### Phase 4: Create Final Entry Point (Completed)

*   [x] **Task 4.1: Write the Root `main.py`**
    *   [x] Add code to set Python Path to include `src`.
    *   [x] Import main components from `radar_tracker`.
    *   [x] Configure application-wide logging.
    *   [x] Launch the application.
*   [x] **Task 4.2: Modify `src/radar_tracker/main.py`**
    *   [x] Use relative imports.
    *   [x] (Optional) Remove `setup_logging()` call.