# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2025-11-07

### Added

- **Dual Pipeline CAN Processing:** Implemented a major architectural enhancement to the `can_logger_app` by introducing a dual-pipeline processing system. This separates the processing of high-frequency (e.g., 10ms) and low-frequency (e.g., 100ms) CAN signals into independent, parallel pipelines. This ensures that high-priority, time-sensitive signals are not delayed by bursts of low-priority messages, significantly improving the real-time reliability and performance of the CAN logger.
    - The `can_handler` now acts as an intelligent dispatcher, sorting incoming messages into high and low-frequency queues.
    - The `main` orchestrator in `can_logger_app` now creates and manages two separate worker pools for decoding, one for each pipeline.

### Fixed

- **`UnboundLocalError` in Tracker:** Resolved a crash in the `radar_tracker` caused by an `UnboundLocalError`. The `delta_t` variable was being used in a debug log message in `src/radar_tracker/tracking/tracker.py` before it was calculated. The fix involved moving the `delta_t` calculation to before the log message.

## [1.2.15] - 2025-11-07

### Fixed

- **CAN Signal Filtering:** Resolved a bug where the CAN logger was processing and logging all signals for a given message ID if at least one signal from that message was in the master signal list. The decoding rule generation in `src/can_logger_app/utils.py` was made more robust to ensure that only signals explicitly listed in the `master_sigList.txt` are ever decoded and logged.

### Changed

- **Enhanced Logging Configuration:**
    - **Enabled Tracking Logs:** Activated detailed, frame-by-frame debug logging for all major tracking components (`DBSCAN`, `RANSAC`, `JPDA`, `IMM Filter`, etc.) by default. This resolves the issue of the `tracking.log` file being empty and provides rich data for debugging the tracking algorithm's behavior.
    - **Refined Log Categorization:** The logging filter for `radar_processing.log` was made more specific. It now exclusively captures logs related to the application's main setup and execution flow for live and playback modes, providing a cleaner log for initialization and high-level processes.

## [1.2.14] - 2025-11-06

### Fixed

- **Inter-Process Communication Deadlock on Non-Linux Systems:** Resolved a critical issue where the radar tracker application would hang indefinitely on non-Linux systems (e.g., Windows) when running in live mode with CAN enabled. The deadlock was caused by an incorrect inter-process communication (IPC) pattern where `main_live` (radar tracker) was launched in a `threading.Thread` while attempting to synchronize with a `multiprocessing.Event` set by a `multiprocessing.Process` (CAN logger). `multiprocessing.Event` objects cannot be reliably shared between `multiprocessing.Process` and `threading.Thread` in this manner.
    - The fix involved modifying `main.py` to remove the `threading.Thread` wrapper around the `main_live` function call in the non-Linux execution block. `main_live` is now called directly in the main process, ensuring correct sharing and synchronization of the `multiprocessing.Event` (`can_logger_ready`) between the CAN logger process and the main process. This allows the radar tracker to correctly receive the "ready" signal from the CAN logger and proceed with data processing.

## [1.2.13] - 2025-11-06

### Fixed

- **CAN Data Corruption in `can_log.json`:** Resolved a critical bug where decoded CAN signal values were constant and incorrect in the final `can_log.json` file. The issue was caused by improper serialization of the complex `can.Message` object when passed between the `can_handler` and `data_processor` processes via a `multiprocessing.Queue`.
    - The fix involved changing the data passed to the queue from a `can.Message` object to a simple, pickle-safe Python dictionary containing only the essential message attributes (`timestamp`, `arbitration_id`, `data`).
    - `can_handler.py` was updated to create this dictionary.
    - `data_processor.py` was updated to expect and process this dictionary, ensuring fresh data is decoded for every message.

## [1.2.12] - 2025-11-06

### Changed

- **CAN Log Summary Display:** The final CAN Data Logging Summary (`[LOGGED]` / `[UNSEEN]` status) is now displayed in the main application's console upon shutdown. Previously, this summary was only available in a separate log file for the `can_logger_app` process. This was achieved by passing the summary data from the child process back to the main process for printing.

## [12.1.11] - 2025-11-06

### Fixed

- **Graceful Shutdown Implementation**: Resolved `ValueError: I/O operation on closed file.`, `BrokenPipeError`, `EOFError`, and `QObject::~QObject: Timers cannot be stopped from another thread` errors by implementing a comprehensive graceful shutdown mechanism across `src/can_logger_app/main.py`, `src/can_logger_app/can_handler.py`, `src/can_logger_app/log_writer.py`, and `src/can_logger_app/data_processor.py`. This ensures all threads and processes terminate cleanly before resources are released.
- **`IndentationError` in `src/can_logger_app/main.py`**: Corrected an `IndentationError` that occurred due to incorrect indentation within the `try...finally` block for console output redirection, and removed duplicated code.
- **CAN Log Data Corruption (Interim Fix)**: Applied an interim fix in `src/can_logger_app/log_writer.py` to explicitly cast the signal `value` to a native Python `float()` before JSON serialization, addressing potential data type corruption.

### Added

- **Shutdown Debugging Messages**: Integrated detailed debug messages into the shutdown sequence of `src/can_logger_app/main.py`, `src/can_logger_app/can_handler.py`, `src/can_logger_app/log_writer.py`, and `src/can_logger_app/data_processor.py` to provide clear console output on the status and order of component termination during shutdown.
- **Comprehensive Console Output Redirection**: Implemented redirection of `sys.stdout` and `sys.stderr` to a timestamped log file in `output/` for `can_logger_app/main.py`, ensuring all console output is captured.
- **Detailed CAN Message Debugging**: Added debug print statements to `src/can_logger_app/can_handler.py` (logging all received CAN messages) and `src/can_logger_app/data_processor.py` (logging raw CAN messages before decoding) to aid in diagnosing constant CAN signal values.

## [1.2.10] - 2025-11-06

### Fixed

- **CAN Logger Configuration on Windows:** Resolved an `AttributeError: 'NoneType' object has no attribute 'DEBUG_PRINTING'` occurring in the `can_logger_app` process on Windows. This was fixed by:
    - Renaming `DEBUG_LOGGING` to `DEBUG_PRINTING` in `src/can_logger_app/config.py` to match its usage.
    - Changing relative imports of `config` and `utils` to absolute imports (`from can_logger_app import config`, `from can_logger_app import utils`) in `src/can_logger_app/main.py` and `src/can_logger_app/utils.py`. This ensures correct module loading in spawned child processes on Windows.

### Added

- **CAN Logger Process Health Checks:** Implemented periodic debug logging in `src/can_logger_app/main.py` to monitor the `CANReader` thread, `LogWriter` thread, and worker processes. These health checks provide visibility into the status of multiprocessing components and are logged to the console and `console_out` files.

## [1.2.9] - 2025-11-06

### Fixed

- **Unnecessary Wait in "No CAN" Mode:** Resolved an issue where the application would unnecessarily wait for the CAN logger to initialize when running in "No CAN" mode. The fix ensures that the `RadarWorker` does not wait for the `can_logger_ready` event when no CAN interface is selected.

## [1.2.8] - 2025-11-06

### Added

- **Categorized Console Logging:** Implemented a new logging system that splits console output into three distinct categories: `can_processing`, `radar_processing`, and `tracking`. These logs are now saved as separate files (`can_processing.log`, `radar_processing.log`, `tracking.log`) within a new `console_out` directory inside the timestamped output folder. This change provides a more organized and debuggable logging structure.

## [1.2.7] - 2025-11-06

### Fixed

- **Threading Error in "No CAN" Mode on Linux:** Resolved a `NameError` that occurred during shutdown when running in "No CAN" mode on a Linux system. The error was caused by an attempt to join a `stop_thread` that was never created. The fix ensures that the thread responsible for checking the hardware-off signal is only initialized and managed when a CAN interface is actively in use.

## [1.2.6] - 2025-11-06

### Fixed

- **can_log.json Data Corruption:** Resolved an issue where the `can_log.json` file contained corrupted data. This was due to a race condition where multiple `data_processor` workers were writing to a shared memory array, leading to mixed and incorrect log entries. The fix involved refactoring the `can_logger_app` to use a direct `multiprocessing.Queue` for log entries, ensuring atomic and uncorrupted data transfer from workers to the `LogWriter`.
- **Centralized Multiprocess Logging:** Implemented a robust logging solution for multiprocessing environments. The main application now uses a `logging.handlers.QueueHandler` and `logging.handlers.QueueListener` to collect logs from all processes, including the `can_logger_app`. All console output, including debug messages from child processes, is now correctly captured and written to `console_log.txt` and `console_log.json`. Debug messages in `data_processor.py` and `log_writer.py` are now controlled by the `DEBUG_LOGGING` flag in `src/can_logger_app/config.py`.

## [1.2.5] - 2025-11-04

### Added

- **'No CAN' Option:** Introduced a 'No CAN' option during CAN interface selection in Live Mode. This allows users to bypass CAN initialization entirely and run the radar tracking algorithm independently, without requiring any CAN hardware or data.

## [1.2.4] - 2025-11-04

### Fixed

- **CAN Data Not Used by Tracking Algorithm:** Resolved an issue where live CAN data (e.g., ego vehicle speed) was not being correctly integrated into the radar tracking algorithm, resulting in `egoVx` being consistently `0.0` in the `track_history.json`. The fix involved:
    - Implementing a `multiprocessing.Event` (`can_logger_ready`) to synchronize the `can_logger_app` and `radar_tracker` processes, ensuring the tracker waits for CAN data to be available before processing frames.
    - Modifying `src/can_logger_app/data_processor.py` to set `can_logger_ready` after the first CAN message is processed and written to the shared dictionary.
    - Updating `src/radar_tracker/main_live.py` to wait for `can_logger_ready` before entering the main tracking loop.
    - Correcting the access method for the `multiprocessing.Manager.dict` in `src/radar_tracker/main_live.py` to ensure a proper deep copy of the shared data, preventing issues with proxy objects.

## [1.2.3] - 2025-11-04

### Fixed

- **Inconsistent Logging in `main_live.py`:** Corrected `main_live.py` to use the centralized application logger, ensuring all debug, info, warning, and error messages are consistently processed and displayed according to the global logging configuration. This resolves the issue where `[INTERPOLATION]` debug messages were not appearing in the console.
- **Centralized Logging:** Refactored the entire logging infrastructure to resolve inconsistencies and bugs.
    - A single, application-wide logger is now defined in `src/radar_tracker/console_logger.py` and used consistently across all modules (`data_adapter.py`, `tracker.py`, `update_and_save_history.py`). This fixes the issue where debug logs were not being displayed or saved.
    - All file-based logging (`console_log.txt` and `console_log.json`) is now managed exclusively by `main.py` to prevent race conditions and ensure logs are correctly saved to the timestamped output directory. This resolves the bug where `console_log.txt` was being overwritten.
- **Indentation Error in `main.py`:** Fixed a critical indentation error that prevented the JSON log from being saved on Linux systems.

### Changed

- **Logging Helper Functions:** The `log_debug` and `log_component_debug` functions in `console_logger.py` were updated to use `logger.debug()` instead of `logger.info()`. This makes their behavior consistent with their names and the new `DEBUG` logging level, improving code clarity and maintainability.
- **Improved Debuggability:** The logging system is now more robust, allowing for easier debugging of data flow issues.

## [1.2.2] - 2025-11-04

### Fixed

- **CAN Signals in Track History:** Resolved an issue where CAN-derived signals (e.g., `canVehSpeed_kmph`, `engagedGear`) were appearing as `null` in `track_history.json`. This was due to a mismatch in signal naming conventions between the `data_adapter.py` and `export_to_json.py` modules, and the `FHistFrame` object not explicitly storing the raw CAN signal values. The fix involved:
    - Updating the `FHistFrame` class to include dedicated attributes for raw CAN signals.
    - Modifying `data_adapter.py` to correctly populate these attributes from the `can_signals` dictionary.
    - Adjusting `export_to_json.py` to read the CAN signal values from the newly added attributes on the `FHistFrame` object.

## [1.2.1] - 2025-11-04

### Fixed

- **Kvaser CAN Interface on Windows:** Resolved `PermissionError: [WinError 5] Access is denied` and `QObject::~QObject: Timers cannot be stopped from another thread` errors when using the Kvaser CAN interface on Windows. This was caused by `multiprocessing` resource conflicts due to premature loading of CAN/Qt-related modules in the main process. The fix involved deferring the import of `can_logger_app.main`, `radar_tracker.main_live`, and `radar_tracker.main_playback` into the `if __name__ == '__main__':` block in `main.py`.

### Changed

- **Documentation Updates:**
    - Updated `GEMINI.md` with a detailed entry (`Part 10`) explaining the diagnosis and solution for the Kvaser Windows `PermissionError`.
    - Updated `README.md` to clarify Kvaser hardware support on Windows, explicitly stating it is now fully supported, and refined hardware recommendations.

## [1.2.0] - 2025-10-31

### Added

- **GPIO-Based Hardware Interaction (Raspberry Pi):** Implemented a comprehensive set of features for running the application on a Raspberry Pi with physical controls.
    - **Switch-Triggered Start:** The application will now wait for a physical switch to be turned ON on a designated GPIO pin before starting the logging and tracking process. This allows for headless operation and control without a keyboard or SSH session.
    - **Switch-OFF to Stop:** The application can be gracefully shut down by turning the physical switch OFF. This provides a convenient way to stop logging and save all data correctly.
    - **Onboard LED Feedback:** The Raspberry Pi's onboard activity LED is used to provide visual feedback to the user:
        - The LED stays **continuously ON** to indicate that the application has successfully started and is actively logging data.
        - The LED turns **OFF** upon shutdown to confirm that the task has been completed and all processes have terminated cleanly.

### Fixed

- **CAN Log Not Saved:** Resolved an issue where the CAN log was not being saved as a JSON file. The `main.py` script now correctly launches the CAN logger in a separate process, ensuring that CAN data is logged to a timestamped JSON Lines file.

## [1.1.0] - 2025-10-31

### Added

- **Automated CAN Interface Setup:** The application now automatically attempts to bring up the `can0` interface on Linux systems by executing `sudo ip link set can0 up type can bitrate 500000`. This removes the need for users to run this command manually before starting the application.
- **Timestamped Output Directories:** All output files (logs, tracking history, etc.) are now stored in a timestamped directory within the `output/` folder for each application run. This helps to organize outputs from different sessions and prevents files from being overwritten.

### Changed

- **Robust Serial Port Detection:** The hardcoded serial port `/dev/ttyACM0` for Linux has been replaced with a dynamic detection mechanism.
    - If no serial ports are found, the application now provides a clear error message and exits gracefully.
    - If a single port is available, it is selected automatically.
    - If multiple ports are available, the user is prompted to choose the correct one from a list.

### Fixed

- **CAN Interface Error Handling:** The application no longer crashes if the CAN interface is already up. It now detects the "Device or resource busy" error, prints a confirmation message, and continues execution.
- **Shutdown `RuntimeError`:** Fixed a race condition that caused a `RuntimeError: wrapped C/C++ object of type QThread has been deleted` during shutdown if the radar sensor failed to initialize. The shutdown sequence is now more robust, ensuring the application closes cleanly in error states.
