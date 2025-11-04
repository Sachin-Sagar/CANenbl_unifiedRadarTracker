# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.3] - 2025-11-04

### Fixed

- **Centralized Logging:** Refactored the entire logging infrastructure to resolve inconsistencies and bugs.
    - A single, application-wide logger is now defined in `src/radar_tracker/console_logger.py` and used consistently across all modules (`data_adapter.py`, `tracker.py`, `update_and_save_history.py`). This fixes the issue where debug logs were not being displayed or saved.
    - All file-based logging (`console_log.txt` and `console_log.json`) is now managed exclusively by `main.py` to prevent race conditions and ensure logs are correctly saved to the timestamped output directory. This resolves the bug where `console_log.txt` was being overwritten.
- **Indentation Error in `main.py`:** Fixed a critical indentation error that prevented the JSON log from being saved on Linux systems.

### Changed

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
