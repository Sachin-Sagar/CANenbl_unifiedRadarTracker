# data_processor.py

import can
import time
import struct
import queue

LOG_ENTRY_FORMAT = struct.Struct('=dI32sd')

def processing_worker(worker_id, decoding_rules, raw_queue, index_queue, shared_mem_array, results_queue, perf_tracker, live_data_dict=None):
    """
    MODIFIED: Now accepts an optional 'live_data_dict' (a Manager.dict())
    to share the latest signal values with another process.
    """
    mem_view = memoryview(shared_mem_array)
    num_slots = len(shared_mem_array) // LOG_ENTRY_FORMAT.size
    current_slot = 0
    local_logged_signals = set()

    try:
        while True:
            msg = raw_queue.get()

            if msg is None:
                results_queue.put(local_logged_signals)
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

                    physical_value = (raw_value * scale) + offset
                    
                    # --- 1. Log to file (existing logic) ---
                    mem_offset = (current_slot % num_slots) * LOG_ENTRY_FORMAT.size
                    LOG_ENTRY_FORMAT.pack_into(
                        mem_view, mem_offset, msg.timestamp, msg.arbitration_id,
                        name.encode('utf-8'), physical_value
                    )
                    index_queue.put(current_slot % num_slots)
                    
                    # --- 2. Share for live radar (NEW LOGIC) ---
                    if live_data_dict is not None:
                        # We use a deque (via list slicing) to store the last 10 values
                        # This mimics the buffer from the old LiveCANManager
                        current_buffer = live_data_dict.get(name, [])
                        current_buffer.append((msg.timestamp, physical_value))
                        # Keep only the last 10 items
                        live_data_dict[name] = current_buffer[-10:]

                    current_slot += 1
                    local_logged_signals.add(name)

                end_time = time.perf_counter()
                duration = (end_time - start_time)
                perf_tracker['processing_total_time'] = perf_tracker.get('processing_total_time', 0) + duration
                perf_tracker['processing_msg_count'] = perf_tracker.get('processing_msg_count', 0) + 1

    except KeyboardInterrupt:
        results_queue.put(local_logged_signals)
    except Exception as e:
        print(f"Error in worker {worker_id}: {e}")
        results_queue.put(local_logged_signals)