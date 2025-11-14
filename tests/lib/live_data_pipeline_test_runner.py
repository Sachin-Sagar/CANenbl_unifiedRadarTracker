
# tests/lib/live_data_pipeline_test_runner.py
import unittest
import multiprocessing
import time
import json
import os
import sys
import numpy as np
import argparse

# Add project root for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.radar_tracker.data_adapter import adapt_frame_data_to_fhist
from src.radar_tracker.tracking.tracker import RadarTracker
from src.radar_tracker.tracking.parameters import define_parameters
from src.radar_tracker.tracking.update_and_save_history import update_and_save_history
from src.radar_tracker.console_logger import logger as radar_logger

# Suppress console logger output during tests
radar_logger.propagate = False
radar_logger.handlers = []

# --- Mock CAN Logger Processes ---
def mock_can_logger_process(shared_dict, ready_event, shutdown_flag, expected_values):
    start_time = time.time()
    ready_event.set()
    while not shutdown_flag.is_set():
        current_time = time.time() - start_time
        shared_dict['ETS_VCU_VehSpeed_Act_kmph'] = (expected_values['speed'], current_time)
        shared_dict['ETS_MOT_ShaftTorque_Est_Nm'] = (expected_values['torque'], current_time)
        shared_dict['EstimatedGrade_Est_Deg'] = (expected_values['grade'], current_time)
        time.sleep(0.01)

def mock_can_logger_delayed_start(shared_dict, ready_event, shutdown_flag, expected_values):
    time.sleep(0.2)
    current_time = time.time()
    shared_dict['ETS_VCU_VehSpeed_Act_kmph'] = (expected_values['speed'], current_time)
    shared_dict['ETS_MOT_ShaftTorque_Est_Nm'] = (expected_values['torque'], current_time)
    shared_dict['EstimatedGrade_Est_Deg'] = (expected_values['grade'], current_time)
    ready_event.set()
    while not shutdown_flag.is_set():
        current_time = time.time()
        shared_dict['ETS_VCU_VehSpeed_Act_kmph'] = (expected_values['speed'], current_time)
        shared_dict['ETS_MOT_ShaftTorque_Est_Nm'] = (expected_values['torque'], current_time)
        shared_dict['EstimatedGrade_Est_Deg'] = (expected_values['grade'], current_time)
        time.sleep(0.01)

def mock_can_logger_numpy_process(shared_dict, ready_event, shutdown_flag, expected_values):
    start_time = time.time()
    ready_event.set()
    while not shutdown_flag.is_set():
        current_time = time.time() - start_time
        shared_dict['ETS_VCU_VehSpeed_Act_kmph'] = (np.float64(expected_values['speed']), current_time)
        shared_dict['ETS_MOT_ShaftTorque_Est_Nm'] = (np.float64(expected_values['torque']), current_time)
        shared_dict['EstimatedGrade_Est_Deg'] = (np.float64(expected_values['grade']), current_time)
        time.sleep(0.01)

def mock_can_logger_imu_stuck_scenario(shared_dict, ready_event, shutdown_flag, expected_values, flip_frame):
    start_time = time.time()
    ready_event.set()
    while not shutdown_flag.is_set():
        elapsed_time = time.time() - start_time
        frame_counter = int(elapsed_time / 0.05)
        imu_stuck_flag = 1 if frame_counter >= flip_frame else 0
        current_time = time.time()
        shared_dict['ETS_VCU_VehSpeed_Act_kmph'] = (expected_values['speed'], current_time)
        shared_dict['ETS_MOT_ShaftTorque_Est_Nm'] = (expected_values['torque'], current_time)
        shared_dict['EstimatedGrade_Est_Deg'] = (expected_values['grade'], current_time)
        shared_dict['ETS_VCU_imuProc_imuStuck_B'] = (imu_stuck_flag, current_time)
        time.sleep(0.01)

# --- Mock Radar Tracker Process ---
def mock_radar_tracker_process(shared_dict, ready_event, shutdown_flag, output_dir, num_frames, radar_log_path):
    params_tracker = define_parameters()
    params_tracker['lifecycle_params']['confirmation_M'] = 2
    params_tracker['lifecycle_params']['confirmation_N'] = 3
    tracker = RadarTracker(params_tracker)
    fhist_history = []
    with open(radar_log_path, 'r') as f:
        radar_frames = json.load(f)
    
    ready = ready_event.wait(timeout=5.0)
    assert ready, "Timed out waiting for CAN logger."

    start_time = time.time()
    for frame_idx, frame_log_data in enumerate(radar_frames):
        if frame_idx >= num_frames or shutdown_flag.is_set():
            break
        time.sleep(0.05)
        current_timestamp_ms = (time.time() - start_time) * 1000.0
        
        class LoggedFrameData:
            def __init__(self, log_data):
                header_data = log_data.get('header', {})
                self.header = self.Header(header_data.get('timestamp_ms', current_timestamp_ms), header_data.get('frame_idx', frame_idx))
                point_cloud_list = log_data.get('point_cloud', [])
                self.point_cloud = np.array(point_cloud_list) if point_cloud_list else np.empty((5, 0))
                self.num_points = self.point_cloud.shape[1] if self.point_cloud.ndim > 1 else 0
                self.points = []
            class Header:
                def __init__(self, timestamp_ms, frame_idx):
                    self.timestamp_ms, self.frame_idx = timestamp_ms, frame_idx

        frame_data = LoggedFrameData(frame_log_data)
        can_data_for_frame = {k: float(v[0]) for k, v in dict(shared_dict).items() if v and isinstance(v, (list, tuple))}
        
        fhist_frame = adapt_frame_data_to_fhist(frame_data, current_timestamp_ms, can_signals=can_data_for_frame)
        _, processed_frame = tracker.process_frame(fhist_frame)
        fhist_history.append(processed_frame)

    if fhist_history:
        filename = os.path.join(output_dir, "track_history.json")
        update_and_save_history(tracker.all_tracks, fhist_history, filename, params=tracker.params)
    
    shutdown_flag.set()

# --- Test Logic Functions ---
def run_data_integrity_test(output_dir):
    manager = multiprocessing.Manager()
    shared_live_can_data = manager.dict()
    can_logger_ready = manager.Event()
    shutdown_flag = manager.Event()
    expected_values = {'speed': 50.0, 'torque': 0.0, 'grade': 0.0}
    radar_log_path = 'tests/test_data/sample_data/radar_log.json'
    num_frames = 50
    
    can_process = multiprocessing.Process(target=mock_can_logger_process, args=(shared_live_can_data, can_logger_ready, shutdown_flag, expected_values))
    radar_process = multiprocessing.Process(target=mock_radar_tracker_process, args=(shared_live_can_data, can_logger_ready, shutdown_flag, output_dir, num_frames, radar_log_path))
    
    can_process.start()
    radar_process.start()
    can_process.join()
    radar_process.join()

    track_history_file = os.path.join(output_dir, 'track_history.json')
    assert os.path.exists(track_history_file), "track_history.json was not created."
    with open(track_history_file, 'r') as f: history = json.load(f)
    radar_frames = history['radarFrames']
    assert len(radar_frames) > 0, "radarFrames list is empty."
    last_frame = radar_frames[-1]
    assert abs(last_frame['canVehSpeed_kmph'] - expected_values['speed']) < 0.1

def run_startup_race_condition_test(output_dir):
    manager = multiprocessing.Manager()
    shared_live_can_data = manager.dict()
    can_logger_ready = manager.Event()
    shutdown_flag = manager.Event()
    expected_values = {'speed': 3.0, 'torque': 5.0, 'grade': 1.0}
    radar_log_path = 'tests/test_data/sample_data/radar_log.json'
    num_frames = 20

    can_process = multiprocessing.Process(target=mock_can_logger_delayed_start, args=(shared_live_can_data, can_logger_ready, shutdown_flag, expected_values))
    radar_process = multiprocessing.Process(target=mock_radar_tracker_process, args=(shared_live_can_data, can_logger_ready, shutdown_flag, output_dir, num_frames, radar_log_path))

    can_process.start()
    radar_process.start()
    can_process.join()
    radar_process.join()

    track_history_file = os.path.join(output_dir, 'track_history.json')
    assert os.path.exists(track_history_file)
    with open(track_history_file, 'r') as f: history = json.load(f)
    first_frame = history['radarFrames'][0]
    assert first_frame['canVehSpeed_kmph'] is not None and first_frame['canVehSpeed_kmph'] > 0

def run_numpy_corruption_test(output_dir):
    manager = multiprocessing.Manager()
    shared_live_can_data = manager.dict()
    can_logger_ready = manager.Event()
    shutdown_flag = manager.Event()
    expected_values = {'speed': np.float64(9.36), 'torque': np.float64(12.5), 'grade': np.float64(0.5)}
    radar_log_path = 'tests/test_data/sample_data/radar_log.json'
    num_frames = 30

    can_process = multiprocessing.Process(target=mock_can_logger_numpy_process, args=(shared_live_can_data, can_logger_ready, shutdown_flag, expected_values))
    radar_process = multiprocessing.Process(target=mock_radar_tracker_process, args=(shared_live_can_data, can_logger_ready, shutdown_flag, output_dir, num_frames, radar_log_path))

    can_process.start()
    radar_process.start()
    can_process.join()
    radar_process.join()

    track_history_file = os.path.join(output_dir, 'track_history.json')
    assert os.path.exists(track_history_file)
    with open(track_history_file, 'r') as f: history = json.load(f)
    last_frame = history['radarFrames'][-1]
    assert abs(last_frame['canVehSpeed_kmph'] - expected_values['speed']) < 0.1

def run_imu_stuck_test(output_dir):
    manager = multiprocessing.Manager()
    shared_live_can_data = manager.dict()
    can_logger_ready = manager.Event()
    shutdown_flag = manager.Event()
    expected_values = {'speed': 40.0, 'torque': 15.0, 'grade': 5.0}
    radar_log_path = 'tests/test_data/sample_data/radar_log.json'
    num_frames = 15
    flip_frame = 8

    can_process = multiprocessing.Process(target=mock_can_logger_imu_stuck_scenario, args=(shared_live_can_data, can_logger_ready, shutdown_flag, expected_values, flip_frame))
    radar_process = multiprocessing.Process(target=mock_radar_tracker_process, args=(shared_live_can_data, can_logger_ready, shutdown_flag, output_dir, num_frames, radar_log_path))

    can_process.start()
    radar_process.start()
    can_process.join()
    radar_process.join()

    track_history_file = os.path.join(output_dir, 'track_history.json')
    assert os.path.exists(track_history_file)
    with open(track_history_file, 'r') as f: history = json.load(f)
    radar_frames = history['radarFrames']
    
    first_null_idx = -1
    for i, frame in enumerate(radar_frames):
        if frame.get('roadGrade_Deg') is None:
            first_null_idx = i
            break
    
    assert first_null_idx != 0, "Grade should not be null in the first frame."
    assert first_null_idx != -1, "Grade was never set to null."
    assert flip_frame - 4 <= first_null_idx <= flip_frame + 4, f"Grade became null at frame {first_null_idx}, too far from expected {flip_frame}."

def main():
    multiprocessing.set_start_method('spawn', force=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', required=True, choices=['data_integrity', 'startup_race', 'numpy_corruption', 'imu_stuck'])
    parser.add_argument('--output_dir', required=True)
    args = parser.parse_args()

    if args.test == 'data_integrity': run_data_integrity_test(args.output_dir)
    elif args.test == 'startup_race': run_startup_race_condition_test(args.output_dir)
    elif args.test == 'numpy_corruption': run_numpy_corruption_test(args.output_dir)
    elif args.test == 'imu_stuck': run_imu_stuck_test(args.output_dir)

if __name__ == '__main__':
    try:
        main()
        sys.exit(0)
    except Exception as e:
        print(f"Failure: An exception occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
