
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


if __name__ == '__main__':
    multiprocessing.freeze_support()
    # Create a timestamped output directory
    output_dir = os.path.join("output", datetime.now().strftime('%Y%m%d_%H%M%S'))
    os.makedirs(output_dir, exist_ok=True)

    # Configure logging for the entire application
    setup_logging(output_dir)

    # --- Ask for mode first ---
    print("--- Welcome to the Unified Radar Tracker ---")
    while True:
        mode = input("Select mode: (1) Live Tracking or (2) Playback from File\nEnter choice (1 or 2): ")
        if mode in ['1', '2']:
            break
        else:
            print("Invalid choice. Please enter 1 or 2.")

    # If on Raspberry Pi, wait for switch to be turned on
    if platform.system() == "Linux":
        shutdown_flag = multiprocessing.Event()
        can_logger_process = None
        try:
            init_gpio()
            print("Waiting for switch ON...")
            wait_for_switch_on()
            print("Switch is ON!")
            turn_on_led()

            # Start the CAN logger in a separate process for live mode
            if mode == '1':
                can_logger_process = multiprocessing.Process(target=can_logger_main, args=(shutdown_flag, output_dir,))
                can_logger_process.start()

            # Start the stop signal checker in a separate thread
            stop_thread = threading.Thread(target=check_for_switch_off, args=(shutdown_flag,))
            stop_thread.start()

            # Launch the appropriate mode
            if mode == '1':
                print("\nStarting in LIVE mode...")
                main_live(output_dir, shutdown_flag)
            elif mode == '2':
                print("\nStarting in PLAYBACK mode...")
                run_playback(output_dir)

        finally:
            shutdown_flag.set() # Signal all processes to shutdown

            if can_logger_process and can_logger_process.is_alive():
                print("Waiting for CAN logger to finish...")
                can_logger_process.join(timeout=5) # Wait for the logger to finish
                if can_logger_process.is_alive():
                    print("CAN logger did not exit gracefully, terminating.")
                    can_logger_process.terminate()
                can_logger_process.join()

            if platform.system() == "Linux":
                turn_off_led()
            
            cleanup_gpio()
            print("Application shut down.")

    else: # Not on Linux
        shutdown_flag = multiprocessing.Event()
        can_logger_process = None
        live_thread = None
        try:
            if mode == '1':
                print("\nStarting in LIVE mode...")
                # Start the CAN logger process
                can_logger_process = multiprocessing.Process(target=can_logger_main, args=(shutdown_flag, output_dir,))
                can_logger_process.start()
                
                # Start the main_live function in a separate thread
                live_thread = threading.Thread(target=main_live, args=(output_dir, shutdown_flag,))
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
                print("Waiting for CAN logger to finish...")
                can_logger_process.join(timeout=5)
                if can_logger_process.is_alive():
                    print("CAN logger did not exit gracefully, terminating.")
                    can_logger_process.terminate()
                    can_logger_process.join()
            
            print("Application shut down.")

