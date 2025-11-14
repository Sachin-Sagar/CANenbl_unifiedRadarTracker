
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

    def test_low_frequency_signals_are_processed(self):
        """
        Simulates the dual-pipeline CAN logger in an isolated process
        to verify that low-frequency signals are processed correctly.
        """
        import subprocess

        runner_script_path = os.path.join(os.path.dirname(__file__), '..', 'lib', 'dual_pipeline_test_runner.py')
        self.assertTrue(os.path.exists(runner_script_path), f"Test runner script not found at {runner_script_path}")

        try:
            result = subprocess.run(
                [sys.executable, runner_script_path],
                capture_output=True,
                text=True,
                check=True,
                timeout=20
            )
            print("\n--- Subprocess Output ---")
            print(result.stdout)
            if result.stderr:
                print("--- Subprocess Stderr ---")
                print(result.stderr)
            print("-------------------------\n")

        except subprocess.CalledProcessError as e:
            self.fail(
                f"The isolated test process failed with exit code {e.returncode}.\n"
                f"--- STDOUT ---\n{e.stdout}\n"
                f"--- STDERR ---\n{e.stderr}"
            )
        except subprocess.TimeoutExpired as e:
            self.fail(
                f"The isolated test process timed out.\n"
                f"--- STDOUT ---\n{e.stdout}\n"
                f"--- STDERR ---\n{e.stderr}"
            )
