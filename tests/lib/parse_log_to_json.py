import os
import json
import can
import cantools
import time
from collections import deque

# --- Configuration ---
LOG_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../test_data/2w_sample.log'))
SIGNAL_LIST_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../test_data/tst_input/master_sigList.txt'))
DBC_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../test_data/tst_input/VCU.dbc'))
OUTPUT_JSON_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../test_data/parsed_signals.json'))

# --- Utility Functions (Adapted from tests/test_can_log_playback.py and src/can_service/utils.py) ---

def parse_busmaster_log(file_path):
    """
    Parses a BUSMASTER log file and yields can.Message objects.
    Assumes the log format: <Time><Tx/Rx><Channel><CAN ID><Type><DLC><DataBytes>
    Example: 11:42:34:1151 Rx 1 0x096 s 8 03 10 40 04 80 00 00 00
    """
    first_message_timestamp_s = None
    base_timestamp = time.time() # Use current system time as a base for the first message

    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('***'):
                continue

            parts = line.split()
            if len(parts) < 7:
                continue

            try:
                time_str = parts[0]
                time_parts = time_str.split(':')
                h, m, s, ms = map(int, time_parts)
                
                current_message_time_s = h * 3600 + m * 60 + s + ms / 1000.0

                if first_message_timestamp_s is None:
                    first_message_timestamp_s = current_message_time_s
                
                timestamp = base_timestamp + (current_message_time_s - first_message_timestamp_s)

                arbitration_id = int(parts[3], 16)
                is_extended_id = (parts[4] == 'e')
                dlc = int(parts[5])
                data_bytes_hex = parts[6:]
                data = bytearray([int(b, 16) for b in data_bytes_hex])

                message = can.Message(
                    timestamp=timestamp,
                    arbitration_id=arbitration_id,
                    is_extended_id=is_extended_id,
                    dlc=dlc,
                    data=data
                )
                yield message
            except (ValueError, IndexError) as e:
                print(f"Warning: Could not parse line: '{line}' - {e}")
                continue

def load_signals_to_monitor(file_path):
    """
    Parses the signal list file (format: CAN_ID,Signal_Name,CycleTime) and
    returns a dictionary of {can_id: {signal_name1, signal_name2}}.
    """
    signals_to_monitor = {}
    try:
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip() or line.strip().startswith('#'):
                    continue

                parts = [p.strip() for p in line.split(',')]
                
                if len(parts) >= 2: # Only need CAN_ID and Signal_Name
                    can_id_raw, signal_name = parts[0], parts[1]
                    
                    try:
                        can_id_int = int(can_id_raw, 16)
                        if can_id_int not in signals_to_monitor:
                            signals_to_monitor[can_id_int] = set()
                        signals_to_monitor[can_id_int].add(signal_name)
                    except ValueError:
                        print(f"Warning: Skipping malformed line {line_num}. CAN ID '{can_id_raw}' is not a valid integer.")
                        continue
                else:
                    print(f"Warning: Skipping malformed line {line_num} in '{file_path}'. Expected at least 2 parts, got {len(parts)}.")

    except FileNotFoundError:
        print(f"Error: Signal list file not found at '{file_path}'.")
        return None
    
    return signals_to_monitor



# --- Main Script Logic ---
def main():
    print(f"Parsing log file: {LOG_FILE_PATH}")
    print(f"Using signal list: {SIGNAL_LIST_PATH}")
    print(f"Using DBC file: {DBC_FILE_PATH}")

    # 1. Load DBC file
    try:
        db = cantools.database.load_file(DBC_FILE_PATH)
    except Exception as e:
        print(f"Error loading DBC file '{DBC_FILE_PATH}': {e}")
        return

    # 2. Load signals to monitor
    signals_to_monitor_by_id = load_signals_to_monitor(SIGNAL_LIST_PATH)
    if not signals_to_monitor_by_id:
        print("No signals to monitor. Exiting.")
        return
        
    # Create a flat set of all signal names to monitor
    all_signals_to_monitor = set()
    for signal_set in signals_to_monitor_by_id.values():
        all_signals_to_monitor.update(signal_set)

    parsed_signals_data = []

    # 3. Process log file
    for msg in parse_busmaster_log(LOG_FILE_PATH):
        # Check if the message ID is one we are interested in
        if msg.arbitration_id in signals_to_monitor_by_id:
            try:
                # Use cantools to decode the message
                decoded_signals = db.decode_message(msg.arbitration_id, msg.data)
                
                # Filter for the signals we want to log
                for signal_name, physical_value in decoded_signals.items():
                    if signal_name in all_signals_to_monitor:
                        parsed_signals_data.append({
                            "timestamp": msg.timestamp,
                            "signal_name": signal_name,
                            "value": float(physical_value) # Ensure native Python float
                        })
            except Exception as e:
                # This can happen if a message ID is in our list but not fully defined in the DBC
                # for the given data, or other decoding errors.
                # print(f"Warning: Could not decode message ID 0x{msg.arbitration_id:x}: {e}")
                continue
    
    # 4. Write to JSON file
    try:
        with open(OUTPUT_JSON_FILE, 'w') as f:
            json.dump(parsed_signals_data, f, indent=4)
        print(f"Successfully parsed {len(parsed_signals_data)} signal values to '{OUTPUT_JSON_FILE}'")
    except Exception as e:
        print(f"Error writing to JSON file '{OUTPUT_JSON_FILE}': {e}")

if __name__ == "__main__":
    main()
