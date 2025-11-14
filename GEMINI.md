

Part 35: Project Structure Clarification

This project is the result of merging two separate projects: a radar tracker and a CAN logger. The initial plan was to create a new `src/can_service` directory for the refactored CAN logger code. However, this plan was modified during development.

- **`src/can_logger_app`**: This directory contains the **active, up-to-date** code for the CAN logger application. It is launched as a separate process by the main application.
- **`src/can_service`**: This directory is **deprecated** and contains outdated, unused code from the initial merge plan. It should not be referenced.
- **`merge_plan.md`**: This document describes the original, outdated merge plan and is kept for historical reference only.

All new development and bug fixes related to CAN logging should be applied to the `src/can_logger_app` directory.

Part 33: Feature Add - Ignore Grade/IMU on "IMU Stuck" Flag
The Goal
To improve the robustness of the vehicle ego-motion estimation by ignoring potentially faulty CAN signals. When the vehicle's control unit indicates that its Inertial Measurement Unit (IMU) is malfunctioning (via the `ETS_VCU_imuProc_imuStuck_B` signal), the tracking algorithm should disregard the road grade and other IMU-derived data.

The Implementation
A multi-step process was implemented to ensure the "IMU stuck" flag was respected throughout the data pipeline, from ingestion to final output.

1.  **Data Propagation (`data_adapter.py`):** The `FHistFrame` class, which represents a single snapshot of radar and vehicle data, was updated. A new boolean attribute, `self.imu_stuck`, was added. The `adapt_frame_data_to_fhist` function now reads the `ETS_VCU_imuProc_imuStuck_B` signal from the incoming CAN data and sets this flag on the frame object.

2.  **Conditional Logic (`tracker.py`):** Inside the main `process_frame` method, a new conditional block was added. Before the ego-motion estimator is called, it checks `if current_frame.imu_stuck:`. If the flag is true, two key actions are performed:
    *   The local `can_grade` variable is set to `np.nan` so the estimator will ignore it.
    *   The `current_frame.EstimatedGrade_Est_Deg` attribute is also set to `np.nan`. This was a critical fix to ensure the change was persisted on the frame object itself.

3.  **Final Output (`export_to_json.py`):** A crucial correction was made to the JSON exporter. It was modified to read the road grade value from the top-level `frame.EstimatedGrade_Est_Deg` attribute instead of the raw `frame.can_signals` dictionary. This ensures that the final `track_history.json` file reflects the *processed result* from the tracker (which may be `null`) rather than the original raw input.

The Verification Test
A new, robust test case, `test_imu_stuck_flag_ignores_grade`, was added to `tests/test_cases/test_live_data_pipeline.py`.

*   **Scenario:** The test uses a special mock CAN logger that simulates the `ETS_VCU_imuProc_imuStuck_B` signal flipping from `0` to `1` in the middle of a run.
*   **Initial Failure & Debugging:** The test initially failed due to a race condition between the mock CAN logger and the mock radar tracker. The logger's internal clock ran faster than the tracker's processing loop, causing the "stuck" flag to be set prematurely.
*   **Robust Solution:** The test's assertion logic was rewritten to be independent of perfect timing. Instead of checking a hardcoded frame number, it now:
    1.  Finds the index of the first frame where `roadGrade_Deg` is `null`.
    2.  Asserts that this index is not zero (proving the grade was initially present).
    3.  Asserts that the index is within a reasonable window of when the flag was expected to flip, accounting for timing skew.
    4.  Asserts that the frame immediately *before* the change has a valid, non-null grade.
*   **Result:** With the corrected application logic and the robust test case, the test suite passes, confirming the feature works as designed.

Part 34: Bugfix - Race Condition and Serialization
During a proactive code audit of the live data pipeline, two critical, latent bugs were identified that could lead to data corruption.

The Problem
1.  **Data Loss (Race Condition):** The `data_processor.py` module allowed multiple worker processes to update the `live_data_dict` concurrently. The "read-modify-write" pattern used to append new data to the signal buffers was not atomic. This created a race condition where one process would frequently overwrite the update from another, leading to silent and random loss of CAN signal data before it ever reached the radar tracker.
2.  **Data Corruption (String Serialization):** To work around an earlier issue with `numpy` data types, a fix was implemented to convert all `float` values to `str` before placing them in the shared dictionary. The receiving process (`main_live.py`) would then parse these strings back to floats. This introduced a significant risk: on a system with a different locale (e.g., German), `str(123.45)` can become `"123,45"`, which causes the `float()` parsing to fail with a `ValueError`.

The Solution
A two-part fix was implemented to resolve both issues.

1.  **Fix 1 (Locking):** To solve the race condition, a `multiprocessing.Lock` was created in `src/can_logger_app/main.py` and shared with all `processing_worker` instances. In `src/can_logger_app/data_processor.py`, the entire block that updates the `live_data_dict` was wrapped in a `with lock:` statement. This ensures that only one process can modify the dictionary at a time, guaranteeing atomic updates and preventing data loss.

2.  **Fix 2 (Native Floats):** The risky string conversion was removed entirely.
    - In `src/can_logger_app/data_processor.py`, the code was changed to store native Python `float` types directly in the shared buffer.
    - In `src/radar_tracker/main_live.py`, the corresponding string-parsing logic was removed. The code now directly unpacks the `(float, float)` tuples from the buffer.

This combined solution makes the live data pipeline significantly more robust, efficient, and reliable by eliminating data loss and removing the risk of locale-dependent parsing failures.
