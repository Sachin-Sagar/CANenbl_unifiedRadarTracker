# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
