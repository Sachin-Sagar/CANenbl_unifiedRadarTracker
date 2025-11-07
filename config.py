# config.py

import platform

# This file contains all the configuration settings for the CAN logger.
# Modify the values here to match your setup.

# --- CAN Hardware Settings ---
# Automatically configure the CAN interface based on the operating system.
# We assume a PCAN adapter is being used.

CAN_BITRATE = 500000

# --- GPIO Settings (for Raspberry Pi) ---
BUTTON_PIN = 17


OS_SYSTEM = platform.system()

if OS_SYSTEM == "Windows":
    CAN_INTERFACE = "pcan"
    # This is the default channel for the PCAN-USB adapter on Windows.
    # You may need to change "PCAN_USBBUS1" if you have multiple adapters.
    CAN_CHANNEL = "PCAN_USBBUS1"
elif OS_SYSTEM == "Linux":
    CAN_INTERFACE = "socketcan"
    # This is the default channel for SocketCAN on Linux.
    CAN_CHANNEL = "can0"
else:
    # Default to Kvaser or raise an error if unsupported OS
    print(f"Warning: Unsupported OS '{OS_SYSTEM}'. Defaulting to 'kvaser'.")
    CAN_INTERFACE = "kvaser"
    CAN_CHANNEL = 0


# --- NEW: Master Debug Switch ---
# This is the master switch to enable or disable all console logging.
# When set to False, it overrides all other debug flags.
ENABLE_CONSOLE_LOGGING = True

# --- NEW: Granular Debug Flags ---
# Set individual flags to True to enable specific debug messages.
# These are only active if ENABLE_CONSOLE_LOGGING is True.
DEBUG_FLAGS = {
    # Logs the raw shared CAN data and the result of the interpolation
    # in src/radar_tracker/main_live.py
    'log_can_interpolation': False,

    # Logs the CAN data as it is being adapted into the FHistFrame
    # in src/radar_tracker/data_adapter.py
    'log_can_data_adapter': False,

    # Logs the egoVx value at the entry point of the main tracker algorithm
    # in src/radar_tracker/tracking/tracker.py
    'log_tracker_entry': True,

    # Logs the egoVx value from the final history before it's saved to JSON
    # in src/radar_tracker/tracking/update_and_save_history.py
    'log_final_history': True,
}

# --- Component-Specific Debug Flags ---
# Enable/disable verbose debug messages for specific tracking components.
COMPONENT_DEBUG_FLAGS = {
    'dbscan': True,
    'ransac': True,
    'tracker_core': True, # For general tracker logic in tracker.py
    'jpda': True,
    'imm_filter': True,
    # Add other components as needed
}

# --- File and Directory Paths ---
# The script will look for the input files in this directory.
# The path is relative to the project's root folder.
INPUT_DIRECTORY = "input"

# The script will save the output log file in this directory.
# This directory will be created automatically if it doesn't exist.
OUTPUT_DIRECTORY = "output"

# The name of your DBC file, located in the INPUT_DIRECTORY.
DBC_FILE = "VCU.dbc"

# The name of your signal list file, located in the INPUT_DIRECTORY.
# This file should contain one signal per line in the format:
# CAN_ID,Signal_Name
# Example: 0x123,EngineSpeed
SIGNAL_LIST_FILE = "master_sigList.txt"
