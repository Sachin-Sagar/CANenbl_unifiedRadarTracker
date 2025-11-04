# src/radar_tracker/console_logger.py

import logging
import os
import config  # Import the main config file
from .json_log_handler import JSONLogHandler

# --- Create a Singleton Logger Instance ---
# This logger can be imported and used by any module in the application.
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.propagate = False  # Prevent messages from being passed to the root logger

# --- Create Handlers ---
# The file and JSON handlers are always active to ensure persistent logging.
output_dir = "output"
os.makedirs(output_dir, exist_ok=True)

log_filename_txt = os.path.join(output_dir, "console_log.txt")

# File Handler (for plain text logs)
file_handler = logging.FileHandler(log_filename_txt, mode='w')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# JSON Handler (for structured logs)
json_log_handler = JSONLogHandler()
json_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(json_log_handler)

# --- Conditional Console Handler ---
# The console handler is only added if the master switch is enabled.
if config.ENABLE_CONSOLE_LOGGING:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(console_handler)

logger.info("Logger initialized. Console logging is {}.".format("ENABLED" if config.ENABLE_CONSOLE_LOGGING else "DISABLED"))

def log_debug(message, flag=None):
    """
    Logs a message if the corresponding debug flag is True in the config.
    Messages are always sent to file handlers, but only to console if ENABLE_CONSOLE_LOGGING is True.
    """
    if flag and config.DEBUG_FLAGS.get(flag, False):
        logger.info(message)
    elif not flag:
        # If no specific flag is required, log it as general info
        logger.info(message)

def log_component_debug(message, component):
    """
    Logs a message for a specific component if its debug flag is True.
    Messages are always sent to file handlers, but only to console if ENABLE_CONSOLE_LOGGING is True.
    """
    if config.COMPONENT_DEBUG_FLAGS.get(component, False):
        logger.info(f"[{component.upper()}] {message}")
