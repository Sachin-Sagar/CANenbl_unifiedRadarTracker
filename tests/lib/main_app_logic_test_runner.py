# tests/lib/main_app_logic_test_runner.py
import os
import sys
import multiprocessing
import threading
import time
import cantools
import can
import queue

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.can_logger_app import config as can_logger_config
from src.can_logger_app import utils
from src.can_logger_app.can_handler import CANReader
from src.can_logger_app.data_processor import processing_worker

def parse_busmaster_log_for_test(file_path):
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('***'): continue
            parts = line.split()
            if len(parts) < 7: continue
            try:
                time_str, _, _, arb_id_hex, _, _, *data_hex = parts
                h, m, s, ms_micro = time_str.split(':')
                timestamp = int(h) * 3600 + int(m) * 60 + int(s) + int(ms_micro) / 10000.0
                arbitration_id = int(arb_id_hex, 16)
                data = bytearray.fromhex("".join(data_hex))
                yield can.Message(timestamp=timestamp, arbitration_id=arbitration_id, data=data)
            except (ValueError, IndexError):
                continue

def main():
    # Setup paths
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    input_dir = os.path.join(root_dir, 'input')
    dbc_path = os.path.join(root_dir, 'tests', 'test_data', 'tst_input', 'VCU.dbc')
    signal_list_path = os.path.join(root_dir, 'tests', 'test_data', 'tst_input', 'master_sigList.txt')
    log_file_path = os.path.join(root_dir, 'tests', 'test_data', '2w_sample.log')

    assert os.path.exists(dbc_path), "VCU.dbc not found"
    assert os.path.exists(signal_list_path), "master_sigList.txt not found"
    assert os.path.exists(log_file_path), "2w_sample.log not found"

    # Mock the CAN Bus
    log_messages = list(parse_busmaster_log_for_test(log_file_path))
    assert len(log_messages) > 0, "Log file parsing yielded no messages."
    
    # Set up the dual-pipeline architecture
    multiprocessing.set_start_method('spawn', force=True)
    manager = multiprocessing.Manager()
    high_freq_raw_queue, low_freq_raw_queue = multiprocessing.Queue(), multiprocessing.Queue()
    log_queue, worker_signals_queue = multiprocessing.Queue(), multiprocessing.Queue()
    perf_tracker = manager.dict()
    shutdown_flag = multiprocessing.Event()
    
    # Load configuration
    db = cantools.database.load_file(dbc_path)
    high_freq_signals, low_freq_signals, id_to_queue_map = utils.load_signals_to_monitor(signal_list_path)
    high_freq_monitored_signals = {s for sig_set in high_freq_signals.values() for s in sig_set}
    low_freq_monitored_signals = {s for sig_set in low_freq_signals.values() for s in sig_set}

    # Directly populate the raw message queues with parsed log messages
    for msg in log_messages:
        msg_dict = {'arbitration_id': msg.arbitration_id, 'data': msg.data, 'timestamp': msg.timestamp}
        queue_name = id_to_queue_map.get(msg.arbitration_id)
        if queue_name == 'high':
            high_freq_raw_queue.put(msg_dict)
        elif queue_name == 'low':
            low_freq_raw_queue.put(msg_dict)
    
    # Start the worker pools
    all_processes = []
    for i in range(can_logger_config.NUM_HIGH_FREQ_WORKERS):
        p = multiprocessing.Process(target=processing_worker, args=(i, db, high_freq_monitored_signals, high_freq_raw_queue, log_queue, perf_tracker, None, None, None, shutdown_flag, worker_signals_queue), daemon=False)
        all_processes.append(p)
        p.start()
    for i in range(can_logger_config.NUM_LOW_FREQ_WORKERS):
        p = multiprocessing.Process(target=processing_worker, args=(i + can_logger_config.NUM_HIGH_FREQ_WORKERS, db, low_freq_monitored_signals, low_freq_raw_queue, log_queue, perf_tracker, None, None, None, shutdown_flag, worker_signals_queue), daemon=False)
        all_processes.append(p)
        p.start()

    # Give some time for workers to process messages
    time.sleep(10)
    shutdown_flag.set()
    
    # Wait for worker processes to terminate
    for p in all_processes: p.join(timeout=2)

    # Aggregate and assert results
    logged_signals_set = set()
    while not worker_signals_queue.empty():
        try:
            logged_signals_set.update(worker_signals_queue.get_nowait())
        except queue.Empty:
            break
    
    print(f"\n--- Test Results ---")
    print(f"Signals logged: {logged_signals_set}")
    
    assert 'ETS_MOT_ShaftTorque_Est_Nm' in logged_signals_set, "A known high-frequency signal (ETS_MOT_ShaftTorque_Est_Nm) was not logged."
    assert 'ETS_VCU_VehSpeed_Act_kmph' in logged_signals_set, "A known low-frequency signal (ETS_VCU_VehSpeed_Act_kmph) was not logged."
    
    print("Success: Both high and low frequency signals were successfully logged.")

if __name__ == '__main__':
    try:
        main()
        sys.exit(0)
    except Exception as e:
        print(f"Failure: An exception occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
