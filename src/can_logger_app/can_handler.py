# src/can_logger_app/can_handler.py

import queue
import threading
import time
from . import config  # <-- This import is safe

# --- MODIFICATION: 'import can' has been REMOVED from the top ---

class CANReader(threading.Thread):
    def __init__(self, bus_params, data_queues, id_to_queue_map, perf_tracker, connection_event):
        """
        MODIFIED: Accepts bus_params (dict) instead of a bus object.
        'connection_event' is a threading.Event() used to signal success/failure.
        """
        super().__init__(daemon=True)
        self.bus_params = bus_params
        self.bus = None # Will be created inside run()
        self.data_queues = data_queues
        self.id_to_queue_map = id_to_queue_map
        self.perf_tracker = perf_tracker
        self.connection_event = connection_event
        self._is_running = threading.Event()
        self.messages_dropped = 0
        self.messages_received = 0

    def run(self):
        # --- MODIFICATION: Import 'can' INSIDE the run() method ---
        # This ensures all Qt/pcan resources are created in THIS thread.
        import can
        
        self._is_running.set()
        
        try:
            # --- Create the bus object *inside* the thread ---
            print(" -> [CANReader] Thread trying to connect to CAN bus...")
            self.bus = can.interface.Bus(**self.bus_params)
            
            # Signal to the main thread that the connection was successful
            self.connection_event.set()
            print(f" -> [CANReader] Thread connected successfully on {self.bus_params.get('channel')}.")

            while self._is_running.is_set():
                start_time = time.perf_counter()
                msg = self.bus.recv(timeout=0.001) # Use a small timeout
                
                if msg:
                    self.messages_received += 1
                    
                    msg_id_int = msg.arbitration_id
                    queue_name = self.id_to_queue_map.get(msg_id_int)
                    
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
        
        except (can.CanError, OSError, ImportError) as e:
            # --- MODIFICATION: Signal failure if connection fails ---
            print(f"FATAL [CANReader]: Failed to create or read from bus: {e}")
            # We don't set the event, so the main thread will know it failed
        
        finally:
            # This code runs INSIDE the CANReader thread after the loop exits
            if self.bus:
                self.bus.shutdown()
                print(" -> [CANReader] Thread shut down bus successfully.")
                # --- MODIFICATION: Force object destruction in THIS thread ---
                self.bus = None
            
            # Ensure the event is cleared if it was never set (e.g., error)
            # or just to be clean.
            if self.connection_event.is_set():
                self.connection_event.clear()


    def stop(self):
        self._is_running.clear()
        print("\n--- CANReader Diagnostics ---")
        print(f"Total messages received by CANReader: {self.messages_received}")
        print(f"Total messages dropped due to full queue: {self.messages_dropped}")
        print("-----------------------------\n")