# Test Suite Documentation

This document describes the test suite for the `CANenbl_unifiedRadarTracker` project. The primary purpose of these tests is to validate the functionality and performance of the CAN logging and processing components, with a special focus on the dual-pipeline architecture.

## Test Scripts

The main test scripts are located in the `tests/test_cases/` directory.

### `test_dual_pipeline_simulation.py`

*   **Purpose:** This is the most critical test for debugging the core CAN processing logic. It simulates the entire dual-pipeline system using a pre-recorded log file (`2w_sample.log`) instead of live hardware.
*   **Functionality:**
    *   It reads a BusMaster `.log` file.
    *   It acts as a dispatcher, sending CAN messages to either a high-frequency or low-frequency queue based on their message ID.
    *   It starts two independent worker processes to consume these queues, mimicking the live application's architecture.
    *   It verifies that the signals listed in `master_sigList.txt` are correctly decoded and processed by the appropriate worker.
*   **Key Feature:** The script uses a special `_debug_processing_worker` function that generates detailed, separate log files for each pipeline (`worker_1_high_freq.log` and `worker_2_low_freq.log`). This allows for isolated analysis of each worker's behavior.

### `test_can_service.py`

*   **Purpose:** To run an integration test on an alternative or legacy version of the CAN handling logic, specifically the `LiveCANManager`.
*   **Functionality:**
    *   It uses mocks to create a virtual CAN bus that produces predictable messages.
    *   It starts the `LiveCANManager` and allows it to process the mock messages.
    *   It then verifies that the signal interpolation logic produces the correct value.

### `test_can_log_playback.py`

*   **Purpose:** This script is a utility module rather than a standalone test. Its main purpose is to provide a reliable way to parse CAN log files.
*   **Functionality:** It contains the `parse_busmaster_log` function, which reads a raw `.log` file and converts each line into a structured `can.Message` object. This utility is used by `test_dual_pipeline_simulation.py` to feed the simulation.

### `tests_main.py`

*   **Purpose:** To act as a centralized test runner for the entire suite.
*   **Functionality:** It uses Python's built-in `unittest` library to automatically discover and execute all test files matching the pattern `test_*.py` within the `test_cases` directory.

## Verifying the Dual-Pipeline Logic

A critical bug was identified where the main application was unable to log low-frequency (100ms) signals, while high-frequency (10ms) signals were logged correctly. The initial investigation confirmed the dual-pipeline code in `src/can_logger_app` appeared logically correct, and the issue was traced to a missing `master_sigList.txt` file in the `input/` directory.

To confirm this fix without requiring live hardware, a temporary test script (`test_main_app_logic.py`) was created.

*   **Purpose:** To perform a hardware-free integration test of the main application's *actual* dual-pipeline architecture.
*   **Method:**
    1.  The test imported the `CANReader`, `processing_worker`, and `utils` directly from the `src/can_logger_app` module.
    2.  It mocked the `can.interface.Bus` to play back messages from the `2w_sample.log` file.
    3.  It instantiated the full dual-pipeline system: a `CANReader` dispatcher thread, a high-frequency queue and worker pool, and a low-frequency queue and worker pool.
    4.  Each worker pool was given its correctly segregated list of signals to monitor, exactly as in the main application.
*   **Result:** The test **passed**. It successfully logged both a known high-frequency signal (`ETS_MOT_ShaftTorque_Est_Nm`) and a known low-frequency signal (`ETS_VCU_VehSpeed_Act_kmph`).
*   **Conclusion:** This test definitively proved that the root cause of the missing 100ms signals was the absent `master_sigList.txt` file. With the input file present, the main application's core logic for segregating and processing high and low-frequency signals works as designed. The temporary test was subsequently removed.


## Worker Task Breakdown (`test_dual_pipeline_simulation.py`)

The `test_dual_pipeline_simulation.py` script creates two specialized worker processes.

### Worker 1: High-Frequency Pipeline

*   **Input Queue:** `high_freq_raw_queue`
*   **Messages:** Receives messages with IDs corresponding to a **10ms** cycle time.
*   **Tasks:**
    1.  Pulls a raw CAN message from its dedicated queue.
    2.  Decodes the message using the `VCU.dbc` file.
    3.  Checks the decoded signals against the `high_freq_monitored_signals` set.
    4.  If a signal is in the monitored set, it puts a log entry into the shared `log_queue`.
*   **Log File:** `tests/test_data/worker_1_high_freq.log`

### Worker 2: Low-Frequency Pipeline

*   **Input Queue:** `low_freq_raw_queue`
*   **Messages:** Receives messages with IDs corresponding to a **100ms** cycle time.
*   **Tasks:**
    1.  Pulls a raw CAN message from its dedicated queue.
    2.  Performs the same decoding process as the high-frequency worker.
    3.  Compares the decoded signals against its unique list of low-frequency signals.
    4.  If a match is found, it puts the data into the shared `log_queue`.
*   **Log File:** `tests/test_data/worker_2_low_freq.log`

## Debugging Notes

### Missing Signals in Test Data

During debugging, it was discovered that the test `test_low_frequency_signals_are_processed` reports a warning that the signal `ETS_VCU_BrakePedal_Act_perc` is not found. This is expected behavior with the current test data.

*   **Reason:** The configuration file `master_sigList.txt` lists `ETS_VCU_BrakePedal_Act_perc` as a signal to be monitored. However, the test log file `2w_sample.log` does not contain any CAN messages that include this specific signal.
*   **Conclusion:** The test is functioning correctly. It is accurately reporting that a configured signal is not present in the provided data. This is a data-configuration mismatch, not a bug in the processing code.
