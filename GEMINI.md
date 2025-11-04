# GEMINI.md - Project Log & Debugging Journey

## 1. Project Overview

This project, `CANenbl_unifiedRadarTracker`, merges two systems:
1.  A real-time radar tracking application (`radar_tracker`) built on PyQt5 and `QThread`.
2.  A high-performance CAN logging application (`can_logger_app`) built on `multiprocessing`.

The goal is to have the CAN logger run as a background service that **both** logs all decoded CAN signals to a `can_log.json` file and **simultaneously** provides live, interpolated CAN data to the radar tracker for sensor fusion.

## 2. Final System Architecture (Live Mode)

The final architecture consists of two main processes to ensure stability, performance, and cross-platform compatibility (especially on Windows):

1.  **Main/Radar Process (Main Thread + QThread):**
    * Runs the `main.py` script.
    * Creates a `multiprocessing.Manager` and a shared dictionary (`live_data_dict`).
    * Launches the **CAN Process** (`can_logger_app`).
    * Launches the `RadarWorker` in a `QThread` (the `main_live` app).
    * The `RadarWorker` reads from the `live_data_dict`, interpolates the data, and runs the tracking algorithm.

2.  **CAN Process (`multiprocessing.Process`):**
    * This single process is given exclusive control of the CAN hardware.
    * It runs the `can_logger_app.main` function.
    * **CANReader Thread:** A dedicated `threading.Thread` *within this process* is now responsible for the entire lifecycle of the `can.interface.Bus` object (create, use, destroy) to solve Qt threading errors.
    * **Worker Pool:** A pool of sub-processes decodes CAN messages.
    * **LogWriter Thread:** Writes all decoded signals to `can_log.json`.
    * **Live Data Sharing:** The worker pool also writes the latest signal values into the `live_data_dict` provided by the Main Process.

This architecture solves all hardware resource conflicts and Windows-specific threading errors.

## 3. The Debugging Journey (Windows)

Achieving this stable architecture required solving two major, intertwined problems that only appear on Windows.

### Part 1: The Initial Failure

After merging the code, the app failed on Windows with two symptoms:
1.  **Missing `can_log.json`:** The CAN log file was never created or was empty.
2.  **`QObject` Error:** The application would crash on exit with `QObject::~QObject: Timers cannot be stopped from another thread`.

### Part 2: Diagnosis & Solution - The "Unified CAN Process"

* **Diagnosis (Hardware Conflict):** We discovered that two different parts of the code were trying to control the PCAN hardware at the same time:
    1.  The `can_logger_app` process (to write the log file).
    2.  The `LiveCANManager` (started by the radar's `QThread`, to provide live data).
* The PCAN driver only allows **one** process to connect. Whichever process lost this "race" would fail. This was why the `can_log.json` was missing—the logger was losing the race.
* **Solution (The Unified Process):**
    1.  **Eliminate `LiveCANManager`:** We completely removed the `src/can_service/live_can_manager.py` from the `radar_tracker`'s execution path.
    2.  **Promote `can_logger_app`:** We made the `can_logger_app` the *only* process that touches the CAN hardware.
    3.  **Implement Sharing:** We modified `main.py` to create a `multiprocessing.Manager.dict()` and pass it to *both* processes.
    4.  We updated `src/can_logger_app/data_processor.py` to write the decoded signals to this shared dictionary *in addition* to writing them to the log file queue.
    5.  We updated `src/radar_tracker/main_live.py` to read from this shared dictionary instead of the old `LiveCANManager`.

### Part 3: The Stubborn `QObject` Error

After fixing the hardware conflict, the `QObject` error *still* persisted.

* **Diagnosis (Qt Thread Ownership):** The `pcan` backend for `python-can` uses Qt internally. Qt has a strict rule: **A QObject must be created, used, and destroyed all in the same thread.**
* Our code was violating this:
    1.  **Creation:** `can_logger_app/main.py` created the `can.interface.Bus(...)` object in the **Main Thread**.
    2.  **Usage:** `can_logger_app/can_handler.py` called `bus.recv()` in the **CANReader Thread**.
    3.  **Destruction:** The `bus` object was destroyed by the **Main Thread** when the process exited.
* This cross-thread interaction is what caused the "Timers cannot be stopped from another thread" error.

### Part 4: The Final Solution (Thread-Local Bus)

* **The Fix:** We moved the `can.interface.Bus` creation *into* the `CANReader` thread.
    1.  `src/can_logger_app/main.py` was changed to no longer create the `bus` object. It now just passes the `bus_params` (a dictionary) to the `CANReader`.
    2.  It also creates a `threading.Event` (`connection_event`) and waits on it.
    3.  `src/can_logger_app/can_handler.py` was updated. Its `run()` method now creates the `can.interface.Bus` itself.
    4.  If the connection is successful, it calls `connection_event.set()` to tell the main thread to proceed.
    5.  A `finally` block was added to the `run()` method's `try` block to ensure `bus.shutdown()` is called from *within the `CANReader` thread*, satisfying Qt's thread-ownership rules.

### Part 5: Cosmetic Fix (Log Spam)

* **Problem:** The console was spammed with `"EXECUTING ROBUST PARSING SCRIPT"` messages.
* **Cause:** This `print` statement was in the global scope of `src/radar_tracker/hardware/parsing_utils.py`. On Windows, `multiprocessing` re-imports all scripts for each new worker process, causing the `print` to re-run.
* **Solution:** Removed the `print` statements from the global scope of `parsing_utils.py`.


### Part 6: Integrating CAN Data into Radar Tracker

#### The Problem Identified
Even though CAN signals were correctly logged to `can_log.json` and read by the `radar_tracker`'s `RadarWorker`, they were not appearing in the `track_history.json` and consequently not being used by the tracking algorithm.

#### Diagnosis and Initial Solution
We traced the data flow and found that while `main_live.py` was correctly interpolating CAN data into a `can_data_for_frame` dictionary, this dictionary was not being passed to `src/radar_tracker/data_adapter.py`. The `adapt_frame_data_to_fhist` function in `data_adapter.py` was creating the `FHistFrame` object (the primary input for the tracking algorithm) with default zero values for ego-motion fields (e.g., `egoVx`).

To fix this:
1.  **Modified `src/radar_tracker/data_adapter.py`:** The `adapt_frame_data_to_fhist` function was updated to accept `can_signals` as an argument. It now populates `fhist_frame.egoVx` and `fhist_frame.correctedEgoSpeed_mps` using the `CAN_VS_KMH` signal from the provided `can_signals` dictionary (converting from km/h to m/s).
2.  **Modified `src/radar_tracker/main_live.py`:** The call to `adapt_frame_data_to_fhist` was updated to pass the `can_data_for_frame` dictionary. Additionally, the execution order was adjusted so that CAN data interpolation occurred *before* the frame adaptation.
3.  **Refactored `src/radar_tracker/tracking/tracker.py`:** The `process_frame` method was cleaned up. The redundant `can_signals` parameter was removed from its signature and all internal logic related to processing this parameter was deleted, as the necessary ego-motion data is now embedded directly in the `current_frame` (FHistFrame) object.

#### Regression: `AttributeError: 'dict' object has no attribute 'timestamp_ms'`
After the initial fixes, the application crashed with an `AttributeError` when trying to access `frame_data.header.timestamp_ms`. This was a regression introduced by replacing `fhist_frame.timestamp` with `frame_data.header.timestamp_ms` in `main_live.py`, based on an incorrect assumption about the structure of `frame_data.header`.

#### Regression Fix: `KeyError: 'timestamp_ms'`
Correcting the `AttributeError`, we changed the access to `frame_data.header['timestamp_ms']`. However, this led to a `KeyError`, indicating that `timestamp_ms` was not a valid key in the `frame_data.header` dictionary at all.

#### Final Solution for Timestamp Handling
Upon closer inspection, `frame_data.header` (obtained from `read_and_parse_frame`) does not contain a direct timestamp. Instead, the application's timing logic relies on calculating the current frame's timestamp by adding a fixed interval (50 ms) to the `self.tracker.last_timestamp_ms`.

To resolve this:
1.  **Modified `src/radar_tracker/data_adapter.py`:** The `adapt_frame_data_to_fhist` function was updated to accept a pre-calculated `current_timestamp_ms` directly, rather than calculating it internally.
2.  **Modified `src/radar_tracker/main_live.py`:** The `run` method now manually calculates `current_timestamp_ms = self.tracker.last_timestamp_ms + 50.0`. This calculated timestamp is then consistently used for both the `_interpolate_can_data` function and the `adapt_frame_data_to_fhist` function.

This final set of changes ensures that CAN data is correctly integrated, and timestamps are handled robustly, resolving both the data fusion problem and the runtime errors.

## 4. Final Status

The application now runs as expected on Windows (in a dry run):
* It starts and shuts down gracefully without the `QObject` error.
* The `can_logger_app` process correctly reports "unseen" signals (as expected when no hardware is connected) and exits cleanly.
* The `radar_tracker` runs, and the main application exits without errors.

### Part 7: Feature Add - Dynamic CAN Interface Selection

#### The Goal
Previously, the application automatically selected the CAN interface based on the operating system, which limited hardware flexibility. The goal was to allow the user to explicitly choose between different CAN hardware (PEAK and Kvaser) at runtime, ensuring the application works with multiple devices on both Windows and Linux.

#### The Implementation

1.  **Interactive Prompt:**
    *   The OS-based detection in `src/can_logger_app/config.py` was removed entirely.
    *   An interactive prompt was added to the main entrypoint (`main.py`). When starting in Live Mode, the application now asks the user to select between `PEAK (pcan)` or `Kvaser`.

2.  **Dynamic Configuration:**
    *   The user's choice is passed as an argument from the main process to the `can_logger_app` process.
    *   Inside `src/can_logger_app/main.py`, this choice is used to dynamically construct the `bus_params` dictionary with the correct `interface` and `channel` for the selected hardware and host OS.
        *   **PEAK:** Uses the `pcan` backend on Windows and the `socketcan` backend on Linux.
        *   **Kvaser:** Uses the `kvaser` backend (via Kvaser's CANlib) on both Windows and Linux.

3.  **Improved Error Handling:**
    *   The fatal error message block in `src/can_logger_app/main.py` was enhanced. It now provides specific, actionable troubleshooting advice based on the combination of the selected hardware (`peak` or `kvaser`) and the operating system, making it easier for users to diagnose connection issues (e.g., missing drivers, incorrect permissions, or network interface status).

### Part 8: Bugfix - Unnecessary Hardware Check in Playback Mode

#### The Problem
The application would crash on startup if no radar hardware was connected, showing a "No serial ports found" error. This occurred even if the user intended to select the hardware-independent Playback Mode, preventing any use of the application without a radar attached.

#### The Cause
The root cause was that the radar serial port detection logic was located in the global scope of `src/radar_tracker/main_live.py`. When `main.py` imported this module at startup, the hardware check was executed immediately, before the user had a chance to select a mode. If no ports were found, it would call `sys.exit(1)`.

#### The Solution
The hardware check was refactored and moved out of the global scope.
1.  A new function, `select_com_port()`, was created in `src/radar_tracker/main_live.py` to contain all the serial port detection and selection logic.
2.  The `main()` function within `main_live.py` (which is only called when Live Mode is active) was updated to call `select_com_port()` at the beginning of its execution.
3.  This change ensures that the hardware is only checked for when Live Mode is explicitly chosen, allowing Playback Mode to run without any connected hardware as intended.