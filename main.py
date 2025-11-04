import sys
import os
import platform
import subprocess

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))


from radar_tracker.main import main as radar_main
from radar_tracker.console_logger import setup_logging
from datetime import datetime
if platform.system() == "Linux":
        from can_logger_app.gpio_handler import init_gpio, wait_for_switch_on, check_for_switch_off, cleanup_gpio, turn_on_led, turn_off_led
import threading
import multiprocessing
from can_logger_app.main import main as can_logger_main
from radar_tracker.main_live import main as main_live
from radar_tracker.main_playback import run_playback


import json
import logging
from src.radar_tracker.json_log_handler import JSONLogHandler

if __name__ == '__main__':
    multiprocessing.freeze_support()
    
    # --- Create the Manager and shared data structures FIRST ---
    manager = multiprocessing.Manager()
    shutdown_flag = multiprocessing.Event()
    shared_live_can_data = manager.dict() # This dict will be shared

    # Create a timestamped output directory
    output_dir = os.path.join("output", datetime.now().strftime('%Y%m%d_%H%M%S'))
    os.makedirs(output_dir, exist_ok=True)

    # Configure logging for the entire application
    setup_logging(output_dir)

    # --- Ask for CAN interface ---
    can_interface = 'peak' # Default for non-live mode
    if any('live' in arg.lower() for arg in sys.argv) or (len(sys.argv) == 1): # Check if running live or no args
        print("--- CAN Interface Selection ---")
        while True:
            can_interface_choice = input("Select CAN interface: (1) PEAK (pcan) or (2) Kvaser\nEnter choice (1 or 2): ").lower().strip()
            if can_interface_choice in ['1', 'peak', 'pcan']:
                can_interface = 'peak'
                break
            elif can_interface_choice in ['2', 'kvaser']:
                can_interface = 'kvaser'
                break
            else:
                print("Invalid choice. Please enter 1 or 2.")

    # --- Ask for mode ---
    print("\n--- Mode Selection ---")
    while True:
        mode = input("Select mode: (1) Live Tracking or (2) Playback from File\nEnter choice (1 or 2): ")
        if mode in ['1', '2']:
            break
        else:
            print("Invalid choice. Please enter 1 or 2.")

    # If on Raspberry Pi, wait for switch to be turned on
    if platform.system() == "Linux":
        
        can_logger_process = None
        try:
            init_gpio()
            print("Waiting for switch ON...")
            wait_for_switch_on()
            print("Switch is ON!")
            turn_on_led()

            # Start the CAN logger in a separate process for live mode
            if mode == '1':
                # MODIFIED: Pass the shared dict and can_interface to the logger
                can_logger_process = multiprocessing.Process(
                    target=can_logger_main, 
                    args=(shutdown_flag, output_dir, shared_live_can_data, can_interface)
                )
                can_logger_process.start()

            # Start the stop signal checker in a separate thread
            stop_thread = threading.Thread(target=check_for_switch_off, args=(shutdown_flag,))
            stop_thread.start()

            # Launch the appropriate mode
            if mode == '1':
                print("\nStarting in LIVE mode...")
                # MODIFIED: Pass the shared dict to the live radar main
                main_live(output_dir, shutdown_flag, shared_live_can_data)
            elif mode == '2':
                print("\nStarting in PLAYBACK mode...")
                run_playback(output_dir)

        finally:
            shutdown_flag.set() # Signal all processes to shutdown

            if can_logger_process and can_logger_process.is_alive():
                print("Signaling CAN logger to shut down...")
                can_logger_process.join(timeout=5)
                if can_logger_process.is_alive():
                    print("CAN logger did not shut down, terminating...")
                    can_logger_process.terminate()
                    can_logger_process.join()

            if platform.system() == "Linux":
                turn_off_led()
            
            cleanup_gpio()
            print("Application shut down.")

    else: # Not on Linux
        
        can_logger_process = None
        live_thread = None
        try:
            if mode == '1':
                print("\nStarting in LIVE mode...")
                # Start the CAN logger process
                # MODIFIED: Pass the shared dict and can_interface to the logger
                can_logger_process = multiprocessing.Process(
                    target=can_logger_main, 
                    args=(shutdown_flag, output_dir, shared_live_can_data, can_interface)
                )
                can_logger_process.start()
                
                # Start the main_live function in a separate thread
                # MODIFIED: Pass the shared dict to the live radar main
                live_thread = threading.Thread(
                    target=main_live, 
                    args=(output_dir, shutdown_flag, shared_live_can_data)
                )
                live_thread.start()
                
                # Wait for the live thread to finish, allowing for Ctrl+C
                live_thread.join()

            elif mode == '2':
                print("\nStarting in PLAYBACK mode...")
                run_playback(output_dir)

        except KeyboardInterrupt:
            print("\nCtrl+C detected. Shutting down...")
        finally:
            shutdown_flag.set() # Signal all processes to shutdown

            if live_thread and live_thread.is_alive():
                print("Waiting for live tracker to finish...")
                live_thread.join(timeout=5)

            if can_logger_process and can_logger_process.is_alive():
                print("Signaling CAN logger to shut down gracefully...")
                can_logger_process.join(timeout=5) 

                if can_logger_process.is_alive():
                    print("CAN logger did not shut down, terminating...")
                    can_logger_process.terminate()
                    can_logger_process.join()
            
            # --- Write console logs to JSON ---
            for handler in logging.getLogger().handlers:
                if isinstance(handler, JSONLogHandler):
                    with open(os.path.join(output_dir, "console_log.json"), 'w') as f:
                        json.dump(handler.log_records, f, indent=4)
                    break
            # -------------------------------------

            print("Application shut down.")