
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
from can_logger_app.gpio_handler import init_gpio, wait_for_switch_on, check_for_switch_off, cleanup_gpio, turn_on_led, turn_off_led
import platform
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
        shutdown_flag = threading.Event()
        stop_event = threading.Event()
        can_logger_process = None
        try:
            init_gpio()
            print("Waiting for switch ON...")
            wait_for_switch_on()
            print("Switch is ON!")
            turn_on_led()

            # Start the CAN logger in a separate process for live mode
            if mode == '1':
                can_logger_process = multiprocessing.Process(target=can_logger_main)
                can_logger_process.start()

            # Start the stop signal checker in a separate thread
            stop_thread = threading.Thread(target=check_for_switch_off, args=(stop_event, shutdown_flag))
            stop_thread.start()

            # Launch the appropriate mode
            if mode == '1':
                print("\nStarting in LIVE mode...")
                main_live(output_dir, shutdown_flag)
            elif mode == '2':
                print("\nStarting in PLAYBACK mode...")
                run_playback(output_dir)

        finally:
            stop_event.set()
            if can_logger_process and can_logger_process.is_alive():
                can_logger_process.terminate()
                can_logger_process.join()
            if platform.system() == "Linux":
                turn_off_led()
            cleanup_gpio()
            print("Switch is OFF! Stopping...")

    else: # Not on Linux
        # Launch the appropriate mode directly
        if mode == '1':
            print("\nStarting in LIVE mode...")
            # Note: CAN logging and GPIO are not supported on non-Linux systems in this setup
            main_live(output_dir)
        elif mode == '2':
            print("\nStarting in PLAYBACK mode...")
            run_playback(output_dir)

