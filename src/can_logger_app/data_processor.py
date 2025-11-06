# data_processor.py

import can
import time
import struct
import queue

from can_logger_app import config

import logging

logger = logging.getLogger(__name__)

LOG_ENTRY_FORMAT = struct.Struct('=dI32sd')

def processing_worker(worker_id, decoding_rules, raw_queue, results_queue, perf_tracker, live_data_dict=None, can_logger_ready=None):
    """
    MODIFIED: Now accepts an optional 'live_data_dict' (a Manager.dict())
    to share the latest signal values with another process.
    MODIFIED: Now accepts 'can_logger_ready' (a multiprocessing.Event) to signal when the first data is ready.
    MODIFIED: Now puts the entire log entry dictionary into the results_queue instead of using shared memory.
    """
    local_logged_signals = set()

    try:
        while True:
            msg = raw_queue.get()

            if msg is None:
                break

            if not isinstance(msg, can.Message):
                continue
            
            start_time = time.perf_counter()

            if msg.arbitration_id in decoding_rules:
                rules = decoding_rules[msg.arbitration_id]
                data_int = int.from_bytes(msg.data, byteorder='little')
                
                for name, is_signed, start, length, scale, offset in rules:
                    shifted = data_int >> start
                    mask = (1 << length) - 1
                    raw_value = shifted & mask

                    if is_signed:
                        if raw_value & (1 << (length - 1)):
                            raw_value -= (1 << length)

                    physical_value = float((raw_value * scale) + offset)
                    
                    # --- 1. Create the log entry --- 
                    log_entry = {
                        "timestamp": float(msg.timestamp),
                        "message_id": msg.arbitration_id,
                        "signal": name,
                        "value": physical_value
                    }
                    if config.DEBUG_PRINTING:
                        logger.debug(f"[WORKER {worker_id}] Queueing: {log_entry}")
                    results_queue.put(log_entry)
                    
                    # --- 2. Share for live radar (existing logic) --- 
                    if live_data_dict is not None:
                        current_buffer = live_data_dict.get(name, [])
                        current_buffer.append((float(msg.timestamp), physical_value))
                        live_data_dict[name] = current_buffer[-10:]

                        if can_logger_ready and not can_logger_ready.is_set():
                            can_logger_ready.set()

                    local_logged_signals.add(name)

                end_time = time.perf_counter()
                duration = (end_time - start_time)
                perf_tracker['processing_total_time'] = perf_tracker.get('processing_total_time', 0) + duration
                perf_tracker['processing_msg_count'] = perf_tracker.get('processing_msg_count', 0) + 1

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error in worker {worker_id}: {e}")
    finally:
        # Put the locally tracked signals into the main results queue for aggregation
        # This is a bit of a hack, we'll send a dict to distinguish it
        results_queue.put({"worker_signals": local_logged_signals})