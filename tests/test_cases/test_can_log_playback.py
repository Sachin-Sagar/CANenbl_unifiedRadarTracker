import unittest
from unittest.mock import MagicMock, patch
import time
import os
import sys
import queue
import numpy as np
import can
import datetime

# Add src to path to allow for relative imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../lib')))


import config as root_config

def parse_busmaster_log(file_path):
    """
    Parses a BUSMASTER log file and yields can.Message objects.
    Assumes the log format: <Time><Tx/Rx><Channel><CAN ID><Type><DLC><DataBytes>
    Example: 11:42:34:1151 Rx 1 0x096 s 8 03 10 40 04 80 00 00 00
    """
    start_datetime = None
    first_message_timestamp_s = None

    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('***'):
                # Skip empty lines and header lines
                continue

            parts = line.split()
            if len(parts) < 7:
                # Skip malformed lines
                continue

            try:
                # Parse timestamp (e.g., 11:42:34:1151)
                time_str = parts[0]
                time_parts = time_str.split(':')
                h, m, s, ms = map(int, time_parts)
                
                current_message_time_s = h * 3600 + m * 60 + s + ms / 1000.0

                if first_message_timestamp_s is None:
                    first_message_timestamp_s = current_message_time_s
                    # Use current system time as a base for the first message
                    base_timestamp = time.time()
                
                # Calculate relative timestamp for can.Message
                timestamp = base_timestamp + (current_message_time_s - first_message_timestamp_s)

                arbitration_id = int(parts[3], 16)
                is_extended_id = (parts[4] == 'e') # 's' for standard, 'e' for extended
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


class TestCANLogPlayback(unittest.TestCase):

    def setUp(self):
        # Create dummy input files for DBC and signal list
        os.makedirs(root_config.INPUT_DIRECTORY, exist_ok=True)
        
        # Example DBC content (simplified for testing)
        dbc_content = """
BO_ 150 VCU_Feedback: 8 Vector__XXX
 SG_ VCU_Speed : 8|16@1+ (0.1,0) [0|25.5] "km/h" Vector__XXX
 SG_ VCU_Torque : 24|16@1+ (0.1,0) [0|1000] "Nm" Vector__XXX
        """
        with open(os.path.join(root_config.INPUT_DIRECTORY, root_config.DBC_FILE), 'w') as f:
            f.write(dbc_content)
        
        # Example signal list content
        signal_list_content = """
0x96,VCU_Speed,10
0x96,VCU_Torque,10
        """
        with open(os.path.join(root_config.INPUT_DIRECTORY, root_config.SIGNAL_LIST_FILE), 'w') as f:
            f.write(signal_list_content)

        self.log_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../test_data/2w_sample.log'))

    @patch('can.interface.Bus')
    def test_can_log_playback(self, mock_bus_class):
        """Test CAN service integration with a log file playback."""
        
        # --- Mocking the CAN Bus with custom parser ---
        try:
            log_messages = list(parse_busmaster_log(self.log_file_path))
            
            def message_generator():
                for msg in log_messages:
                    yield msg
                while True:
                    yield None

            mock_bus_class.return_value.recv.side_effect = message_generator()
        except Exception as e:
            self.fail(f"Failed to parse log file {self.log_file_path}: {e}")

        # --- Setup LiveCANManager ---
        dbc_path = os.path.join(root_config.INPUT_DIRECTORY, root_config.DBC_FILE)
        signal_list_path = os.path.join(root_config.INPUT_DIRECTORY, root_config.SIGNAL_LIST_FILE)
        
        mock_config = MagicMock()
        mock_config.DEBUG_PRINTING = False
        mock_config.OS_SYSTEM = "Linux"
        mock_config.CAN_CHANNEL = "can0"
        mock_config.CAN_BITRATE = 500000
        mock_config.CAN_INTERFACE = "socketcan"

        with patch.dict('sys.modules', {'config': mock_config}):
            # Reload utils to make sure it picks up the mocked config
            import importlib
            from src.can_service import utils
            importlib.reload(utils)

            # Import the fixed manager here so it and its dependencies
            # are loaded with the mocked config module.
            from live_can_manager_fixed import LiveCANManager
            
            can_manager = LiveCANManager(mock_config, dbc_path, signal_list_path)
            can_manager.start()

            # Give time for the CAN messages to be processed.
            time.sleep(2) # Wait for threads to process some messages

            # --- Assertions ---
            can_buffers = can_manager.get_signal_buffers()
            self.assertTrue(can_buffers, "CAN signal buffers should not be empty.")
            self.assertIn('VCU_Speed', can_buffers)
            self.assertGreater(len(can_buffers['VCU_Speed']), 0, "VCU_Speed buffer should not be empty.")
            
            # --- Shutdown ---
            can_manager.stop()

if __name__ == '__main__':
    unittest.main()
