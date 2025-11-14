# Test Suite Technical Documentation

This document provides a detailed technical description of the test suite for the `CANenbl_unifiedRadarTracker` project, focusing on the architecture and purpose of the key test cases.

## Test Architecture Overview

The test suite is designed to validate the CAN logging and processing components, with a strong emphasis on the dual-pipeline architecture for handling high and low-frequency CAN messages. The tests are organized into several categories:

1.  **Core Logic Simulation**: Tests that simulate the application's core data processing pipelines in a hardware-free environment.
2.  **Live Pipeline Integration**: Tests that validate the integration between the CAN logger and the radar tracker using shared memory.
3.  **Data Integrity**: Tests that check for race conditions and other data corruption issues in the multiprocessing architecture.

All tests are run through the main interactive runner, `tests/tests_main.py`, which centralizes test output into a timestamped directory under `tests/output/`.

## Key Test Scripts

### `test_dual_pipeline_simulation.py`

*   **Purpose:** This is a critical test for debugging the core CAN processing logic. It simulates the entire dual-pipeline system using a pre-recorded log file (`2w_sample.log`) instead of live hardware.
*   **Functionality:**
    *   It reads a BusMaster `.log` file and dispatches messages to either a high-frequency or low-frequency queue based on their ID.
    *   It starts two independent worker processes (`_debug_processing_worker`) to consume these queues, mimicking the live application's architecture.
    *   It verifies that signals are correctly decoded and processed by the appropriate worker.
*   **Key Feature:** The script uses a special `_debug_processing_worker` function that generates detailed, separate log files for each pipeline (e.g., `worker_1_high_freq.log`). These logs are now saved to the run-specific timestamped output directory (e.g., `tests/output/test_run_YYYYMMDD_HHMMSS/`).

### `test_main_app_logic.py`

*   **Purpose:** To perform a hardware-free integration test of the main application's *actual* dual-pipeline architecture, using the production code from `src/can_logger_app`.
*   **Method:**
    1.  The test runner (`tests/lib/main_app_logic_test_runner.py`) imports the `processing_worker` and `utils` directly from `src/can_logger_app`.
    2.  It parses the `2w_sample.log` file and populates the high and low-frequency queues.
    3.  It instantiates the full dual-pipeline system with separate worker pools for each queue.
*   **Current Status:** **FAILING**. The test currently fails because the `logged_signals_set` remains empty, meaning the test harness is not correctly capturing the output from the worker processes. This indicates a bug in the test's implementation, not necessarily in the application code itself.

### `test_live_data_pipeline.py`

*   **Purpose:** To validate the end-to-end data pipeline for live CAN signal integration into the radar tracking algorithm.
*   **Functionality:** This test suite uses a `mock_can_logger_process` to write data into a shared dictionary and a `mock_radar_tracker_process` to read from it, simulating the real-world interaction between the two main components of the application. It verifies that CAN signals are correctly passed, processed, and reflected in the final tracking output.
*   **Key Tests**:
    *   `test_data_integrity_in_live_pipeline`: Ensures data flows correctly without corruption.
    *   `test_startup_race_condition_fix`: Confirms the tracker waits for the CAN logger to be ready.
    *   `test_imu_stuck_flag_ignores_grade`: Verifies the tracker handles the "IMU stuck" flag correctly.

### `test_can_service.py`

*   **Purpose:** To run an integration test on a legacy version of the CAN handling logic (`LiveCANManager` from the deprecated `src/can_service` directory).
*   **Current Status:** **FAILING**. The test fails because the interpolated speed value it calculates (2.0) does not match the expected value (4.0). As this test targets deprecated code, its failure is not a primary concern for current development.

### `tests_main.py`

*   **Purpose:** To act as a centralized, interactive test runner for the entire suite.
*   **Functionality:**
    *   Uses Python's `unittest` library to automatically discover all tests.
    *   Presents an interactive menu to the user to select which test(s) to run.
    *   Creates a unique timestamped directory for each run in `tests/output/` to store all test artifacts, including the console log.
    *   Prints a final summary of test results.

## Debugging Notes

### Missing Signals in Test Data (`test_dual_pipeline_simulation.py`)

The test `test_low_frequency_signals_are_processed` may report that certain signals (e.g., `ETS_VCU_BrakePedal_Act_perc`) are not found. This is expected behavior.

*   **Reason:** The configuration file `master_sigList.txt` lists these signals for monitoring, but the test log file `2w_sample.log` does not contain any CAN messages with those signals.
*   **Conclusion:** The test is functioning correctly by reporting that a configured signal is not present in the provided data. This is a data-configuration mismatch, not a bug in the processing code.
