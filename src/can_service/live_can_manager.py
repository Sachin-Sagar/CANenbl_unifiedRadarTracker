import multiprocessing
import threading
import time
import os
from collections import deque
import platform # <-- ADD THIS IMPORT

import can
import cantools

from .can_handler import CANReader
from .data_processor import processing_worker
from . import utils

class LiveCANManager:
    def __init__(self, config, dbc_path, signal_list_path):
        self.config = config
        self.dbc_path = dbc_path
        self.signal_list_path = signal_list_path
        
        self.manager = multiprocessing.Manager()
        self.output_queue = self.manager.Queue(maxsize=16384)
        self.shared_data_buffer = self.manager.dict()
        self.perf_tracker = self.manager.dict()
        
        self.can_reader_thread = None
        self.processing_workers = []
        self.buffer_filler_thread = None
        self.bus = None  # <-- THIS IS THE FIX
        self._is_running = threading.Event()

    def start(self):
        print("[+] Initializing CAN Service...")
        self._is_running.set()

        # 1. Pre-flight checks: Bring up CAN interface on Linux
        if self.config.OS_SYSTEM == "Linux":
            print(" -> Ensuring CAN interface is up...")
            command = f"sudo ip link set {self.config.CAN_CHANNEL} up type can bitrate {self.config.CAN_BITRATE}"
            import subprocess
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode != 0 and "Device or resource busy" not in result.stderr:
                print(f"Error: Failed to bring up CAN interface '{self.config.CAN_CHANNEL}'.")
                print(f" -> STDERR: {result.stderr.strip()}")
                print(" -> Please check your CAN hardware and drivers.")
                # Do not return here, as the interface might still be connectable
            else:
                print(f" -> Interface '{self.config.CAN_CHANNEL}' is up or was already up.")

        # 2. Load Configuration and pre-compile decoding rules
        print(" -> Loading DBC and signal list...")
        db = cantools.database.load_file(self.dbc_path)
        high_freq_signals, low_freq_signals, id_to_queue_map = utils.load_signals_to_monitor(self.signal_list_path)
        self.decoding_rules = utils.precompile_decoding_rules(db, {**high_freq_signals, **low_freq_signals})

        # 3. Connect to CAN hardware
        print(" -> Connecting to CAN hardware...")
        try:
            self.bus = can.interface.Bus(
                interface=self.config.CAN_INTERFACE,
                channel=self.config.CAN_CHANNEL,
                bitrate=self.config.CAN_BITRATE,
                receive_own_messages=False
            )
            print(f" -> Connection successful on '{self.config.CAN_INTERFACE}' channel {self.config.CAN_CHANNEL}.")
        except (can.CanError, OSError) as e:
            print("\n" + "="*60)
            print("WARNING: CAN HARDWARE NOT DETECTED".center(60))
            print("="*60)
            print(f"Error: {e}")
            print("The application will continue without CAN data.")
            print("\nTroubleshooting:")
            print(" 1. Is the CAN hardware (e.g., PCAN-USB) securely connected?")
            if self.config.OS_SYSTEM == "Linux":
                print(" 2. Is the correct kernel driver loaded? (e.g., 'peak_usb')")
                print(f" 3. Does the CAN interface '{self.config.CAN_CHANNEL}' exist? (check with 'ip link show')")
            else: # Windows
                print(" 2. Are the necessary drivers (e.g., PCAN-Basic) installed?")
            print("="*60 + "\n")
            # Do not start CAN-related threads if connection failed
            return True # Indicate that the service manager has 'started' but without CAN functionality

        # 4. Start CANReader thread
        self.raw_mp_queue = multiprocessing.Queue(maxsize=4000)
        self.can_reader_thread = CANReader(bus=self.bus, data_queues={'high': self.raw_mp_queue, 'low': self.raw_mp_queue}, id_to_queue_map=id_to_queue_map, perf_tracker=self.perf_tracker)
        self.can_reader_thread.start()

        # 5. Start processing_worker processes
        num_processes = (os.cpu_count() or 2) - 1
        print(f" -> Starting {num_processes} decoding processes...")
        for i in range(num_processes):
            p = multiprocessing.Process(
                target=processing_worker,
                args=(i, self.decoding_rules, self.raw_mp_queue, self.output_queue, self.perf_tracker),
                daemon=True
            )
            self.processing_workers.append(p)
            p.start()

        # 6. Start the internal buffer-filler thread
        self.buffer_filler_thread = threading.Thread(target=self._buffer_filler, daemon=True)
        self.buffer_filler_thread.start()
        
        print("[+] CAN Service running.")
        return True

    def stop(self):
        print("\n[+] Shutting down CAN Service...")
        self._is_running.clear()

        if self.can_reader_thread and self.can_reader_thread.is_alive():
            self.can_reader_thread.stop()
            self.can_reader_thread.join(timeout=2)

        for _ in self.processing_workers:
            try:
                self.raw_mp_queue.put(None, timeout=0.1)
            except Exception:
                pass

        for p in self.processing_workers:
            p.join(timeout=2)

        for p in self.processing_workers:
            if p.is_alive():
                print(f"Warning: Process {p.pid} did not exit gracefully. Terminating.")
                p.terminate()
                p.join()

        if self.buffer_filler_thread and self.buffer_filler_thread.is_alive():
            self.buffer_filler_thread.join(timeout=2)

        # --- THIS BLOCK IS MODIFIED ---
        if self.bus:
            # On Windows, calling shutdown() from a different thread than
            # recv() causes a QObject timer error. We skip it.
            if platform.system() != "Windows":
                self.bus.shutdown()
        # --- END OF MODIFICATION ---
        
        print("[+] CAN Service stopped.")

    def get_signal_buffers(self):
        # Return a copy of the shared data buffer
        return dict(self.shared_data_buffer)

    def _buffer_filler(self):
        while self._is_running.is_set():
            try:
                timestamp, signal_name, value = self.output_queue.get(timeout=0.1)
                
                if signal_name not in self.shared_data_buffer:
                    self.shared_data_buffer[signal_name] = deque(maxlen=10) # Store last 10 values
                
                self.shared_data_buffer[signal_name].append((timestamp, value))

            except Exception:
                # Queue is empty or other error
                continue