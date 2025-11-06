# log_writer.py

import threading
import queue
import json
import time
import struct
from can_logger_app import config
import logging

# Configure a basic logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

import logging

logger = logging.getLogger(__name__)

LOG_ENTRY_FORMAT = struct.Struct('=dI32sd')

class LogWriter(threading.Thread):
    def __init__(self, log_queue, filepath, perf_tracker, batch_size=1000):
        super().__init__(daemon=True)
        self.log_queue = log_queue
        self.filepath = filepath
        self.perf_tracker = perf_tracker
        self.batch_size = batch_size
        self._is_running = threading.Event()

    def run(self):
        self._is_running.set()
        
        with open(self.filepath, 'a') as log_file:
            while self._is_running.is_set() or not self.log_queue.empty():
                write_batch = []
                while len(write_batch) < self.batch_size:
                    try:
                        log_entry = self.log_queue.get(timeout=0.01)
                        
                        if config.DEBUG_PRINTING:
                            logger.debug(f"[LOG WRITER] Dequeued: {log_entry}")

                        # The worker now sends a dict to signal its logged signals
                        # We need to filter those out
                        if isinstance(log_entry, dict) and "worker_signals" in log_entry:
                            # In the future, we might want to do something with this
                            continue

                        # Re-format the entry for JSON logging
                        formatted_entry = {
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(log_entry["timestamp"])) + f".{int((log_entry["timestamp"] % 1) * 1e6):06d}",
                            "message_id": f"0x{log_entry['message_id']:x}",
                            "signal": log_entry["signal"],
                            "value": log_entry["value"]
                        }
                        if config.DEBUG_PRINTING:
                            logger.debug(f"[LOG WRITER] Writing: {formatted_entry}")
                        write_batch.append(formatted_entry)

                    except queue.Empty:
                        break
                
                if write_batch:
                    start_time = time.perf_counter()
                    log_lines = [json.dumps(entry) + '\n' for entry in write_batch]
                    log_file.writelines(log_lines)
                    end_time = time.perf_counter()
                    
                    duration = end_time - start_time
                    self.perf_tracker['log_write_total_time'] = self.perf_tracker.get('log_write_total_time', 0) + duration
                    self.perf_tracker['log_write_batch_count'] = self.perf_tracker.get('log_write_batch_count', 0) + 1

    def stop(self):
        self._is_running.clear()