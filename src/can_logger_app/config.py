# config.py

import platform

# This file contains all the configuration settings for the CAN logger.
# Modify the values here to match your setup.

# --- CAN Hardware Settings ---
# The CAN bitrate for the bus.
CAN_BITRATE = 500000


# --- General Settings ---
# Set to True to enable verbose debug printing, False to disable.
# --- Debugging --- #
DEBUG_LOGGING = True


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
