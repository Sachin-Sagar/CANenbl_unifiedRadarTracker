# config.py

import platform

# This file contains all the configuration settings for the CAN logger.
# Modify the values here to match your setup.

# --- CAN Hardware Settings ---
# Automatically configure the CAN interface based on the operating system.
# We assume a PCAN adapter is being used.

CAN_BITRATE = 500000
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


# --- General Settings ---
# Set to True to enable verbose debug printing, False to disable.
DEBUG_PRINTING = False


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
