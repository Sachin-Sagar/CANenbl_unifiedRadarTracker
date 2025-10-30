# data_processor.py

import can
import time
import struct
import queue



def processing_worker(worker_id, decoding_rules, raw_queue, output_queue, perf_tracker):

    local_logged_signals = set()



    try:

        while True:

            msg = raw_queue.get()



            if msg is None:

                # Sentinel value to stop the worker

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

                    

                    output_queue.put((msg.timestamp, name, physical_value))

                    local_logged_signals.add(name)



                end_time = time.perf_counter()

                duration = (end_time - start_time)

                perf_tracker['processing_total_time'] = perf_tracker.get('processing_total_time', 0) + duration

                perf_tracker['processing_msg_count'] = perf_tracker.get('processing_msg_count', 0) + 1



    except KeyboardInterrupt:

        pass

    except Exception as e:

        print(f"Error in worker {worker_id}: {e}")
