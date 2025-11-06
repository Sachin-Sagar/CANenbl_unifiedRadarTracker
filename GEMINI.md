# GEMINI.md - Project Log & Debugging Journey

## 1. Project Overview

This project, `CANenbl_unifiedRadarTracker`, merges two systems:
1.  A real-time radar tracking application (`radar_tracker`) built on PyQt5 and `QThread`.
2.  A high-performance CAN logging application (`can_logger_app`) built on `multiprocessing`.

The goal is to have the CAN logger run as a background service that **both** logs all decoded CAN signals to a `can_log.json` file and **simultaneously** provides live, interpolated CAN data to the radar tracker for sensor fusion.

## 2. Final System Architecture (Live Mode)

The final architecture consists of two main processes to ensure stability, performance, and cross-platform compatibility (especially on Windows):

1.  **Main/Radar Process (Main Thread + QThread):**
    *   Runs the `main.py` script.
    *   Creates a `multiprocessing.Manager` and a shared dictionary (`live_data_dict`).
    *   Launches the **CAN Process** (`can_logger_app`).
    *   Launches the `RadarWorker` in a `QThread` (the `main_live` app).
    *   The `RadarWorker` reads from the `live_data_dict`, interpolates the data, and runs the tracking algorithm.

2.  **CAN Process (`multiprocessing.Process`):**
    *   This single process is given exclusive control of the CAN hardware.
    *   It runs the `can_logger_app.main` function.
    *   **CANReader Thread:** A dedicated `threading.Thread` *within this process* is now responsible for the entire lifecycle of the `can.interface.Bus` object (create, use, destroy) to solve Qt threading errors.
    *   **Worker Pool:** A pool of sub-processes decodes CAN messages.
    *   **LogWriter Thread:** Writes all decoded signals to `can_log.json`.
    *   **Live Data Sharing:** The worker pool also writes the latest signal values into the `live_data_dict` provided by the Main Process.

This architecture solves all hardware resource conflicts and Windows-specific threading errors.

## 3. The Debugging Journey (Windows)

Achieving this stable architecture required solving two major, intertwined problems that only appear on Windows.

### Part 1: The Initial Failure

After merging the code, the app failed on Windows with two symptoms:
1.  **Missing `can_log.json`:** The CAN log file was never created or was empty.
2.  **`QObject` Error:** The application would crash on exit with `QObject::~QObject: Timers cannot be stopped from another thread`.

### Part 2: Diagnosis & Solution - The "Unified CAN Process"

*   **Diagnosis (Hardware Conflict):** We discovered that two different parts of the code were trying to control the PCAN hardware at the same time:
    1.  The `can_logger_app` process (to write the log file).
    2.  The `LiveCANManager` (started by the radar's `QThread`, to provide live data).
*   The PCAN driver only allows **one** process to connect. Whichever process lost this "race" would fail. This was why the `can_log.json` was missing—the logger was losing the race.
*   **Solution (The Unified Process):**
    1.  **Eliminate `LiveCANManager`:** We completely removed the `src/can_service/live_can_manager.py` from the `radar_tracker`'s execution path.
    2.  **Promote `can_logger_app`:** We made the `can_logger_app` the *only* process that touches the CAN hardware.
    3.  **Implement Sharing:** We modified `main.py` to create a `multiprocessing.Manager.dict()` and pass it to *both* processes.
    4.  We updated `src/can_logger_app/data_processor.py` to write the decoded signals to this shared dictionary *in addition* to writing them to the log file queue.
    5.  We updated `src/radar_tracker/main_live.py` to read from this shared dictionary instead of the old `LiveCANManager`.

### Part 3: The Stubborn `QObject` Error

After fixing the hardware conflict, the `QObject` error *still* persisted.

*   **Diagnosis (Qt Thread Ownership):** The `pcan` backend for `python-can` uses Qt internally. Qt has a strict rule: **A QObject must be created, used, and destroyed all in the same thread.**
*   Our code was violating this:
    1.  **Creation:** `can_logger_app/main.py` created the `can.interface.Bus(...)` object in the **Main Thread**.
    2.  **Usage:** `can_logger_app/can_handler.py` called `bus.recv()` in the **CANReader Thread**.
    3.  **Destruction:** The `bus` object was destroyed by the **Main Thread** when the process exited.
*   This cross-thread interaction is what caused the "Timers cannot be stopped from another thread" error.

### Part 4: The Final Solution (Thread-Local Bus)

*   **The Fix:** We moved the `can.interface.Bus` creation *into* the `CANReader` thread.
    1.  `src/can_logger_app/main.py` was changed to no longer create the `bus` object. It now just passes the `bus_params` (a dictionary) to the `CANReader`.
    2.  It also creates a `threading.Event` (`connection_event`) and waits on it.
    3.  `src/can_logger_app/can_handler.py` was updated. Its `run()` method now creates the `can.interface.Bus` itself.
    4.  If the connection is successful, it calls `connection_event.set()` to tell the main thread to proceed.
    5.  A `finally` block was added to the `run()` method's `try` block to ensure `bus.shutdown()` is called from *within the `CANReader` thread*, satisfying Qt's thread-ownership rules.

### Part 5: Cosmetic Fix (Log Spam)

*   **Problem:** The console was spammed with `"EXECUTING ROBUST PARSING SCRIPT"` messages.
*   **Cause:** This `print` statement was in the global scope of `src/radar_tracker/hardware/parsing_utils.py`. On Windows, `multiprocessing` re-imports all scripts for each new worker process, causing the `print` to re-run.
*   **Solution:** Removed the `print` statements from the global scope of `parsing_utils.py`.

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
*   It starts and shuts down gracefully without the `QObject` error.
*   The `can_logger_app` process correctly reports "unseen" signals (as expected when no hardware is connected) and exits cleanly.
*   The `radar_tracker` runs, and the main application exits without errors.

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

### Part 9: Kvaser Interface Failure on Linux

#### The Problem
When selecting the `Kvaser` interface on a Linux system, the application fails to initialize the CAN logger and crashes. The console shows a `NameError` originating from the `python-can` library's Kvaser backend.

NameError: name 'canGetNumberOfChannels' is not defined


This prevents the application from running with Kvaser hardware on Linux, even if the official Kvaser drivers and `canlib` are installed.

#### The Diagnosis
This error indicates a low-level incompatibility between the `python-can` library's `kvaser` backend and the specific version of the proprietary Kvaser `canlib` driver installed on the Linux system. The `ctypes` wrapper used by `python-can` is unable to find the expected `canGetNumberOfChannels` function within the shared library provided by the driver.

This is a recurring issue, previously diagnosed during development on other Linux platforms (e.g., Raspberry Pi), and is not a bug in the application's own code. It stems from the fragility of the interaction between `python-can` and Kvaser's proprietary, non-standard driver stack on Linux.

#### The Solution / Workaround
The most reliable solution is to **use PCAN hardware with the standard SocketCAN interface on Linux**.

1.  **Hardware:** Use a PCAN-USB adapter instead of a Kvaser device.
2.  **Interface Selection:** When prompted by the application, select `PEAK (pcan)`. The application will automatically use the stable `socketcan` backend, which is integrated directly into the Linux kernel.
3.  **Kernel Drivers:** The necessary `peak_usb` kernel module is included in most modern Linux distributions, including Debian/Raspbian, making setup much simpler than with Kvaser's proprietary drivers.

This approach bypasses the problematic proprietary driver layer entirely, providing a stable and well-supported connection to the CAN bus. The application's dynamic interface selection was designed specifically to handle this scenario.

### Part 10: Kvaser PermissionError on Windows

#### The Problem
When selecting the `Kvaser` interface on Windows, the application would crash immediately after starting the CAN logger process. The console would show a `PermissionError: [WinError 5] Access is denied` originating deep within the `multiprocessing.spawn` module, often accompanied by a `QObject::~QObject: Timers cannot be stopped from another thread` warning.

#### The Cause
This issue was a classic problem related to how `multiprocessing` works on Windows.
1.  Windows uses the `spawn` method to create new processes, which starts a clean Python interpreter. The parent process must "pickle" and send all necessary data and resources to the child.
2.  The main entrypoint script (`main.py`) was importing `can_logger_app.main` at the global scope (at the top of the file).
3.  Because the Kvaser backend for `python-can` has dependencies that use Qt, this top-level import caused Qt objects and potentially low-level hardware handles to be loaded into the main parent process *before* the child process was spawned.
4.  These resources are not "picklable" and cannot be transferred to the child process. When `multiprocessing` attempted to duplicate the handles for the new process, it resulted in a `PermissionError` because the parent's handles were not meant to be inherited.

#### The Solution
The fix was to prevent any CAN-related modules from being loaded in the parent process.
1.  The import statements for `can_logger_main`, `main_live`, and `run_playback` were moved from the global scope at the top of `main.py`.
2.  They were placed inside the `if __name__ == '__main__':` block.
3.  This ensures that these modules (and their dependencies, like `python-can` and its backends) are only imported *after* the main script has started, and crucially, they are not loaded in the global scope that gets processed when a child process is spawned. As a result, the `can_logger_process` starts clean, imports the CAN library within its own memory space, and can create and manage its own hardware handles without conflict, resolving the error.

### Part 11: Bugfix - Missing CAN Signals in Final Output

#### The Problem
Despite the CAN data being correctly logged in `can_log.json` and interpolated in the live tracker, the final `track_history.json` file contained `null` values for all CAN-derived fields (e.g., `canVehSpeed_kmph`, `engagedGear`).

#### The Diagnosis
The root cause was a data flow disconnect between the data adaptation step and the final JSON export step:
1.  **Inconsistent Naming:** The `data_adapter.py` module used one set of names for CAN signals when populating the `FHistFrame` object (e.g., calculating `egoVx` from `ETS_VCU_VehSpeed_Act_kmph`), but the `export_to_json.py` module expected different, shorter attribute names (e.g., `VehSpeed_Act_kmph`).
2.  **Missing Raw Data:** The `FHistFrame` object was being populated with the processed `egoVx` (speed in m/s), but it was not storing the original, raw CAN signal values (like speed in km/h, gear status, or torque) that the final JSON schema required.

#### The Solution
A three-part fix was implemented to ensure the raw CAN data is carried through the entire pipeline to the final output:
1.  **Expanded `FHistFrame`:** The `FHistFrame` class in `src/radar_tracker/data_adapter.py` was updated to include new attributes to hold the raw CAN signal values (e.g., `self.ETS_VCU_VehSpeed_Act_kmph = np.nan`).
2.  **Populate Raw Values:** The `adapt_frame_data_to_fhist` function in the same file was modified. In addition to calculating `egoVx`, it now also populates the new raw signal attributes on the `fhist_frame` object directly from the incoming `can_signals` dictionary.
3.  **Corrected JSON Export:** The `create_visualization_data` function in `src/radar_tracker/tracking/export_to_json.py` was updated to read the CAN values from the new, correctly named attributes on the `FHistFrame` object (e.g., `get_attr_safe(frame_data, 'ETS_VCU_VehSpeed_Act_kmph')`).

This change ensures that the final `track_history.json` file accurately reflects the CAN data that was received during the live tracking session.

### Part 12: Logging System Refactor

#### The Problem
Following the data flow fixes, debugging became difficult due to an inconsistent and fragmented logging system. Key symptoms included:
-   `DEBUG` level messages (e.g., `[ADAPTER]`, `[HISTORY]`) were not appearing in the console output, even when debug flags were enabled.
-   The `console_log.txt` file was being created in the root `output/` directory instead of the timestamped session folder, causing it to be overwritten on each run.
-   The `console_log.json` file was not being saved reliably, especially on Linux, due to a race condition and an indentation error in `main.py`.

#### The Diagnosis
1.  **Inconsistent Logger Instances:** Different modules (`data_adapter.py`, `tracker.py`, etc.) were using the standard `import logging`, which created separate logger instances, instead of using the centralized, application-specific logger defined in `console_logger.py`.
2.  **Incorrect Log Levels:** The main application logger was initialized with `INFO` level, which suppressed all `DEBUG` messages.
3.  **Decentralized File I/O:** The `console_logger.py` module was attempting to write log files directly, while `main.py` was also trying to manage log output, leading to conflicts.

#### The Solution
A comprehensive refactoring of the logging system was performed:
1.  **Centralized Logger:** `src/radar_tracker/console_logger.py` was simplified to define a single, application-wide logger instance. All other modules (`data_adapter.py`, `tracker.py`, `update_and_save_history.py`) were modified to import and use this shared logger instance.
2.  **Corrected Log Level:** The centralized logger was set to `logging.DEBUG` to ensure all diagnostic messages are captured.
3.  **Centralized File I/O:** All file-writing responsibility was moved to `main.py`. 
    -   It now creates a `FileHandler` to save a plain text `console_log.txt` to the correct timestamped directory.
    -   The shutdown sequence in `main.py` was fixed to reliably save the in-memory JSON logs to `console_log.json` in the timestamped directory, resolving the indentation error and race condition.
4.  **Consistent Logger Usage in `main_live.py`:** The `src/radar_tracker/main_live.py` module was updated to import and use the centralized `logger` instance from `console_logger.py` instead of the standard `logging` module. This ensures that all messages (including `[INTERPOLATION]` debug messages) from the live radar processing are correctly routed through the application's logging infrastructure and appear in the console and log files.
5.  **Consistent Logging Helper Functions:** The `log_debug` and `log_component_debug` functions in `console_logger.py` were updated to use `logger.debug()` instead of `logger.info()`. This makes their behavior consistent with their names and the new `DEBUG` logging level, improving code clarity and maintainability.

### Part 13: CAN Data Not Used in Tracking Algorithm

#### The Problem
In live mode, although the CAN logger was correctly receiving and logging CAN signals to `can_log.json`, the radar tracking algorithm was not using this data. The `track_history.json` showed `null` or `0.0` for all ego-motion fields (like `egoVx`), and console logs confirmed that the `radar_tracker` process was receiving empty CAN data buffers.

#### The Diagnosis
A detailed review of the console logs revealed a critical timing issue:
1.  The `radar_tracker` process would start, configure the radar sensor, and immediately begin its processing loop.
2.  It would attempt to read from the `shared_live_can_data` dictionary in the very first frame.
3.  However, the `can_logger_app` process, which runs in parallel, was still in its initialization phase (connecting to the CAN bus, starting worker processes). It had not yet received, decoded, or written any data to the shared dictionary.
4.  The result was a race condition: the `radar_tracker` was always too fast and would read an empty dictionary, leading to the observed behavior.

A secondary potential issue was also identified in how the `radar_tracker` read from the shared dictionary. It was using `dict(self.shared_live_can_data)`, which performs a shallow copy and could lead to issues with the underlying `multiprocessing.Proxy` objects.

#### The Solution
A synchronization mechanism was implemented to solve the race condition, and the data access method was made more robust:
1.  **Synchronization with `multiprocessing.Event`:**
    -   A new `multiprocessing.Event` named `can_logger_ready` was created in `main.py`.
    -   This event is passed to both the `can_logger_app` process and the `radar_tracker` process.
2.  **Signaling Readiness:**
    -   The `can_logger_app`'s `data_processor.py` was modified. After a worker process successfully decodes its *first* CAN message and writes it to the `shared_live_can_data` dictionary, it sets the `can_logger_ready` event. This serves as a definitive signal that live data is flowing.
3.  **Waiting for Readiness:**
    -   The `radar_tracker`'s `main_live.py` was updated. Before entering its main processing loop, the `RadarWorker` now calls `can_logger_ready.wait(timeout=10.0)`.
    -   This call blocks the `RadarWorker`, forcing it to wait up to 10 seconds for the signal from the CAN logger. Once the event is set, the worker proceeds, now guaranteed that there is data in the shared dictionary.
4.  **Robust Data Access:**
    -   The data access in `src/radar_tracker/main_live.py` was changed from `dict(self.shared_live_can_data)` to a manual deep copy. This ensures that the `radar_tracker` is working with a clean, local copy of the data and avoids any potential pitfalls with multiprocessing proxy objects.

This solution completely resolves the timing issue, ensuring that the tracking algorithm correctly receives and utilizes live CAN data for ego-motion compensation.

### Part 14: Feature Add - "No CAN" Mode

#### The Goal
To provide users with the flexibility to run the live tracking application using only the radar sensor, without requiring any CAN hardware to be connected. This is useful for testing the radar and tracking algorithms independently.

#### The Implementation
1.  **Modified `main.py`:**
    *   The CAN interface selection prompt was updated to include a "No CAN" option.
    *   If the user selects this option, the `can_logger_process` is not started.
    *   The `main_live` function is called with `None` for the `shared_live_can_data` and `can_logger_ready` arguments.
2.  **No Changes to `radar_tracker`:**
    *   The `RadarWorker` in `src/radar_tracker/main_live.py` was already designed to handle cases where CAN data is not available. If the `shared_live_can_data` object is `None`, it simply skips the CAN interpolation step, and the vehicle's ego-motion (`egoVx`) defaults to zero. This existing robustness meant no further changes were needed in the radar tracker itself.

### Part 15: Bugfix - Torque Data Corruption and Algorithm Integration

#### The Problem
A critical bug was identified where the `ETS_MOT_ShaftTorque_Est_Nm` signal was being corrupted when passed from the `can_logger_app` process to the `radar_tracker` process. A value like `9.36` would appear as `-303728010253.7477`. Furthermore, even if the value were correct, the tracking algorithm was hardcoded to ignore it and use `np.nan` instead. The resulting calculated acceleration was also not being saved.

#### The Diagnosis
1.  **Data Corruption:** The `can_logger_app/data_processor.py` was calculating the `physical_value` as a `numpy.float64`. This non-standard type was being corrupted by the `multiprocessing.Manager.dict` when sent between processes.
2.  **Algorithm Usage:** `src/radar_tracker/tracking/tracker.py` was ignoring the CAN torque value from the `current_frame` and hardcoding `can_torque = np.nan`, which was then passed to the ego-motion estimator.
3.  **Data Logging:** The `tracker.py` file never saved the `ax_dynamics` (calculated acceleration) back to the `current_frame`, so it was always `null` in the final `track_history.json`.

#### The Solution (A 3-part fix)
1.  **Fix Corruption:** In `src/can_logger_app/data_processor.py`, the `physical_value` is now explicitly cast to a native Python `float()` using `physical_value = float(...)` before being put into the shared dictionary. This prevents the multiprocessing corruption.
2.  **Fix Usage:** In `src/radar_tracker/tracking/tracker.py`, the hardcoded `can_torque = np.nan` and `can_gear = np.nan` lines were removed. The code now correctly reads these values from the `current_frame` object: `can_torque = current_frame.ETS_MOT_ShaftTorque_Est_Nm`.
3.  **Fix Logging:** In `src/radar_tracker/tracking/tracker.py`, a new line was added after the `estimate_ego_motion` call to save the result: `current_frame.estimatedAcceleration_mps2 = ax_dynamics`. Finally, `src/radar_tracker/tracking/export_to_json.py` was updated to map the correct attribute names (e.g., `ETS_MOT_ShaftTorque_Est_Nm`) to the final JSON fields (e.g., `shaftTorque_Nm`).

### Part 16: Feature Add - Road Grade Integration

#### The Goal
To fully implement the vehicle dynamics model by piping the `EstimatedGrade_Est_Deg` signal from the CAN bus all the way to the ego-motion estimator and into the final JSON log.

#### The Implementation
1.  **`src/radar_tracker/data_adapter.py`:** The `FHistFrame` class was updated to include `self.EstimatedGrade_Est_Deg = np.nan`. The `adapt_frame_data_to_fhist` function now populates this attribute from the `can_signals` dictionary.
2.  **`src/radar_tracker/tracking/tracker.py`:** The `process_frame` method now reads the grade from the frame object (`can_grade = current_frame.EstimatedGrade_Est_Deg`) and passes it to the `estimate_ego_motion` function.
3.  **`src/radar_tracker/tracking/export_to_json.py`:** The `create_visualization_data` function was updated to map the `EstimatedGrade_Est_Deg` attribute to the `roadGrade_Deg` field in the final JSON.

### Part 17: Bugfix - CAN Data Corruption and Null Acceleration

#### The Problem
A persistent and multifaceted bug was causing two main issues in the final `track_history.json` output:
1.  **Data Corruption:** CAN signal values (e.g., `canVehSpeed_kmph`, `shaftTorque_Nm`) were appearing as massive, incorrect negative numbers.
2.  **Null Acceleration:** The `estimatedAcceleration_mps2` field was always `null`.

#### The Diagnosis
A deep dive into the data pipeline revealed two distinct root causes:
1.  **Data Corruption:** The previous fix (Part 15) had corrected the data type for the CAN signal's *value* (`physical_value`) but not its *timestamp*. The `msg.timestamp`, which was a `numpy.float64`, was still being corrupted by the `multiprocessing.Manager.dict` when the data was passed from the `can_logger_app` to the `radar_tracker` process.
2.  **Null Acceleration:** The `estimate_ego_motion` function was calculating the vehicle's acceleration and using it as an *input* to its internal Extended Kalman Filter (EKF). However, the function was returning this initial input value instead of the final, corrected acceleration value from the EKF's updated state. This meant the logged value did not reflect the result of the filtering process.

#### The Solution
A two-part fix was implemented to resolve both issues:
1.  **Fix Data Corruption:** In `src/can_logger_app/data_processor.py`, the fix was extended. Now, both the CAN signal's `physical_value` and its `msg.timestamp` are explicitly cast to a native Python `float()` before being placed in the shared dictionary. This completely eliminates the data type mismatch and prevents inter-process corruption for all CAN signals.
2.  **Fix Null Acceleration:** In `src/radar_tracker/tracking/algorithms/estimate_ego_motion.py`, the function's return statement was modified. It now returns the final, corrected acceleration value (`updated_kf_state['x'][2, 0]`) from the EKF's state, rather than the initial input value. This ensures the most accurate estimate for acceleration is propagated to the `tracker` and saved in the final log.

### Part 18: Final Bugfix - The Data Corruption Strikes Back

#### The Problem
Even after fixing the data transfer between processes (Part 17), the CAN signal values in the final `track_history.json` were *still* showing signs of corruption.

#### The Diagnosis
The investigation revealed that the corruption was being re-introduced *inside* the `radar_tracker` process. The data was arriving from the `can_logger_app` as clean, standard Python floats. However, the `_interpolate_can_data` method in `src/radar_tracker/main_live.py` uses `numpy.interp` to estimate the CAN signal's value at the precise radar frame timestamp. This interpolation function returns a `numpy.float64` data type.

This non-standard float was then passed through the rest of the tracking pipeline, where it once again caused corruption before being written to the final JSON file. The root cause was the same (a non-native float type), but it was occurring at a different stage.

#### The Solution
The final fix was applied in `src/radar_tracker/main_live.py`. Immediately after the value is calculated by the interpolation function, it is explicitly cast to a native Python `float()`.

This ensures that from the moment the CAN data is interpolated, it remains a standard data type throughout the entire internal pipeline, from data adaptation to tracking to final export. This definitively solves the persistent data corruption issue.

### Part 19: Bugfix - can_log.json Data Corruption

#### The Problem
The `can_log.json` file, which is supposed to be a raw log of all decoded CAN signals, was found to contain corrupted data. The numerical `value` field for signals was appearing as a garbled or incorrect number.

#### The Diagnosis
The root cause was traced to the `can_logger_app/log_writer.py` module. The `data_processor.py` worker correctly decodes the CAN message and packs the physical value into a shared memory array using `struct.pack`. This packing process creates a C-style `double` data type. The `log_writer.py` thread then reads this `double` from the shared memory but was writing it directly into the JSON file without converting it to a standard Python data type. The `json.dumps()` function does not handle C-style doubles correctly, leading to the data corruption in the output file.

#### The Solution
The fix was implemented in `src/can_logger_app/log_writer.py`. Before writing the log entry to the JSON file, the `value` read from the shared memory is now explicitly cast to a native Python `float()` using `float(value)`. This ensures that the `json.dumps()` function receives a standard data type it can serialize correctly, resolving the corruption in the `can_log.json` file.
