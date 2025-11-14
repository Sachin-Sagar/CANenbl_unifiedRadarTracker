
import unittest
from unittest.mock import MagicMock, patch
import time
import os
import can

# Add src to path to allow for relative imports
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../lib')))

import config as root_config

class TestCANService(unittest.TestCase):

    def setUp(self):
        # Create dummy input files
        os.makedirs(root_config.INPUT_DIRECTORY, exist_ok=True)
        with open(os.path.join(root_config.INPUT_DIRECTORY, root_config.DBC_FILE), 'w') as f:
            f.write("BO_ 2295333120 VCU_Feedback: 8 VCU\n SG_ VCU_Speed : 8|16@1- (0.1,0) [0|25.5] \"km/h\" Vector__XXX\n")
        with open(os.path.join(root_config.INPUT_DIRECTORY, root_config.SIGNAL_LIST_FILE), 'w') as f:
            f.write("0x8D00100,VCU_Speed,10\n")

    def test_can_service_integration(self):
        """
        Sanity check for the CAN service integration.
        This test runs its logic in a separate process to avoid a
        PicklingError related to multiprocessing.Manager and the unittest runner.
        """
        import subprocess

        runner_script_path = os.path.join(os.path.dirname(__file__), '..', 'lib', 'can_service_test_runner.py')
        self.assertTrue(os.path.exists(runner_script_path), f"Test runner script not found at {runner_script_path}")

        try:
            # Execute the test runner script in a clean python interpreter process.
            # We use sys.executable to ensure it uses the same python environment.
            # `check=True` will raise a CalledProcessError if the script returns a non-zero exit code.
            result = subprocess.run(
                [sys.executable, runner_script_path],
                capture_output=True,
                text=True,
                check=True,
                timeout=20 # Add a timeout to prevent hangs
            )
            # Print the output from the script for debugging purposes, even on success
            print("\n--- Subprocess Output ---")
            print(result.stdout)
            if result.stderr:
                print("--- Subprocess Stderr ---")
                print(result.stderr)
            print("-------------------------\n")

        except subprocess.CalledProcessError as e:
            # The script exited with a non-zero code, meaning an assertion or other error occurred.
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
    # Need to import numpy for the test
    import numpy as np
    unittest.main()
