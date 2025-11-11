
import unittest
import os
import sys
import multiprocessing
import time
from collections import defaultdict
import queue
import cantools
import builtins
# Ensure parse_busmaster_log is correctly imported
from tests.test_cases.test_can_log_playback import parse_busmaster_log

# Force 'spawn' start method for clean process creation, avoiding fork-related issues
try:
    multiprocessing.set_start_method('spawn', force=True)
except RuntimeError:
    # It might already be set, which is fine.
    pass

from src.can_logger_app import config as can_config_root

# Add project root for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# --- Debug Worker Function ---
# Copied from src/can_logger_app/data_processor.py and modified for intense debugging
def _debug_processing_worker(worker_id, db, signals_to_log, raw_queue, results_queue, perf_tracker, log_file_path, live_data_dict=None, can_logger_ready=None, shutdown_flag=None, worker_signals_queue=None):
    """
    Debug version of the processing worker that logs its output to a specific file.
    """
    local_logged_signals = set()
    
    relevant_message_ids = {
        message.frame_id for message in db.messages 
        if any(signal.name in signals_to_log for signal in message.signals)
    }

    try:
        with open(log_file_path, 'w', buffering=1) as log_f:
            # Define a new print function for this scope that writes to the log file
            def print(*args, **kwargs):
                builtins.print(*args, file=log_f, **kwargs)

            print(f"--- [DEBUG WORKER {worker_id}] LOG START ---")
            print(f"Monitoring signals: {signals_to_log}")

            while not (shutdown_flag and shutdown_flag.is_set()):
                try:
                    msg = raw_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if msg is None:
                    break

                if msg['arbitration_id'] in relevant_message_ids:
                    try:
                        decoded_signals = db.decode_message(msg['arbitration_id'], msg['data'], allow_truncated=True)

                        # --- START INTENSE DEBUGGING ---
                        # This intense debug block will now write to the worker's own log file
                        print(f"\n--- [DEBUG WORKER {worker_id}] ---")
                        print(f"Processing Message ID: 0x{msg['arbitration_id']:X}")
                        print(f"Monitored signals for this worker: {signals_to_log}")
                        print(f"Decoded signals from cantools: {decoded_signals.keys()}")
                        for name in decoded_signals.keys():
                            is_in_set = name in signals_to_log
                            print(f"  - Checking signal: {repr(name)}")
                            print(f"    - Is in monitored set? {is_in_set}")
                            if not is_in_set:
                                for s in signals_to_log:
                                    if s.strip() == name.strip():
                                        print(f"    - NEAR MATCH FOUND! Monitored: {repr(s)}, Decoded: {repr(name)}")
                        print(f"--- [END DEBUG] ---\n")
                        # --- END INTENSE DEBUGGING ---

                        for name, physical_value in decoded_signals.items():
                            if name in signals_to_log:
                                final_value = physical_value
                                if not isinstance(physical_value, (int, float)):
                                    final_value = getattr(physical_value, 'value', 0)

                                log_entry = {
                                    "timestamp": float(msg['timestamp']),
                                    "message_id": msg['arbitration_id'],
                                    "signal": name,
                                    "value": float(final_value)
                                }
                                results_queue.put(log_entry)
                                local_logged_signals.add(name)
                                print(f"Logged signal: {name}")


                    except Exception as e:
                        print(f"[WORKER {worker_id}] Failed to decode message ID 0x{msg['arbitration_id']:x}: {e}")
                        continue
    
    except KeyboardInterrupt:
        pass
    finally:
        if worker_signals_queue:
            worker_signals_queue.put(local_logged_signals)


class TestDualPipelineSimulation(unittest.TestCase):

    def setUp(self):
        """Set up the test environment."""
        self.log_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../test_data/2w_sample.log'))
        self.dbc_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../test_data/tst_input/VCU.dbc'))
        self.signal_list_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../test_data/tst_input/master_sigList.txt'))

        # Ensure files exist
        self.assertTrue(os.path.exists(self.log_file_path), f"Log file not found: {self.log_file_path}")
        self.assertTrue(os.path.exists(self.dbc_path), f"DBC file not found: {self.dbc_path}")
        self.assertTrue(os.path.exists(self.signal_list_path), f"Signal list not found: {self.signal_list_path}")

    def test_low_frequency_signals_are_processed(self):
        """
        Simulates the dual-pipeline CAN logger to verify that low-frequency
        signals are processed correctly from a log file.
        """
        # 1. Setup logging directories and paths
        output_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../test_data'))
        os.makedirs(output_base_dir, exist_ok=True)
        
        # Define separate log files for each worker
        hf_log_path = os.path.join(output_base_dir, "worker_1_high_freq.log")
        lf_log_path = os.path.join(output_base_dir, "worker_2_low_freq.log")
        main_log_path = os.path.join(output_base_dir, "console_output.log")

        original_stdout = sys.stdout
        original_stderr = sys.stderr
        log_file = None

        try:
            # Main test output will go to console_output.log
            log_file = open(main_log_path, 'w', buffering=1)
            sys.stdout = log_file
            sys.stderr = log_file
            print(f"[INFO] Main test output redirected to: {main_log_path}")
            print(f"[INFO] High-frequency worker log: {hf_log_path}")
            print(f"[INFO] Low-frequency worker log: {lf_log_path}")

            # 1. Load DBC and signal lists
            db = cantools.database.load_file(self.dbc_path)
            
            high_freq_monitored_signals = set()
            low_freq_monitored_signals = set()
            
            high_freq_msg_ids = {154, 155, 160, 161, 162, 173}
            low_freq_msg_ids = {782, 783, 784} # 0x310 is 784

            with open(self.signal_list_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) == 3:
                        msg_id_hex, signal_name, cycle_time_str = parts
                        cycle_time = int(cycle_time_str)
                        if cycle_time == 10:
                            high_freq_monitored_signals.add(signal_name.strip())
                        elif cycle_time == 100:
                            low_freq_monitored_signals.add(signal_name.strip())

            self.assertTrue(len(low_freq_monitored_signals) > 0, "No low-frequency signals found in master_sigList.txt")

            # 2. Create multiprocessing queues
            high_freq_raw_queue = multiprocessing.Queue()
            low_freq_raw_queue = multiprocessing.Queue()
            log_queue = multiprocessing.Queue()
            worker_signals_queue = multiprocessing.Queue()
            manager = multiprocessing.Manager()
            live_data_dict = manager.dict()
            perf_tracker = manager.dict()
            can_logger_ready = multiprocessing.Event()
            shutdown_flag = multiprocessing.Event()

            # 3. Start worker processes with the DEBUG worker and dedicated log files
            high_freq_worker = multiprocessing.Process(
                target=_debug_processing_worker,
                args=(1, db, high_freq_monitored_signals, high_freq_raw_queue, log_queue, perf_tracker, hf_log_path, live_data_dict, can_logger_ready, shutdown_flag, worker_signals_queue)
            )
            low_freq_worker = multiprocessing.Process(
                target=_debug_processing_worker,
                args=(2, db, low_freq_monitored_signals, low_freq_raw_queue, log_queue, perf_tracker, lf_log_path, live_data_dict, can_logger_ready, shutdown_flag, worker_signals_queue)
            )
            
            workers = [high_freq_worker, low_freq_worker]
            for w in workers:
                w.start()

            # 4. Parse and dispatch log messages
            log_messages = list(parse_busmaster_log(self.log_file_path))
            self.assertTrue(len(log_messages) > 0, "Log file parsing yielded no messages.")

            for msg in log_messages:
                msg_dict = {'arbitration_id': msg.arbitration_id, 'data': msg.data, 'timestamp': msg.timestamp}
                if msg.arbitration_id in high_freq_msg_ids:
                    high_freq_raw_queue.put(msg_dict)
                elif msg.arbitration_id in low_freq_msg_ids:
                    low_freq_raw_queue.put(msg_dict)
            
            # Give workers time to process messages before sending shutdown signal
            time.sleep(2) 

            # 5. Collect results
            shutdown_flag.set()
            
            processed_signals = defaultdict(list)
            
            # Add sentinels to ensure workers exit if they are waiting on an empty queue
            high_freq_raw_queue.put(None)
            low_freq_raw_queue.put(None)

            for w in workers:
                w.join(timeout=2)
                if w.is_alive():
                    w.terminate()
                    w.join()

            while not log_queue.empty():
                try:
                    log_entry = log_queue.get_nowait()
                    if log_entry:
                        processed_signals[log_entry["signal"]].append(log_entry["value"])
                except Exception:
                    break
            
            # 6. Assertions
            print("\n--- Processed Signals ---")
            for sig, vals in processed_signals.items():
                print(f"- {sig}: Found {len(vals)} values.")
            
            print("\n--- Monitored Low-Frequency Signals ---")
            for sig in low_freq_monitored_signals:
                print(f"- {sig}")

            for signal_name in low_freq_monitored_signals:
                if signal_name not in processed_signals:
                    print(f"[WARNING] Monitored low-frequency signal '{signal_name}' was not found in the processed output.")
                else:
                    self.assertGreater(len(processed_signals[signal_name]), 0, f"Low-frequency signal '{signal_name}' was processed, but has no values.")

        finally:
            # Restore original stdout and stderr
            if log_file:
                log_file.close()
            sys.stdout = original_stdout
            sys.stderr = original_stderr
