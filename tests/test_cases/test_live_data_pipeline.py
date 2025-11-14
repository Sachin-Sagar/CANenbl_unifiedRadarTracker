import unittest
import multiprocessing
import time
import json
import os
from datetime import datetime
import numpy as np
import cantools
import struct

# Assuming the script is run from the project root
import sys
sys.path.append(os.getcwd())

from src.can_logger_app import config as can_config
from src.can_logger_app import utils as can_utils
from src.radar_tracker.data_adapter import adapt_frame_data_to_fhist
from src.radar_tracker.tracking.tracker import RadarTracker
from src.radar_tracker.tracking.parameters import define_parameters
from src.radar_tracker.tracking.update_and_save_history import update_and_save_history
from src.radar_tracker.console_logger import logger as radar_logger # Use a distinct logger name

# Suppress console logger output during tests
radar_logger.propagate = False
radar_logger.handlers = []

# --- Mock CAN Logger Process ---
def mock_can_logger_process(shared_dict, ready_event, shutdown_flag, output_dir, expected_values):
    """
    Simulates the CAN logger application by periodically writing known values
    to the shared dictionary. This avoids parsing a log file and ensures the
    radar process gets consistent data.
    """
    print(f"[CAN Mock] Starting, providing constant data.")
    
    # Temporarily remove stdout/stderr redirection for debugging
    # original_stdout = sys.stdout
    # original_stderr = sys.stderr
    
    # process_log_filepath = os.path.join(output_dir, f"can_mock_console_{os.getpid()}.log")
    # log_file_handle = open(process_log_filepath, 'a', buffering=1) # Line-buffered
    # sys.stdout = log_file_handle
    # sys.stderr = log_file_handle
    # print(f"[CAN Mock] Console output redirected to: {process_log_filepath}")

    try:
        start_time = time.time()
        
        # Set the ready event immediately
        ready_event.set()
        print("[CAN Mock] Ready event set.")

        while not shutdown_flag.is_set():
            current_time = time.time() - start_time
            
            # Update the shared dictionary with the expected values
            shared_dict['ETS_VCU_VehSpeed_Act_kmph'] = (expected_values['speed'], current_time)
            shared_dict['ETS_MOT_ShaftTorque_Est_Nm'] = (expected_values['torque'], current_time)
            shared_dict['EstimatedGrade_Est_Deg'] = (expected_values['grade'], current_time)
            
            time.sleep(0.01) # Update every 10ms

        print("[CAN Mock] Shutdown flag set, exiting.")
    except Exception as e:
        print(f"[CAN Mock] Fatal error: {e}")
    # finally:
        # print("[CAN Mock] Shutting down.")
        # log_file_handle.close()
        # sys.stdout = original_stdout
        # sys.stderr = original_stderr

def mock_can_logger_delayed_start(shared_dict, ready_event, shutdown_flag, output_dir, expected_values):
    """
    A mock CAN logger that intentionally waits before sending any data.
    This is used to test the startup race condition fix.
    """
    print("[CAN Mock Delayed] Starting. Will wait 200ms before sending any data.")
    time.sleep(0.2)
    print("[CAN Mock Delayed] Delay finished. Sending initial data and setting ready event.")

    # The real data processor would set the event after all critical signals are present.
    # Here, we simulate that by setting it after we populate the dict for the first time.
    current_time = time.time()
    shared_dict['ETS_VCU_VehSpeed_Act_kmph'] = (expected_values['speed'], current_time)
    shared_dict['ETS_MOT_ShaftTorque_Est_Nm'] = (expected_values['torque'], current_time)
    shared_dict['EstimatedGrade_Est_Deg'] = (expected_values['grade'], current_time)
    
    # This simulates the real logic where the event is set only after data is available.
    ready_event.set()
    print("[CAN Mock Delayed] Ready event set.")

    # Now, run the continuous loop
    while not shutdown_flag.is_set():
        current_time = time.time()
        shared_dict['ETS_VCU_VehSpeed_Act_kmph'] = (expected_values['speed'], current_time)
        shared_dict['ETS_MOT_ShaftTorque_Est_Nm'] = (expected_values['torque'], current_time)
        shared_dict['EstimatedGrade_Est_Deg'] = (expected_values['grade'], current_time)
        time.sleep(0.01)

    print("[CAN Mock Delayed] Shutdown flag set, exiting.")


def mock_can_logger_numpy_process(shared_dict, ready_event, shutdown_flag, output_dir, expected_values):
    """
    Simulates the CAN logger, but intentionally provides numpy.float64 types
    to test for inter-process data corruption.
    """
    print(f"[CAN Mock Numpy] Starting, providing numpy.float64 data.")
    try:
        start_time = time.time()
        ready_event.set()
        print("[CAN Mock Numpy] Ready event set.")

        while not shutdown_flag.is_set():
            current_time = time.time() - start_time
            
            # Intentionally use numpy.float64 to test the corruption fix
            shared_dict['ETS_VCU_VehSpeed_Act_kmph'] = (np.float64(expected_values['speed']), current_time)
            shared_dict['ETS_MOT_ShaftTorque_Est_Nm'] = (np.float64(expected_values['torque']), current_time)
            shared_dict['EstimatedGrade_Est_Deg'] = (np.float64(expected_values['grade']), current_time)
            
            time.sleep(0.01)

        print("[CAN Mock Numpy] Shutdown flag set, exiting.")
    except Exception as e:
        print(f"[CAN Mock Numpy] Fatal error: {e}")


def mock_can_logger_imu_stuck_scenario(shared_dict, ready_event, shutdown_flag, output_dir, expected_values, flip_frame):
    """
    Simulates a scenario where the IMU 'stuck' flag flips mid-run.
    """
    print(f"[CAN Mock IMU Stuck] Starting. IMU stuck flag will flip at frame {flip_frame}.")
    try:
        start_time = time.time()
        ready_event.set()
        # We need to simulate frame progression. Since this process runs faster than the
        # radar process, we'll use a simple time-based progression.
        # The radar runs at ~20 FPS (50ms interval).
        
        while not shutdown_flag.is_set():
            current_time = time.time()
            elapsed_time = current_time - start_time
            frame_counter = int(elapsed_time / 0.05) # Estimate current frame index

            imu_stuck_flag = 1 if frame_counter >= flip_frame else 0

            shared_dict['ETS_VCU_VehSpeed_Act_kmph'] = (expected_values['speed'], current_time)
            shared_dict['ETS_MOT_ShaftTorque_Est_Nm'] = (expected_values['torque'], current_time)
            shared_dict['EstimatedGrade_Est_Deg'] = (expected_values['grade'], current_time)
            shared_dict['ETS_VCU_imuProc_imuStuck_B'] = (imu_stuck_flag, current_time)
            
            # Log the changeover
            if frame_counter == flip_frame:
                print(f"[CAN Mock IMU Stuck] Frame {frame_counter}, IMU Stuck Flag flipped to: {imu_stuck_flag}")

            time.sleep(0.01) # Update faster than the radar consumes

        print("[CAN Mock IMU Stuck] Shutdown flag set, exiting.")
    except Exception as e:
        print(f"[CAN Mock IMU Stuck] Fatal error: {e}")


# --- Mock Radar Tracker Process ---
def mock_radar_tracker_process(shared_dict, ready_event, shutdown_flag, output_dir, num_frames, radar_log_path):
    """
    Simulates the radar tracker application, reading frames from a radar log file
    and processing them with CAN data from the shared dictionary.
    """
    print(f"[Radar Mock] Starting, processing {num_frames} frames from {radar_log_path}.")

    # Temporarily remove stdout/stderr redirection for debugging
    # ... (rest of the redirection code is already commented out)

    try:
        params_tracker = define_parameters()
        # Modify lifecycle params for faster track confirmation in test
        params_tracker['lifecycle_params']['confirmation_M'] = 2
        params_tracker['lifecycle_params']['confirmation_N'] = 3
        print(f"[Radar Mock] Track confirmation parameters set to M=2, N=3.")

        tracker = RadarTracker(params_tracker)
        fhist_history = []

        # Load radar data from the specified log file
        with open(radar_log_path, 'r') as f:
            radar_frames = json.load(f)

        print("[Radar Mock] Waiting for CAN logger to be ready...")
        ready = ready_event.wait(timeout=5.0)
        if not ready:
            print("[Radar Mock] Timed out waiting for CAN logger.")
            return
        else:
            print("[Radar Mock] CAN logger is ready. Starting tracking loop.")

        start_time = time.time()
        for frame_idx, frame_log_data in enumerate(radar_frames):
            if frame_idx >= num_frames or shutdown_flag.is_set():
                print("[Radar Mock] Reached frame limit or shutdown flag set, exiting.")
                break

            time.sleep(0.05) # Simulate 50ms frame interval

            current_timestamp_ms = (time.time() - start_time) * 1000.0

            # Create a FrameData-like object from the log data
            class LoggedFrameData:
                def __init__(self, log_data):
                    # The log format might be a list of dicts, let's be careful
                    header_data = log_data.get('header', {})
                    self.header = self.Header(header_data.get('timestamp_ms', current_timestamp_ms), header_data.get('frame_idx', frame_idx))
                    
                    # The point cloud in the log is likely a list of lists, convert to numpy array
                    point_cloud_list = log_data.get('point_cloud', [])
                    if point_cloud_list:
                        self.point_cloud = np.array(point_cloud_list)
                        self.num_points = self.point_cloud.shape[1] if self.point_cloud.ndim > 1 else 0
                    else:
                        self.point_cloud = np.empty((5, 0))
                        self.num_points = 0
                    
                    self.points = [] # This attribute is not used by the adapter

                class Header:
                    def __init__(self, timestamp_ms, frame_idx):
                        self.timestamp_ms = timestamp_ms
                        self.frame_idx = frame_idx

            frame_data = LoggedFrameData(frame_log_data)

            # Get CAN data from shared dictionary
            can_data_for_frame = {}
            if shared_dict:
                # Create a clean copy of the shared data for this frame
                temp_can_data = dict(shared_dict)
                for signal_name, value_tuple in temp_can_data.items():
                    if value_tuple and isinstance(value_tuple, (list, tuple)) and len(value_tuple) > 0:
                        # The mock loggers store data as (value, timestamp)
                        can_data_for_frame[signal_name] = float(value_tuple[0])

            fhist_frame = adapt_frame_data_to_fhist(frame_data, current_timestamp_ms, can_signals=can_data_for_frame)
            
            updated_tracks, processed_frame = tracker.process_frame(fhist_frame)
            fhist_history.append(processed_frame)
            
            # --- DEBUG LOGGING FOR TRACKS ---
            if frame_idx % 5 == 0: # Log every 5 frames
                print(f"[Radar Mock] --- Frame {frame_idx} Track Status ---")
                if not tracker.all_tracks:
                    print("[Radar Mock] No active tracks.")
                for track in tracker.all_tracks:
                    track_id = track.get('id', 'N/A')
                    is_confirmed = track.get('isConfirmed', False)
                    history_len = len(track.get('historyLog', []))
                    print(f"[Radar Mock] Track ID: {track_id}, Confirmed: {is_confirmed}, History Length: {history_len}")
                print(f"[Radar Mock] ----------------------------------")
            # --- END DEBUG LOGGING ---
            
            if frame_idx % 10 == 0:
                speed_val = can_data_for_frame.get('ETS_VCU_VehSpeed_Act_kmph', 'N/A')
                speed_str = f"{speed_val:.2f}" if isinstance(speed_val, float) else speed_val
                ego_vx_val = processed_frame.egoVx if hasattr(processed_frame, 'egoVx') else 'N/A'
                accel_val = processed_frame.estimatedAcceleration_mps2 if hasattr(processed_frame, 'estimatedAcceleration_mps2') else 'N/A'
                print(f"[Radar Mock] Processed frame {frame_idx}. CAN speed: {speed_str} kmph, egoVx: {ego_vx_val:.2f} m/s, Accel: {accel_val:.2f} m/s^2")
                print(f"[Radar Mock] Number of active tracks: {len(tracker.all_tracks)}")



        # Save tracking history
        if fhist_history:
            if tracker.all_tracks:
                print(f"[Radar Mock] Inspecting first track before saving. ID: {tracker.all_tracks[0].get('id')}")
                print(f"[Radar Mock] First track historyLog length: {len(tracker.all_tracks[0].get('historyLog', []))}")

            filename = os.path.join(output_dir, "track_history.json")
            print(f"[Radar Mock] Attempting to save track history to: {filename}")
            update_and_save_history(
                tracker.all_tracks,
                fhist_history,
                filename,
                params=tracker.params
            )
            print(f"[Radar Mock] Track history saved to {filename}")
        else:
            print("[Radar Mock] No frames processed, no history to save.")

    except Exception as e:
        import traceback
        print(f"[Radar Mock] Fatal error: {e}\n{traceback.format_exc()}")
    finally:
        shutdown_flag.set() # Signal CAN logger to shut down
        print("[Radar Mock] Shutting down.")
        # log_file_handle.close()
        # sys.stdout = original_stdout
        # sys.stderr = original_stderr


class TestLiveDataPipeline(unittest.TestCase):

    def setUp(self):
        """Set up for the test by creating a unique output directory within the run's output folder."""
        base_output_dir = os.environ.get('TEST_RUN_OUTPUT_DIR')
        if not base_output_dir:
            # Fallback for running this test file directly
            base_output_dir = os.path.join('tests', 'output', 'live_pipeline_fallback')
            os.makedirs(base_output_dir, exist_ok=True)

        # Create a unique directory for this specific test case to avoid file collisions
        self.test_output_dir = os.path.join(base_output_dir, f"{self.id()}_{time.strftime('%H%M%S')}")
        os.makedirs(self.test_output_dir, exist_ok=True)

    def tearDown(self):
        """Clean up the unique output directory created for the test."""
        # This method is called after each test.
        # We can choose to keep the directory if the test failed.
        # For now, we will remove it unconditionally to keep the output clean.
        if hasattr(self, 'test_output_dir') and os.path.exists(self.test_output_dir):
            import shutil
            shutil.rmtree(self.test_output_dir)

    def _run_test_in_subprocess(self, test_name):
        """Helper function to run a specific test from the runner script."""
        import subprocess

        runner_script_path = os.path.join(os.path.dirname(__file__), '..', 'lib', 'live_data_pipeline_test_runner.py')
        self.assertTrue(os.path.exists(runner_script_path), f"Test runner script not found at {runner_script_path}")

        try:
            result = subprocess.run(
                [sys.executable, runner_script_path, f'--test={test_name}', f'--output_dir={self.test_output_dir}'],
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            print(f"\n--- Subprocess Output for {test_name} ---")
            print(result.stdout)
            if result.stderr:
                print(f"--- Subprocess Stderr for {test_name} ---")
                print(result.stderr)
            print("-------------------------------------------\n")
        except subprocess.CalledProcessError as e:
            self.fail(
                f"The isolated test '{test_name}' failed with exit code {e.returncode}.\n"
                f"--- STDOUT ---\n{e.stdout}\n"
                f"--- STDERR ---\n{e.stderr}"
            )
        except subprocess.TimeoutExpired as e:
            self.fail(
                f"The isolated test '{test_name}' timed out.\n"
                f"--- STDOUT ---\n{e.stdout}\n"
                f"--- STDERR ---\n{e.stderr}"
            )

    def test_data_integrity_in_live_pipeline(self):
        """Runs the data integrity test in an isolated process."""
        self._run_test_in_subprocess('data_integrity')

    def test_startup_race_condition_fix(self):
        """Runs the startup race condition test in an isolated process."""
        self._run_test_in_subprocess('startup_race')

    def test_numpy_float64_corruption_fix(self):
        """Runs the numpy float64 corruption test in an isolated process."""
        self._run_test_in_subprocess('numpy_corruption')

    def test_imu_stuck_flag_ignores_grade(self):
        """Runs the IMU stuck flag test in an isolated process."""
        self._run_test_in_subprocess('imu_stuck')



