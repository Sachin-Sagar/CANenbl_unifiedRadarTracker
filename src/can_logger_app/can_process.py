# src/can_logger_app/can_process.py

import can
import time
from . import config
from .can_handler import CANReader

class CANProcess:
    def __init__(self, shutdown_flag, raw_mp_queue, id_to_queue_map, perf_tracker):
        self.shutdown_flag = shutdown_flag
        self.raw_mp_queue = raw_mp_queue
        self.id_to_queue_map = id_to_queue_map
        self.perf_tracker = perf_tracker
        self.bus = None
        self.dispatcher_thread = None

    def run(self):
        try:
            print(" -> Connecting to CAN hardware...")
            self.bus = can.interface.Bus(
                interface=config.CAN_INTERFACE,
                channel=config.CAN_CHANNEL,
                bitrate=config.CAN_BITRATE,
                receive_own_messages=False
            )
            print(f" -> Connection successful on '{config.CAN_INTERFACE}' channel {config.CAN_CHANNEL}.")

            self.dispatcher_thread = CANReader(
                bus=self.bus,
                data_queues={'high': self.raw_mp_queue, 'low': self.raw_mp_queue},
                id_to_queue_map=self.id_to_queue_map,
                perf_tracker=self.perf_tracker
            )
            self.dispatcher_thread.start()

            while not self.shutdown_flag.is_set():
                time.sleep(0.1)

        except (can.CanError, OSError) as e:
            print("\n" + "="*60)
            print("FATAL: CAN LOGGER FAILED TO INITIALIZE".center(60))
            print("="*60)
            print(f"Error: {e}")
            print(f"Could not connect to interface '{config.CAN_INTERFACE}' on channel '{config.CAN_CHANNEL}'.")
            print("\nTroubleshooting:")
            print(" 1. Is the CAN hardware (e.g., PCAN-USB) securely connected?")
            if config.OS_SYSTEM == "Linux":
                print(" 2. Is the correct kernel driver loaded? (e.g., 'peak_usb')")
                print(f" 3. Does the CAN interface '{config.CAN_CHANNEL}' exist? (check with 'ip link show')")
            else: # Windows
                print(" 2. Are the necessary drivers (e.g., PCAN-Basic) installed?")
            print("="*60 + "\n")
        finally:
            if self.dispatcher_thread and self.dispatcher_thread.is_alive():
                self.dispatcher_thread.stop()
                self.dispatcher_thread.join(timeout=2)
            
            if self.bus:
                self.bus.shutdown()
                print(" -> CAN bus shut down.")
