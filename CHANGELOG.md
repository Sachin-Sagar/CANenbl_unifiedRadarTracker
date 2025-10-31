# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
