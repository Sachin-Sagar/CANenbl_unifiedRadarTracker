# Tests Documentation

This document provides an overview of the test suite, its structure, and instructions on how to run the tests and utility scripts.

## Folder Structure

The `tests` directory has been restructured for better organization:

```
tests/
├── tests_main.py           # Main script to discover and run all tests
├── lib/                    # Library and utility scripts used by tests
│   ├── live_can_manager_fixed.py # Fixed version of LiveCANManager for testing
│   └── parse_log_to_json.py    # Utility script to parse log files to JSON
├── test_cases/             # Contains individual test files
│   ├── test_can_log_playback.py
│   └── test_can_service.py
├── test_data/              # Contains data files used by tests
│   ├── 2w_sample.log
│   └── tst_input/
│       ├── master_sigList.txt
│       └── VCU.dbc
└── documentation/          # Test-related documentation
    ├── tests.md            # Detailed documentation of test fixes and changes
    └── tests_readme.md     # This file
```

## How to Run Tests

### Running All Tests

To run the entire test suite, execute the `tests_main.py` script from the project root directory:

```bash
python3 tests/tests_main.py
```

This script will discover and execute all test files (`test_*.py`) located in the `tests/test_cases/` directory. It will report the results to the console.

### Running Individual Tests

You can also run individual test files directly if you only want to execute specific tests. Navigate to the project root and run:

```bash
python3 tests/test_cases/test_can_log_playback.py
python3 tests/test_cases/test_can_service.py
```

## Test Descriptions

### `test_can_log_playback.py`

-   **Purpose**: This is an integration test for the `LiveCANManager`. It verifies that the CAN processing pipeline can correctly read and decode signals from a pre-recorded CAN log file.
-   **Functionality**: It uses `tests/test_data/2w_sample.log` as its input and expects to find and decode signals specified in `tests/test_data/tst_input/master_sigList.txt` using `tests/test_data/tst_input/VCU.dbc`.
-   **Note**: This test uses a fixed version of the `LiveCANManager` (`tests/lib/live_can_manager_fixed.py`) to work around a bug in the main application's `LiveCANManager` implementation.

### `test_can_service.py`

-   **Purpose**: This is a sanity check for the `LiveCANManager`'s ability to process a small, hardcoded set of CAN messages and perform basic signal interpolation.
-   **Functionality**: It mocks a CAN bus to provide a few `can.Message` objects with specific arbitration IDs and data. It then checks if the `LiveCANManager` can process these messages and if an interpolated value can be retrieved.
-   **Note**: Similar to `test_can_log_playback.py`, this test also uses the fixed `LiveCANManager` from `tests/lib/live_can_manager_fixed.py`.

## Utility Script: `parse_log_to_json.py`

This script is not a test, but a utility for processing CAN log data.

-   **Purpose**: To parse a specified CAN log file (`tests/test_data/2w_sample.log`) and extract signals defined in `tests/test_data/tst_input/master_sigList.txt` using the DBC file `tests/test_data/tst_input/VCU.dbc`. The parsed signals are then written to a JSON file.
-   **How to Run**: From the project root directory, execute:
    ```bash
    python3 tests/lib/parse_log_to_json.py
    ```
-   **Output**: The parsed signals will be saved to `tests/parsed_signals.json`.
