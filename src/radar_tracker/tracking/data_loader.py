# src/data_loader.py

import scipy.io as sio
import numpy as np
import os
import logging
import re
from datetime import datetime, timedelta

def load_fhist_data(file_path):
    """
    Loads the fHist structure from a .mat file and extracts the start time from the filename.
    """
    if not os.path.exists(file_path):
        logging.error(f"Error: Radar history file not found at {file_path}")
        return None, None

    try:
        mat_data = sio.loadmat(file_path, struct_as_record=False, squeeze_me=True)
        
        if 'fHist' in mat_data:
            fhist = mat_data['fHist']
            logging.info(f"Successfully loaded fHist data with {len(fhist)} frames.")
            
            filename = os.path.basename(file_path)
            match = re.search(r'fHist_(\d{8}_\d{6}\.\d{3})', filename)
            
            if match:
                timestamp_str = match.group(1)
                radar_start_datetime = datetime.strptime(timestamp_str, '%d%m%Y_%H%M%S.%f')
                logging.info(f"Radar log start time from filename: {radar_start_datetime.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                return fhist, radar_start_datetime
            else:
                logging.warning(f"Could not extract radar start timestamp from filename '{filename}'. CAN sync will not be possible.")
                return fhist, None
        else:
            logging.error("Error: 'fHist' variable not found in the .mat file.")
            return None, None
            
    except Exception as e:
        logging.error(f"An error occurred while loading the .mat file: {e}")
        return None, None

def load_and_sync_can_data(can_file_path, radar_start_datetime, fhist):
    """
    Loads CAN log data, synchronizes it with the radar history, and
    creates a dictionary of snipped CAN signals.
    """
    if radar_start_datetime is None:
        logging.warning("Cannot sync CAN data without radar start time.")
        return None

    if not os.path.exists(can_file_path):
        logging.error(f"Error: CAN log file not found at {can_file_path}")
        return None
    
    signal_list = [
        'VehSpeed_Act_kmph', 'ShaftTorque_Est_Nm', 'Gear_Engaged_St_enum', 'AccelerationAvg', 
        'EstimatedGrade_Est_Deg', 'imuProc_xaccel', 'imuProc_yaccel', 'imuProc_zaccel', 
        'imuProc_imuStuck_B', 'imuProc_pitchCF', 'imuProc_pitchRate', 'imuProc_rollCF', 
        'imuProc_rollRate', 'imuProc_yawRate', 'BrakePressStatus_St_enum', 
        'AccelPedal_Act_perc', 'BrakePedal_Act_perc'
    ]
    
    snipped_can_signals = {}
    
    try:
        logging.info(f"Loading CAN log data from: {can_file_path}")
        can_data = sio.loadmat(can_file_path, struct_as_record=False, squeeze_me=True)
        
        radar_end_datetime = radar_start_datetime + timedelta(milliseconds=fhist[-1].timestamp)
        logging.info(f"Radar log end time (calculated): {radar_end_datetime.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        tolerance = timedelta(milliseconds=50)
        
        # --- DEBUG MESSAGE ADDED ---
        logging.info("\n--- Checking for CAN Signals ---")
        for signal_name in signal_list:
            if hasattr(can_data.get('decoded_signals', {}), signal_name):
                signal = getattr(can_data['decoded_signals'], signal_name)
                raw_data = np.atleast_1d(signal.Physical_Value)
                raw_timestamps_str = np.atleast_1d(signal.Timestamp)
                raw_timestamps_dt = [datetime.strptime(ts, '%d-%m-%Y %H:%M:%S.%f') for ts in raw_timestamps_str]
                can_indices = [
                    i for i, ts in enumerate(raw_timestamps_dt) 
                    if (radar_start_datetime - tolerance) <= ts <= (radar_end_datetime + tolerance)
                ]
                if can_indices:
                    timestamps = np.array([dt.timestamp() for dt in raw_timestamps_dt])[can_indices]
                    data = raw_data[can_indices]
                    snipped_can_signals[signal_name] = {'posix_timestamps': timestamps, 'data': data}
                    # --- DEBUG MESSAGE ADDED ---
                    logging.info(f"  [SUCCESS] Found {len(data)} data points for signal '{signal_name}'.")
                else:
                    logging.warning(f"  [WARNING] No data found for signal '{signal_name}' within the radar time frame.")
            else:
                logging.warning(f"  [WARNING] Signal '{signal_name}' not found in the CAN log file.")
        
        logging.info("--- CAN log extraction and snipping complete. ---\n")
        return snipped_can_signals

    except Exception as e:
        logging.error(f"An error occurred while processing the CAN log: {e}")
        return None