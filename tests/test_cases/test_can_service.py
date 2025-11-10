
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

    @patch('can.interface.Bus')
    def test_can_service_integration(self, mock_bus):
        """Sanity check for the CAN service integration."""
        
        # --- Mocking the CAN Bus ---
        mock_bus.return_value.recv.side_effect = [
            can.Message(arbitration_id=0x8D00100, data=[0, 20, 0, 0, 0, 0, 0, 0], timestamp=time.time(), is_extended_id=True),
            can.Message(arbitration_id=0x8D00100, data=[0, 40, 0, 0, 0, 0, 0, 0], timestamp=time.time() + 0.1, is_extended_id=True),
            None
        ]

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
            import importlib
            from src.can_service import utils, can_handler
            importlib.reload(utils)
            importlib.reload(can_handler)
            from live_can_manager_fixed import LiveCANManager

            can_manager = LiveCANManager(mock_config, dbc_path, signal_list_path)
            can_manager.start()

            time.sleep(0.5) # Give time for the CAN messages to be processed

            # --- Mock RadarWorker getting data ---
            radar_timestamp_ms = (time.time() + 0.05) * 1000
            can_buffers = can_manager.get_signal_buffers()
            
            # --- Interpolation (simplified from RadarWorker) ---
            interp_value = None
            if 'VCU_Speed' in can_buffers:
                # Need to import numpy for this test
                import numpy as np
                buffer = can_buffers['VCU_Speed']
                timestamps = [item[0] for item in buffer]
                values = [item[1] for item in buffer]
                interp_value = np.interp(radar_timestamp_ms / 1000.0, timestamps, values)

            # --- Assertions ---
            self.assertIsNotNone(interp_value, "Interpolated value should not be None")
            self.assertAlmostEqual(interp_value, 3.0, delta=1.0, msg="Interpolated speed should be close to 3.0")

            # --- Shutdown ---
            can_manager.stop()

if __name__ == '__main__':
    # Need to import numpy for the test
    import numpy as np
    unittest.main()
