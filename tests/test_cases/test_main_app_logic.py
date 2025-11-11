
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

    def setUp(self):
        """Ensure necessary input files exist."""
        self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
        self.input_dir = os.path.join(self.root_dir, 'input')
        self.dbc_path = os.path.join(self.input_dir, 'VCU.dbc')
        self.signal_list_path = os.path.join(self.input_dir, 'master_sigList.txt')
        self.log_file_path = os.path.join(self.root_dir, 'tests', 'test_data', '2w_sample.log')

        self.assertTrue(os.path.exists(self.dbc_path), "VCU.dbc not found in input directory")
        self.assertTrue(os.path.exists(self.signal_list_path), "master_sigList.txt not found in input directory")
        self.assertTrue(os.path.exists(self.log_file_path), "2w_sample.log not found in test_data directory")

    @unittest.mock.patch('can.interface.Bus')
    def test_dual_pipeline_from_log_file(self, mock_bus_class):
        """
        Tests the main application's dual-pipeline logic using a log file.
        """
        # 1. Mock the CAN Bus to play back messages from the log file
        log_messages = list(parse_busmaster_log_for_test(self.log_file_path))
        self.assertGreater(len(log_messages), 0, "Log file parsing yielded no messages.")
        
        # The mock bus will return a message on each recv() call
        mock_bus_instance = unittest.mock.MagicMock()
        mock_bus_instance.recv.side_effect = log_messages + [None]*10 # Add Nones to terminate loop
        mock_bus_class.return_value = mock_bus_instance

        # 2. Load configuration (same as main app)
        db = cantools.database.load_file(self.dbc_path)
        high_freq_signals, low_freq_signals, id_to_queue_map = utils.load_signals_to_monitor(self.signal_list_path)
        
        high_freq_monitored_signals = {s for sig_set in high_freq_signals.values() for s in sig_set}
        low_freq_monitored_signals = {s for sig_set in low_freq_signals.values() for s in sig_set}

        self.assertGreater(len(high_freq_monitored_signals), 0, "No high-frequency signals loaded.")
        self.assertGreater(len(low_freq_monitored_signals), 0, "No low-frequency signals loaded.")

        # 3. Set up the dual-pipeline architecture
        manager = multiprocessing.Manager()
        high_freq_raw_queue = multiprocessing.Queue()
        low_freq_raw_queue = multiprocessing.Queue()
        log_queue = multiprocessing.Queue()
        worker_signals_queue = multiprocessing.Queue()
        perf_tracker = manager.dict()
        shutdown_flag = multiprocessing.Event()

        # 4. Start the CANReader thread
        # This thread will read from the mocked bus and dispatch to the two queues
        connection_event = threading.Event()
        dispatcher_thread = CANReader(
            bus_params={'interface': 'mock'}, # Params don't matter due to mock
            data_queues={'high': high_freq_raw_queue, 'low': low_freq_raw_queue},
            id_to_queue_map=id_to_queue_map,
            perf_tracker=perf_tracker,
            connection_event=connection_event,
            shutdown_flag=shutdown_flag
        )
        dispatcher_thread.start()
        connection_event.set() # Manually set event as we are not really connecting

        # 5. Start the worker pools
        high_freq_processes = []
        for i in range(can_logger_config.NUM_HIGH_FREQ_WORKERS):
            p = multiprocessing.Process(
                target=processing_worker,
                args=(i, db, high_freq_monitored_signals, high_freq_raw_queue, log_queue, perf_tracker, None, None, shutdown_flag, worker_signals_queue),
                daemon=True
            )
            high_freq_processes.append(p)
            p.start()

        low_freq_processes = []
        for i in range(can_logger_config.NUM_LOW_FREQ_WORKERS):
            p = multiprocessing.Process(
                target=processing_worker,
                args=(i + can_logger_config.NUM_HIGH_FREQ_WORKERS, db, low_freq_monitored_signals, low_freq_raw_queue, log_queue, perf_tracker, None, None, shutdown_flag, worker_signals_queue),
                daemon=True
            )
            low_freq_processes.append(p)
            p.start()

        # 6. Wait for processing to complete
        # Give the system enough time to process all messages from the log file
        time.sleep(5) 

        # 7. Shut down gracefully
        shutdown_flag.set()

        dispatcher_thread.join(timeout=2)
        for p in high_freq_processes + low_freq_processes:
            p.join(timeout=2)

        # 8. Aggregate results
        logged_signals_set = set()
        while not worker_signals_queue.empty():
            try:
                signal_set = worker_signals_queue.get_nowait()
                logged_signals_set.update(signal_set)
            except queue.Empty:
                break
        
        # 9. Assertions
        print(f"\n--- Test Results ---")
        print(f"Signals logged: {logged_signals_set}")
        
        # Check for a known high-frequency signal
        self.assertIn('ETS_MOT_ShaftTorque_Est_Nm', logged_signals_set, "A known high-frequency signal was not logged.")
        
        # Check for a known low-frequency signal
        self.assertIn('ETS_VCU_VehSpeed_Act_kmph', logged_signals_set, "A known low-frequency signal was not logged.")
        
        print("Both high and low frequency signals were successfully logged.")
        print("--------------------\n")


if __name__ == '__main__':
    unittest.main()
