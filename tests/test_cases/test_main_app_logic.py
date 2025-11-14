
import unittest
from unittest import mock
import os
import sys
import multiprocessing
import threading
import time
import cantools
import can
import queue

# Add project root to path to allow for absolute imports from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.can_logger_app import config as can_logger_config
from src.can_logger_app import utils
from src.can_logger_app.can_handler import CANReader
from src.can_logger_app.data_processor import processing_worker
from src.can_logger_app.log_writer import LogWriter

def parse_busmaster_log_for_test(file_path):
    """
    Parses a BUSMASTER log file and yields can.Message objects.
    This is a copy from the other test to make this script self-contained.
    """
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
                h, m, s, ms_micro = time_str.split(':')
                # Fake a timestamp starting from the Unix epoch for simplicity
                timestamp = int(h) * 3600 + int(m) * 60 + int(s) + int(ms_micro) / 10000.0

                arbitration_id = int(parts[3], 16)
                data = bytearray([int(b, 16) for b in parts[6:]])

                message = can.Message(
                    timestamp=timestamp,
                    arbitration_id=arbitration_id,
                    is_extended_id=False,
                    dlc=len(data),
                    data=data
                )
                yield message
            except (ValueError, IndexError):
                continue

class TestMainAppLogic(unittest.TestCase):

    def test_dual_pipeline_from_log_file(self):
        """
        Tests the main application's dual-pipeline logic in an isolated process.
        """
        import subprocess

        runner_script_path = os.path.join(os.path.dirname(__file__), '..', 'lib', 'main_app_logic_test_runner.py')
        self.assertTrue(os.path.exists(runner_script_path), f"Test runner script not found at {runner_script_path}")

        try:
            result = subprocess.run(
                [sys.executable, runner_script_path],
                capture_output=True,
                text=True,
                check=True,
                timeout=30
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


if __name__ == '__main__':
    unittest.main()
