# log_writer.py

import threading
import queue
import json
import time
import struct
import logging

# Configure a basic logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

LOG_ENTRY_FORMAT = struct.Struct('=dI32sd')

class LogWriter(threading.Thread):
    def __init__(self, index_queue, shared_mem_array, filepath, perf_tracker, batch_size=1000):
        super().__init__(daemon=True)
        self.index_queue = index_queue
        self.shared_mem_array = shared_mem_array
        self.filepath = filepath
        self.perf_tracker = perf_tracker
        self.batch_size = batch_size
        self._is_running = threading.Event()

    def run(self):
        self._is_running.set()
        
        with open(self.filepath, 'a') as log_file:
            while self._is_running.is_set() or not self.index_queue.empty():
                write_batch = []
                while len(write_batch) < self.batch_size:
                    try:
                        slot_index = self.index_queue.get(timeout=0.01)
                        
                        offset = slot_index * LOG_ENTRY_FORMAT.size
                        ts, can_id, sig_name_bytes, value = LOG_ENTRY_FORMAT.unpack_from(
                            self.shared_mem_array, offset
                        )

                        sig_name = sig_name_bytes.strip(b'\x00').decode('utf-8')
                        
                        logger.debug(f"Original value from shared memory: {value} (type: {type(value)})")
                        casted_value = float(value)
                        logger.debug(f"Casted value: {casted_value} (type: {type(casted_value)})")
                        
                        log_entry = {
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(ts)) + f".{int((ts % 1) * 1e6):06d}",
                            "message_id": f"0x{can_id:x}",
                            "signal": sig_name,
                            "value": casted_value
                        }
                        logger.debug(f"Final log entry: {log_entry}")
                        write_batch.append(log_entry)

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