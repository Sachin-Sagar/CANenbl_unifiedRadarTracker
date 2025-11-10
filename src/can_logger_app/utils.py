# utils.py

import os
import cantools
import bitstruct
from can_logger_app import config

def load_signals_to_monitor(file_path):
    """
    Parses the signal list file (format: CAN_ID,Signal_Name,CycleTime) and
    creates dictionaries to separate high-frequency and low-frequency signals.
    ---
    MODIFIED: CAN IDs are now stored as INTEGERS to avoid string formatting issues.
    """
    high_freq_signals = {}
    low_freq_signals = {}
    id_to_queue_map = {}

    if config.DEBUG_PRINTING:
        print("DEBUG: Loading and parsing signal list...")

    try:
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip() or line.strip().startswith('#'):
                    continue

                parts = [p.strip() for p in line.split(',')]
                
                if len(parts) == 3:
                    can_id_raw, signal_name, cycle_time = parts
                    
                    try:
                        can_id_int = int(can_id_raw, 16)

                        rate = int(cycle_time)
                        if rate == 10:
                            if can_id_int not in high_freq_signals:
                                high_freq_signals[can_id_int] = set()
                            high_freq_signals[can_id_int].add(signal_name)
                            id_to_queue_map[can_id_int] = 'high'
                        elif rate == 100:
                            if can_id_int not in low_freq_signals:
                                low_freq_signals[can_id_int] = set()
                            low_freq_signals[can_id_int].add(signal_name)
                            id_to_queue_map[can_id_int] = 'low'
                        else:
                            print(f"Warning: Skipping line {line_num}. Cycle time must be 10 or 100, but got {rate}.")
                            continue
                    except ValueError:
                        print(f"Warning: Skipping malformed line {line_num}. CAN ID '{can_id_raw}' or cycle time '{cycle_time}' is not a valid integer.")
                        continue
                else:
                    print(f"Warning: Skipping malformed line {line_num} in '{file_path}'. Expected 3 parts, got {len(parts)}.")

    except FileNotFoundError:
        print(f"Error: Signal list file not found at '{file_path}'.")
        return None, None, None
    
    if config.DEBUG_PRINTING:
        print("DEBUG: --- CAN ID to Queue Mapping (INTEGER KEYS) ---")
        for can_id, queue_name in id_to_queue_map.items():
            print(f" -> ID: {can_id} (0x{can_id:x}) mapped to '{queue_name}' queue.")
        print("--------------------------------------------------")
    
    if not high_freq_signals and not low_freq_signals:
        print(f"Warning: No valid signals were loaded from '{file_path}'.")
        
    return high_freq_signals, low_freq_signals, id_to_queue_map
