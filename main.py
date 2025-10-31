
import sys
import os
import platform
import subprocess

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

if platform.system() == "Linux":
    print("Detected Linux OS. Attempting to bring up CAN interface 'can0'...")
    try:
        # This command requires sudo privileges and might prompt for a password.
        # The user has explicitly requested this command to be run.
        result = subprocess.run(["sudo", "ip", "link", "set", "can0", "up", "type", "can", "bitrate", "500000"], check=True, capture_output=True, text=True)
        print("CAN interface 'can0' brought up successfully.")
    except subprocess.CalledProcessError as e:
        if "Device or resource busy" in e.stderr:
            print("CAN interface 'can0' is already up. Continuing...")
        else:
            print(f"Error bringing up CAN interface: {e}")
            print(e.stderr)
            print("Please ensure 'can-utils' is installed and you have appropriate permissions.")
            sys.exit(1)
    except FileNotFoundError:
        print("Error: 'ip' command not found. Please ensure 'iproute2' is installed.")
        sys.exit(1)

from radar_tracker.main import main as radar_main
from radar_tracker.console_logger import setup_logging
from datetime import datetime
from can_logger_app.gpio_handler import init_gpio, wait_for_switch_on, check_for_switch_off, cleanup_gpio, turn_on_led, turn_off_led
import platform
import threading
import multiprocessing
from can_logger_app.main import main as can_logger_main

if __name__ == '__main__':
    multiprocessing.freeze_support()
    # Create a timestamped output directory
    output_dir = os.path.join("output", datetime.now().strftime('%Y%m%d_%H%M%S'))
    os.makedirs(output_dir, exist_ok=True)

    # Configure logging for the entire application
    setup_logging(output_dir)

    # If on Raspberry Pi, wait for switch to be turned on
    if platform.system() == "Linux":
        shutdown_flag = threading.Event()
        stop_event = threading.Event()
        can_logger_process = None
        try:
            init_gpio()
            wait_for_switch_on()
            turn_on_led()

            # Start the CAN logger in a separate process
            can_logger_process = multiprocessing.Process(target=can_logger_main)
            can_logger_process.start()

            # Start the stop signal checker in a separate thread
            stop_thread = threading.Thread(target=check_for_switch_off, args=(stop_event, shutdown_flag))
            stop_thread.start()

            # Launch the radar application
            radar_main(output_dir, shutdown_flag)
        finally:
            stop_event.set()
            if can_logger_process and can_logger_process.is_alive():
                can_logger_process.terminate()
                can_logger_process.join()
            if platform.system() == "Linux":
                turn_off_led()
            cleanup_gpio()
    else:
        # Launch the radar application directly on other systems
        radar_main(output_dir)

