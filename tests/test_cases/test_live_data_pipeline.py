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
        """Set up for the test."""
        self.test_output_dir = os.path.join('tests', 'output', datetime.now().strftime("%Y%m%d_%H%M%S"))
        print(f"DEBUG: Creating output directory: {self.test_output_dir}")
        os.makedirs(self.test_output_dir, exist_ok=True)
        print(f"DEBUG: Directory created: {os.path.exists(self.test_output_dir)}")
        
        self.track_history_file = os.path.join(self.test_output_dir, 'track_history.json')

    def test_data_integrity_in_live_pipeline(self):
        """
        Test the full pipeline from a simulated CAN source to the final track history.
        This test will:
        1. Start a mock CAN logger process that provides constant, known values.
        2. Start a mock radar tracker process that generates dummy radar data.
        3. Pass CAN data from the logger to the tracker via a shared dictionary.
        4. Verify that the CAN data in the final track_history.json is not corrupted.
        """
        manager = multiprocessing.Manager()
        shared_live_can_data = manager.dict()
        can_logger_ready = manager.Event()
        shutdown_flag = manager.Event()

        expected_values = {
            'speed': 50.0, # kmph
            'torque': 0.0, # Nm
            'grade': 0.0 # Deg
        }
        expected_ego_vx_mps = expected_values['speed'] / 3.6 # Convert kmph to mps

        radar_log_path = 'tests/test_data/sample_data/radar_log.json'
        self.assertTrue(os.path.exists(radar_log_path), f"Radar log file not found at {radar_log_path}")

        can_process = multiprocessing.Process(
            target=mock_can_logger_process,
            args=(shared_live_can_data, can_logger_ready, shutdown_flag, self.test_output_dir, expected_values)
        )

        # Process enough frames to ensure data is captured
        num_frames = 50 
        radar_process = multiprocessing.Process(
            target=mock_radar_tracker_process,
            args=(shared_live_can_data, can_logger_ready, shutdown_flag, self.test_output_dir, num_frames, radar_log_path)
        )

        print("Starting CAN logger and Radar tracker processes...")
        can_process.start()
        radar_process.start()

        # Wait for processes to finish gracefully
        can_process.join()
        radar_process.join()

        # Verification
        self.assertTrue(os.path.exists(self.track_history_file), f"track_history.json was not created in {self.test_output_dir}")
        
        with open(self.track_history_file, 'r') as f:
            history = json.load(f)
        
        self.assertIn('tracks', history, "The 'tracks' key is missing from track_history.json")
        self.assertIn('radarFrames', history, "The 'radarFrames' key is missing from track_history.json")
        
        # --- VERIFICATION IS NOW DONE ON radarFrames ---
        radar_frames = history['radarFrames']
        self.assertGreater(len(radar_frames), 0, "The radarFrames list is empty.")

        # Check the last few frames for the correct CAN data
        num_frames_to_check = min(10, len(radar_frames))
        self.assertGreater(num_frames_to_check, 0, "No frames to check in the radarFrames list.")

        for i in range(1, num_frames_to_check + 1):
            frame = radar_frames[-i]
            
            self.assertIn('canVehSpeed_kmph', frame, f"Frame {-i} is missing 'canVehSpeed_kmph'")
            if frame['canVehSpeed_kmph'] is not None:
                self.assertAlmostEqual(frame['canVehSpeed_kmph'], expected_values['speed'], delta=0.1, msg=f"Frame {-i} speed is incorrect")

            self.assertIn('shaftTorque_Nm', frame, f"Frame {-i} is missing 'shaftTorque_Nm'")
            if frame['shaftTorque_Nm'] is not None:
                self.assertAlmostEqual(frame['shaftTorque_Nm'], expected_values['torque'], delta=0.1, msg=f"Frame {-i} torque is incorrect")

            self.assertIn('roadGrade_Deg', frame, f"Frame {-i} is missing 'roadGrade_Deg'")
            if frame['roadGrade_Deg'] is not None:
                self.assertAlmostEqual(frame['roadGrade_Deg'], expected_values['grade'], delta=0.1, msg=f"Frame {-i} grade is incorrect")

            # Check the egoVx which is derived from the CAN speed
            self.assertIn('egoVelocity', frame, f"Frame {-i} is missing 'egoVelocity'")
            if frame['egoVelocity'] and frame['egoVelocity'][0] is not None:
                self.assertAlmostEqual(frame['egoVelocity'][0], expected_ego_vx_mps, delta=0.1, msg=f"Frame {-i} egoVx is incorrect")

            self.assertIn('estimatedAcceleration_mps2', frame, f"Frame {-i} is missing 'estimatedAcceleration_mps2'")
            # The acceleration should be close to zero since speed and grade are constant
            if frame['estimatedAcceleration_mps2'] is not None:
                self.assertAlmostEqual(frame['estimatedAcceleration_mps2'], 0.0, delta=0.5, msg=f"Frame {-i} estimatedAcceleration_mps2 is not close to zero")
        
        print(f"Test finished successfully. Output files are in: {self.test_output_dir}")

    def test_startup_race_condition_fix(self):
        """
        Tests that the radar tracker waits for the CAN logger to be ready.
        It uses a mock CAN logger that has an initial delay, simulating a
        real-world startup sequence. The test verifies that the first frame
        of data is valid, not garbage.
        """
        manager = multiprocessing.Manager()
        shared_live_can_data = manager.dict()
        can_logger_ready = manager.Event()
        shutdown_flag = manager.Event()

        expected_values = {
            'speed': 3.0, # kmph
            'torque': 5.0, # Nm
            'grade': 1.0 # Deg
        }
        expected_ego_vx_mps = expected_values['speed'] / 3.6

        radar_log_path = 'tests/test_data/sample_data/radar_log.json'
        self.assertTrue(os.path.exists(radar_log_path), f"Radar log file not found at {radar_log_path}")

        # Use the DELAYED mock CAN logger
        can_process = multiprocessing.Process(
            target=mock_can_logger_delayed_start,
            args=(shared_live_can_data, can_logger_ready, shutdown_flag, self.test_output_dir, expected_values)
        )

        num_frames = 20 # Process fewer frames, we only care about the start
        radar_process = multiprocessing.Process(
            target=mock_radar_tracker_process,
            args=(shared_live_can_data, can_logger_ready, shutdown_flag, self.test_output_dir, num_frames, radar_log_path)
        )

        print("Starting DELAYED CAN logger and Radar tracker processes...")
        can_process.start()
        radar_process.start()

        can_process.join()
        radar_process.join()

        # Verification
        self.assertTrue(os.path.exists(self.track_history_file), f"track_history.json was not created in {self.test_output_dir}")
        
        with open(self.track_history_file, 'r') as f:
            history = json.load(f)
        
        self.assertIn('radarFrames', history)
        radar_frames = history['radarFrames']
        self.assertGreater(len(radar_frames), 0, "The radarFrames list is empty.")

        # --- CRITICAL ASSERTION: Check the VERY FIRST frame in radarFrames ---
        first_frame = radar_frames[0]
        
        self.assertIn('canVehSpeed_kmph', first_frame, "First frame is missing 'canVehSpeed_kmph'")
        # The very first frame might have a slightly different interpolated value
        # but it should NOT be a massive negative number.
        self.assertIsNotNone(first_frame['canVehSpeed_kmph'], "First frame speed is None")
        self.assertGreater(first_frame['canVehSpeed_kmph'], 0, "First frame speed should be positive")
        self.assertLess(first_frame['canVehSpeed_kmph'], 100, "First frame speed is unrealistically high")

        self.assertIn('shaftTorque_Nm', first_frame, "First frame is missing 'shaftTorque_Nm'")
        self.assertIsNotNone(first_frame['shaftTorque_Nm'], "First frame torque is None")
        self.assertGreater(first_frame['shaftTorque_Nm'], 0, "First frame torque should be positive")
        self.assertLess(first_frame['shaftTorque_Nm'], 100, "First frame torque is unrealistically high")

        self.assertIn('egoVelocity', first_frame, "First frame is missing 'egoVelocity'")
        self.assertIsNotNone(first_frame['egoVelocity'][0], "First frame egoVx is None")
        self.assertGreater(first_frame['egoVelocity'][0], 0, "First frame egoVx should be positive")

        print(f"Startup race condition test finished successfully. Output files are in: {self.test_output_dir}")

    def test_numpy_float64_corruption_fix(self):
        """
        Tests that a numpy.float64 value, which caused corruption, is now
        handled correctly when passed through the multiprocessing shared dictionary.
        """
        manager = multiprocessing.Manager()
        shared_live_can_data = manager.dict()
        can_logger_ready = manager.Event()
        shutdown_flag = manager.Event()

        expected_values = {
            'speed': np.float64(9.36),    # A value that was known to corrupt
            'torque': np.float64(12.5),
            'grade': np.float64(0.5)
        }
        expected_ego_vx_mps = expected_values['speed'] / 3.6

        radar_log_path = 'tests/test_data/sample_data/radar_log.json'
        self.assertTrue(os.path.exists(radar_log_path))

        # Use the special numpy-based mock CAN logger
        can_process = multiprocessing.Process(
            target=mock_can_logger_numpy_process,
            args=(shared_live_can_data, can_logger_ready, shutdown_flag, self.test_output_dir, expected_values)
        )

        num_frames = 30
        radar_process = multiprocessing.Process(
            target=mock_radar_tracker_process,
            args=(shared_live_can_data, can_logger_ready, shutdown_flag, self.test_output_dir, num_frames, radar_log_path)
        )

        print("Starting Numpy Corruption Test...")
        can_process.start()
        radar_process.start()

        can_process.join()
        radar_process.join()

        self.assertTrue(os.path.exists(self.track_history_file))
        
        with open(self.track_history_file, 'r') as f:
            history = json.load(f)
        
        radar_frames = history['radarFrames']
        self.assertGreater(len(radar_frames), 10, "Ensure enough frames were processed") # Ensure enough frames were processed

        # Check the last frame for the correct, uncorrupted CAN data
        last_frame = radar_frames[-1]
        
        self.assertIn('canVehSpeed_kmph', last_frame)
        self.assertIsNotNone(last_frame['canVehSpeed_kmph'])
        # This is the critical assertion: is the value correct or corrupted?
        self.assertAlmostEqual(last_frame['canVehSpeed_kmph'], expected_values['speed'], delta=0.1, msg="Numpy float64 speed value was corrupted")

        self.assertIn('shaftTorque_Nm', last_frame)
        self.assertIsNotNone(last_frame['shaftTorque_Nm'])
        self.assertAlmostEqual(last_frame['shaftTorque_Nm'], expected_values['torque'], delta=0.1, msg="Numpy float64 torque value was corrupted")

        self.assertIn('roadGrade_Deg', last_frame)
        self.assertIsNotNone(last_frame['roadGrade_Deg'])
        self.assertAlmostEqual(last_frame['roadGrade_Deg'], expected_values['grade'], delta=0.1, msg="Numpy float64 grade value was corrupted")

        print(f"Numpy corruption test finished successfully. Output files are in: {self.test_output_dir}")

    def test_imu_stuck_flag_ignores_grade(self):
        """
        Tests that when the 'ETS_VCU_imuProc_imuStuck_B' flag is set to 1,
        the road grade is ignored by the tracker, resulting in a null value
        in the final output.
        """
        manager = multiprocessing.Manager()
        shared_live_can_data = manager.dict()
        can_logger_ready = manager.Event()
        shutdown_flag = manager.Event()

        expected_values = {
            'speed': 40.0,
            'torque': 15.0,
            'grade': 5.0  # A non-zero grade
        }
        
        radar_log_path = 'tests/test_data/sample_data/radar_log.json'
        self.assertTrue(os.path.exists(radar_log_path))

        # The test data file only has ~16 frames.
        num_frames = 15
        flip_frame = 8 # The frame where the IMU stuck flag will be set to 1

        # Use the new scenario-based mock CAN logger
        can_process = multiprocessing.Process(
            target=mock_can_logger_imu_stuck_scenario,
            args=(shared_live_can_data, can_logger_ready, shutdown_flag, self.test_output_dir, expected_values, flip_frame)
        )

        radar_process = multiprocessing.Process(
            target=mock_radar_tracker_process,
            args=(shared_live_can_data, can_logger_ready, shutdown_flag, self.test_output_dir, num_frames, radar_log_path)
        )

        print("Starting IMU Stuck Flag Test...")
        can_process.start()
        radar_process.start()

        can_process.join()
        radar_process.join()

        self.assertTrue(os.path.exists(self.track_history_file))
        
        with open(self.track_history_file, 'r') as f:
            history = json.load(f)
        
        radar_frames = history['radarFrames']
        self.assertGreaterEqual(len(radar_frames), num_frames - 5, "Not enough frames were processed")

        # --- ROBUST VERIFICATION ---
        # Find the first frame where the grade is null
        first_null_idx = -1
        for i, frame in enumerate(radar_frames):
            if frame.get('roadGrade_Deg') is None:
                first_null_idx = i
                break
        
        # 1. Assert that the grade was not null from the very beginning
        self.assertNotEqual(first_null_idx, 0, "Grade should not be null in the first frame.")
        self.assertTrue(first_null_idx != -1, "Grade was never set to null, the feature did not work.")

        # 2. Assert that the flip happened near the expected frame, allowing for some timing skew
        self.assertTrue(flip_frame - 4 <= first_null_idx <= flip_frame + 4, 
                        f"Grade became null at frame {first_null_idx}, which is too far from the expected flip frame of {flip_frame}.")

        # 3. Assert that the frame right before the flip has a valid grade
        frame_before = radar_frames[first_null_idx - 1]
        self.assertIsNotNone(frame_before['roadGrade_Deg'], f"Grade should be valid in frame {first_null_idx - 1}, right before it became null.")
        self.assertAlmostEqual(frame_before['roadGrade_Deg'], expected_values['grade'], delta=0.1)

        print(f"IMU stuck flag test finished successfully. Grade became null at frame {first_null_idx}. Output files are in: {self.test_output_dir}")


if __name__ == '__main__':
    # Set the start method for multiprocessing
    # 'fork' is the default on Linux, but 'spawn' is safer and more cross-platform
    # 'fork' can cause issues with shared resources and threads.
    try:
        multiprocessing.set_start_method('spawn')
    except RuntimeError:
        # set_start_method can only be called once
        pass
    unittest.main()
