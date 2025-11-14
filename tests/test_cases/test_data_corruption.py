
import unittest
import multiprocessing
import time
import locale
import os
import sys

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

# --- Constants ---
RACE_CONDITION_SIGNAL_NAME = 'TestSignal_Race'
LOCALE_TEST_SIGNAL_NAME = 'TestSignal_Locale'
NUM_WRITERS = 4
TEST_DURATION_SECONDS = 2.0
FLOAT_VALUE_FOR_LOCALE_TEST = 123.45

# --- Mock Processes for Race Condition Test ---

def race_condition_writer_process(shared_dict, shutdown_flag, process_id, use_lock, lock):
    """
    A process that rapidly writes its own ID to a specific key in a shared dictionary.
    It can optionally use a lock to protect the write operation.
    """
    print(f"[Writer {process_id}] Starting. Use lock: {use_lock}", flush=True)
    
    while not shutdown_flag.is_set():
        current_time = time.time()
        
        if use_lock:
            with lock:
                shared_dict[RACE_CONDITION_SIGNAL_NAME] = (float(process_id), current_time)
        else:
            shared_dict[RACE_CONDITION_SIGNAL_NAME] = (float(process_id), current_time)
        
        time.sleep(0.001)

    print(f"[Writer {process_id}] Finished.", flush=True)

def race_condition_reader_process(shared_dict, shutdown_flag, writer_ids_seen):
    """
    A process that reads from the shared dictionary and records which writer IDs it sees.
    """
    print("[Reader] Starting.", flush=True)
    
    while not shutdown_flag.is_set():
        if RACE_CONDITION_SIGNAL_NAME in shared_dict:
            try:
                value_tuple = shared_dict[RACE_CONDITION_SIGNAL_NAME]
                if value_tuple and isinstance(value_tuple, (list, tuple)) and len(value_tuple) > 0:
                    process_id = int(value_tuple[0])
                    if process_id not in writer_ids_seen:
                        writer_ids_seen.append(process_id)
            except (KeyError, TypeError):
                pass
        time.sleep(0.005)

    print(f"[Reader] Finished. Saw IDs: {sorted(list(writer_ids_seen))}", flush=True)





class TestDataCorruption(unittest.TestCase):

    def _run_test_in_subprocess(self, test_name):
        """Helper function to run a specific test from the runner script."""
        import subprocess

        runner_script_path = os.path.join(os.path.dirname(__file__), '..', 'lib', 'data_corruption_test_runner.py')
        self.assertTrue(os.path.exists(runner_script_path), f"Test runner script not found at {runner_script_path}")

        try:
            result = subprocess.run(
                [sys.executable, runner_script_path, f'--test={test_name}'],
                capture_output=True,
                text=True,
                check=True,
                timeout=20
            )
            print(f"\n--- Subprocess Output for {test_name} ---")
            print(result.stdout)
            if result.stderr:
                print(f"--- Subprocess Stderr for {test_name} ---")
                print(result.stderr)
            print("-------------------------------------------\n")
        except subprocess.CalledProcessError as e:
            self.fail(
                f"The isolated test '{test_name}' failed with exit code {e.returncode}.\n"
                f"--- STDOUT ---\n{e.stdout}\n"
                f"--- STDERR ---\n{e.stderr}"
            )
        except subprocess.TimeoutExpired as e:
            self.fail(
                f"The isolated test '{test_name}' timed out.\n"
                f"--- STDOUT ---\n{e.stdout}\n"
                f"--- STDERR ---\n{e.stderr}"
            )

    def test_race_condition_without_lock(self):
        """
        Demonstrates that without a lock, concurrent writes lead to data loss.
        This test runs in an isolated process.
        """
        self._run_test_in_subprocess('without_lock')

    def test_race_condition_with_lock(self):
        """
        Verifies that using a lock prevents data loss from concurrent writes.
        This test runs in an isolated process.
        """
        self._run_test_in_subprocess('with_lock')


if __name__ == '__main__':
    unittest.main()
