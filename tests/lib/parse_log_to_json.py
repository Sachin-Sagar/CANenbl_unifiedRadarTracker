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

def precompile_decoding_rules(db, signals_to_monitor):
    """
    Pre-compiles the decoding rules for faster processing.
    Returns a dictionary of {msg_id_int: [(signal_name, is_signed, start, length, scale, offset), ...]}
    """
    rules = {}
    for msg_id_int, signal_names in signals_to_monitor.items():
        try:
            message = db.get_message_by_frame_id(msg_id_int)
            
            rule_list = []
            for signal_name in signal_names:
                signal = message.get_signal_by_name(signal_name)
                
                rule = (
                    signal.name,
                    signal.is_signed,
                    signal.start,
                    signal.length,
                    signal.scale,
                    signal.offset
                )
                rule_list.append(rule)
            
            if rule_list:
                rules[msg_id_int] = rule_list

        except KeyError:
            print(f"Warning: Message ID {msg_id_int} (0x{msg_id_int:x}) from signal list not found in DBC file.")
            continue
            
    return rules

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
    signals_to_monitor = load_signals_to_monitor(SIGNAL_LIST_PATH)
    if not signals_to_monitor:
        print("No signals to monitor. Exiting.")
        return

    # 3. Precompile decoding rules
    decoding_rules = precompile_decoding_rules(db, signals_to_monitor)
    if not decoding_rules:
        print("No decoding rules compiled. Exiting.")
        return

    parsed_signals_data = []

    # 4. Process log file
    for msg in parse_busmaster_log(LOG_FILE_PATH):
        if msg.arbitration_id in decoding_rules:
            rules = decoding_rules[msg.arbitration_id]
            data_int = int.from_bytes(msg.data, byteorder='little')
            
            for name, is_signed, start, length, scale, offset in rules:
                shifted = data_int >> start
                mask = (1 << length) - 1
                raw_value = shifted & mask

                if is_signed:
                    if raw_value & (1 << (length - 1)):
                        raw_value -= (1 << length)

                physical_value = (raw_value * scale) + offset
                
                parsed_signals_data.append({
                    "timestamp": msg.timestamp,
                    "signal_name": name,
                    "value": float(physical_value) # Ensure native Python float
                })
    
    # 5. Write to JSON file
    try:
        with open(OUTPUT_JSON_FILE, 'w') as f:
            json.dump(parsed_signals_data, f, indent=4)
        print(f"Successfully parsed {len(parsed_signals_data)} signal values to '{OUTPUT_JSON_FILE}'")
    except Exception as e:
        print(f"Error writing to JSON file '{OUTPUT_JSON_FILE}': {e}")

if __name__ == "__main__":
    main()
