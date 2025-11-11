# data_processor.py

import can
import time
import struct
import queue

from can_logger_app import config

import logging

logger = logging.getLogger(__name__)

LOG_ENTRY_FORMAT = struct.Struct('=dI32sd')

def processing_worker(worker_id, db, signals_to_log, raw_queue, results_queue, perf_tracker, live_data_dict=None, can_logger_ready=None, shutdown_flag=None, worker_signals_queue=None):
    """
    MODIFIED: Accepts 'db' (cantools database object) and 'signals_to_log' (a set) instead of 'decoding_rules'.
    MODIFIED: Uses db.decode_message() for robust CAN signal decoding.
    MODIFIED: Now accepts an optional 'live_data_dict' (a Manager.dict())
    to share the latest signal values with another process.
    MODIFIED: Now accepts 'can_logger_ready' (a multiprocessing.Event) to signal when the first data is ready.
    MODIFIED: Now puts the entire log entry dictionary into the results_queue.
    MODIFIED: Now accepts a 'shutdown_flag' (a multiprocessing.Event) to signal when to stop processing.
    MODIFIED: Now accepts a 'worker_signals_queue' to send the final set of logged signals.
    """
    local_logged_signals = set()
    
    # Create a set of message IDs this worker should process based on the signals it's logging.
    # This is a performance optimization to avoid trying to decode messages that contain no relevant signals.
    relevant_message_ids = {
        message.frame_id for message in db.messages 
        if any(signal.name in signals_to_log for signal in message.signals)
    }

    try:
        while not (shutdown_flag and shutdown_flag.is_set()):
            try:
                msg = raw_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if msg is None:
                break

            # Optimization: check if the message ID is relevant before attempting to decode
            if msg['arbitration_id'] in relevant_message_ids:
                start_time = time.perf_counter()
                try:
                    # Use cantools to decode the entire message at once
                    # MODIFICATION: Allow decoding of truncated frames, as seen in some logs.
                    decoded_signals = db.decode_message(msg['arbitration_id'], msg['data'], allow_truncated=True)

                    for name, physical_value in decoded_signals.items():
                        # Only process signals that are in our master list
                        if name in signals_to_log:
                            
                            # MODIFICATION: Handle cantools 'NamedSignalValue' for enums
                            final_value = physical_value
                            if not isinstance(physical_value, (int, float)):
                                # It's likely a NamedSignalValue, get its numerical value
                                final_value = getattr(physical_value, 'value', 0)

                            # --- 1. Create the log entry --- 
                            log_entry = {
                                "timestamp": float(msg['timestamp']),
                                "message_id": msg['arbitration_id'],
                                "signal": name,
                                "value": float(final_value) # Ensure native Python float
                            }
                            if config.DEBUG_PRINTING:
                                logger.debug(f"[WORKER {worker_id}] Queueing: {log_entry}")
                            results_queue.put(log_entry)
                            
                            # --- 2. Share for live radar --- 
                            if live_data_dict is not None:
                                # Use a simple list as the buffer
                                buffer = live_data_dict.get(name, [])
                                buffer.append((float(msg['timestamp']), float(final_value)))
                                # Keep the buffer trimmed to the last 10 values
                                live_data_dict[name] = buffer[-10:]

                                if can_logger_ready and not can_logger_ready.is_set():
                                    can_logger_ready.set()

                            local_logged_signals.add(name)

                    end_time = time.perf_counter()
                    duration = (end_time - start_time)
                    perf_tracker['processing_total_time'] = perf_tracker.get('processing_total_time', 0) + duration
                    perf_tracker['processing_msg_count'] = perf_tracker.get('processing_msg_count', 0) + 1

                except Exception as e:
                    # This might happen with malformed data or DBC inconsistencies
                    logger.warning(f"[WORKER {worker_id}] Failed to decode message ID 0x{msg['arbitration_id']:x}: {e}")
                    continue

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error in worker {worker_id}: {e}")
    finally:
        # Put the locally tracked signals into the dedicated worker signals queue for aggregation
        if worker_signals_queue:
            worker_signals_queue.put(local_logged_signals)