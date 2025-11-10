import multiprocessing
import threading
import time
import os
from collections import deque
import platform
import queue

import can
import cantools

from src.can_service.can_handler import CANReader
from src.can_service.data_processor import processing_worker
from src.can_service import utils

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
        self.bus = None
        self._is_running = threading.Event()

    def start(self):
        print("[+] Initializing CAN Service...")
        self._is_running.set()

        if self.config.OS_SYSTEM == "Linux":
            print(" -> Ensuring CAN interface is up...")
            command = f"sudo ip link set {self.config.CAN_CHANNEL} up type can bitrate {self.config.CAN_BITRATE}"
            import subprocess
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode != 0 and "Device or resource busy" not in result.stderr:
                print(f"Error: Failed to bring up CAN interface '{self.config.CAN_CHANNEL}'.")
                print(f" -> STDERR: {result.stderr.strip()}")
                print(" -> Please check your CAN hardware and drivers.")
            else:
                print(f" -> Interface '{self.config.CAN_CHANNEL}' is up or was already up.")

        print(" -> Loading DBC and signal list...")
        db = cantools.database.load_file(self.dbc_path)
        high_freq_signals, low_freq_signals, id_to_queue_map = utils.load_signals_to_monitor(self.signal_list_path)
        self.decoding_rules = utils.precompile_decoding_rules(db, {**high_freq_signals, **low_freq_signals})

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
            return True

        self.raw_mp_queue = multiprocessing.Queue(maxsize=4000)
        self.can_reader_thread = CANReader(bus=self.bus, data_queues={'high': self.raw_mp_queue, 'low': self.raw_mp_queue}, id_to_queue_map=id_to_queue_map, perf_tracker=self.perf_tracker)
        self.can_reader_thread.start()

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

        if self.bus:
            if platform.system() != "Windows":
                self.bus.shutdown()
        
        print("[+] CAN Service stopped.")

    def get_signal_buffers(self):
        return dict(self.shared_data_buffer)

    def _buffer_filler(self):
        import queue
        while self._is_running.is_set():
            try:
                timestamp, signal_name, value = self.output_queue.get(timeout=0.1)
                
                current_deque = self.shared_data_buffer.get(signal_name, deque(maxlen=10))
                
                current_deque.append((timestamp, value))
                
                self.shared_data_buffer[signal_name] = current_deque

            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in CAN service buffer filler: {e}")
                continue
