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
                temp_can_data = dict(shared_dict)
                speed_tuple = temp_can_data.get('ETS_VCU_VehSpeed_Act_kmph')
                if speed_tuple:
                    can_data_for_frame['ETS_VCU_VehSpeed_Act_kmph'] = float(speed_tuple[0])

                torque_tuple = temp_can_data.get('ETS_MOT_ShaftTorque_Est_Nm')
                if torque_tuple:
                    can_data_for_frame['ETS_MOT_ShaftTorque_Est_Nm'] = float(torque_tuple[0])

                grade_tuple = temp_can_data.get('EstimatedGrade_Est_Deg')
                if grade_tuple:
                    can_data_for_frame['EstimatedGrade_Est_Deg'] = float(grade_tuple[0])

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
            'torque': 10.0, # Nm
            'grade': 5.0 # Deg
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
        self.assertGreater(len(history['tracks']), 0, "No tracks were saved in track_history.json")

        # For this test, we'll just check the history of the first track
        first_track_history = history['tracks'][0].get('trackHistory', [])
        self.assertGreater(len(first_track_history), 0, "The first track has an empty trackHistory.")

        # Check the last few frames for the correct CAN data
        num_frames_to_check = min(10, len(first_track_history))
        self.assertGreater(num_frames_to_check, 0, "No frames to check in the first track's history.")

        for i in range(1, num_frames_to_check + 1):
            frame = first_track_history[-i]
            
            # The JSON export maps the long signal name to a shorter key.
            # This mapping happens in export_to_json.py, which is NOT used by update_and_save_history.
            # So we need to check the FHistFrame attribute names directly.
            
            # Let's re-read the export logic. The final JSON from update_and_save_history
            # is created by create_visualization_data. Let's check that file.
            # Okay, create_visualization_data IS used. So the mapping should be correct.

            self.assertIn('canVehSpeed_kmph', frame, f"Frame {-i} is missing 'canVehSpeed_kmph'")
            if frame['canVehSpeed_kmph'] is not None:
                self.assertAlmostEqual(frame['canVehSpeed_kmph'], expected_values['speed'], delta=0.1, msg=f"Frame {-i} speed is incorrect")

            self.assertIn('shaftTorque_Nm', frame, f"Frame {-i} is missing 'shaftTorque_Nm'")
            if frame['shaftTorque_Nm'] is not None:
                self.assertAlmostEqual(frame['shaftTorque_Nm'], expected_values['torque'], delta=0.1, msg=f"Frame {-i} torque is incorrect")

            self.assertIn('roadGrade_Deg', frame, f"Frame {-i} is missing 'roadGrade_Deg'")
            if frame['roadGrade_Deg'] is not None:
                self.assertAlmostEqual(frame['roadGrade_Deg'], expected_values['grade'], delta=0.1, msg=f"Frame {-i} grade is incorrect")

            self.assertIn('egoVx', frame, f"Frame {-i} is missing 'egoVx'")
            if frame['egoVx'] is not None:
                self.assertAlmostEqual(frame['egoVx'], expected_ego_vx_mps, delta=0.1, msg=f"Frame {-i} egoVx is incorrect")

            self.assertIn('estimatedAcceleration_mps2', frame, f"Frame {-i} is missing 'estimatedAcceleration_mps2'")
            # The acceleration should be close to zero since speed and grade are constant
            if frame['estimatedAcceleration_mps2'] is not None:
                self.assertAlmostEqual(frame['estimatedAcceleration_mps2'], 0.0, delta=0.5, msg=f"Frame {-i} estimatedAcceleration_mps2 is not close to zero")
        
        print(f"Test finished successfully. Output files are in: {self.test_output_dir}")

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
