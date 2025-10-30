# can_handler.py

import can
import queue
import threading
import time
import config

class CANReader(threading.Thread):
    def __init__(self, bus, data_queues, id_to_queue_map, perf_tracker):
        super().__init__(daemon=True)
        self.bus = bus
        self.data_queues = data_queues
        self.id_to_queue_map = id_to_queue_map
        self.perf_tracker = perf_tracker
        self._is_running = threading.Event()
        self.messages_dropped = 0
        self.messages_received = 0

    def run(self):
        self._is_running.set()
        
        while self._is_running.is_set():
            start_time = time.perf_counter()
            msg = self.bus.recv(timeout=0.001)
            
            if msg:
                self.messages_received += 1
                
                msg_id_int = msg.arbitration_id
                queue_name = self.id_to_queue_map.get(msg_id_int)
                
                # --- MODIFICATION: Check debug flag before printing ---
                if config.DEBUG_PRINTING:
                    if queue_name:
                        print(f"DEBUG [CANReader]: Match found! ID: {msg_id_int} (0x{msg_id_int:x}) -> Queue: '{queue_name}'")
                    else:
                        print(f"DEBUG [CANReader]: No match for ID: {msg_id_int} (0x{msg_id_int:x})")
                
                if queue_name:
                    try:
                        self.data_queues[queue_name].put_nowait(msg)
                        end_time = time.perf_counter()
                        duration = (end_time - start_time)
                        self.perf_tracker['dispatch_total_time'] = self.perf_tracker.get('dispatch_total_time', 0) + duration
                        self.perf_tracker['dispatch_count'] = self.perf_tracker.get('dispatch_count', 0) + 1
                    except queue.Full:
                        self.messages_dropped += 1

    def stop(self):
        self._is_running.clear()
        print("\n--- CANReader Diagnostics ---")
        print(f"Total messages received by CANReader: {self.messages_received}")
        print(f"Total messages dropped due to full queue: {self.messages_dropped}")
        print("-----------------------------\n")