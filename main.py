
import sys
import os
import platform
import subprocess

# Add the 'src' directory to the Python path
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

if __name__ == '__main__':
    # Create a timestamped output directory
    output_dir = os.path.join("output", datetime.now().strftime('%Y%m%d_%H%M%S'))
    os.makedirs(output_dir, exist_ok=True)

    # Configure logging for the entire application
    setup_logging(output_dir)
    
    # Launch the radar application
    radar_main(output_dir)
