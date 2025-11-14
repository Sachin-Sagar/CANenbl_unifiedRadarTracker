
# tests/lib/can_service_test_runner.py
import time
import os
import sys
import can
import numpy as np
from unittest.mock import patch, MagicMock

# This script is designed to be run as a standalone process
# to avoid the PicklingError seen when running within the unittest suite.

def main():
    """
    Runs the core logic of the CAN service integration test.
    Exits with code 0 on success, 1 on failure.
    """
    # --- Setup Paths ---
    # Add project root to path to allow for absolute imports from src
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    # Add lib path for live_can_manager_fixed
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
    
    import config as root_config
    from live_can_manager_fixed import LiveCANManager

    print("[Test Runner] Starting CAN service integration test in isolated process...")

    # --- Mocking the CAN Bus ---
    mock_bus_patch = patch('can.interface.Bus')
    mock_bus = mock_bus_patch.start()
    mock_bus.return_value.recv.side_effect = [
        can.Message(arbitration_id=0x8D00100, data=[0, 20, 0, 0, 0, 0, 0, 0], timestamp=time.time(), is_extended_id=True),
        can.Message(arbitration_id=0x8D00100, data=[0, 40, 0, 0, 0, 0, 0, 0], timestamp=time.time() + 0.1, is_extended_id=True),
        None
    ]

    # --- Create a mock config object ---
    mock_config = MagicMock()
    mock_config.ENABLE_CONSOLE_LOGGING = False
    mock_config.DEBUG_FLAGS = {}
    mock_config.OS_SYSTEM = "Linux"
    mock_config.CAN_CHANNEL = "can0"
    mock_config.CAN_BITRATE = 500000
    mock_config.CAN_INTERFACE = "socketcan"
    mock_config.INPUT_DIRECTORY = root_config.INPUT_DIRECTORY
    mock_config.OUTPUT_DIRECTORY = root_config.OUTPUT_DIRECTORY
    mock_config.DBC_FILE = root_config.DBC_FILE
    mock_config.SIGNAL_LIST_FILE = root_config.SIGNAL_LIST_FILE

    # --- Setup and Run LiveCANManager ---
    dbc_path = os.path.join(root_config.INPUT_DIRECTORY, root_config.DBC_FILE)
    signal_list_path = os.path.join(root_config.INPUT_DIRECTORY, root_config.SIGNAL_LIST_FILE)

    # Use patch.dict to temporarily replace the config module
    with patch.dict('sys.modules', {'config': mock_config, 'src.can_service.config': mock_config}):
        import importlib
        from src.can_service import utils, can_handler
        importlib.reload(utils)
        importlib.reload(can_handler)
        
        # The manager is created here, in a clean process
        can_manager = LiveCANManager(mock_config, dbc_path, signal_list_path)
        can_manager.start()

        time.sleep(0.5)

        # --- Get and check data ---
        radar_timestamp_ms = (time.time() + 0.05) * 1000
        can_buffers = can_manager.get_signal_buffers()
        
        interp_value = None
        if 'VCU_Speed' in can_buffers:
            buffer = can_buffers['VCU_Speed']
            timestamps = [item[0] for item in buffer]
            values = [item[1] for item in buffer]
            interp_value = np.interp(radar_timestamp_ms / 1000.0, timestamps, values)

        # --- Shutdown ---
        can_manager.stop()
        mock_bus_patch.stop()

    # --- Assertions ---
    print(f"[Test Runner] Final interpolated value: {interp_value}")
    assert interp_value is not None, "Assertion Failed: Interpolated value should not be None"
    assert abs(interp_value - 4.0) < 0.1, f"Assertion Failed: Interpolated speed {interp_value} should be close to 4.0"
    
    print("[Test Runner] Assertions passed.")

if __name__ == '__main__':
    try:
        main()
        print("[Test Runner] Success: Test completed without errors.")
        sys.exit(0)
    except Exception as e:
        print(f"[Test Runner] Failure: An exception occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
