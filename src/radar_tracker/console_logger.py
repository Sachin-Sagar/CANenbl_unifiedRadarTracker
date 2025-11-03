# src/console_logger.py

import logging
from datetime import datetime
import os
from .json_log_handler import JSONLogHandler

def setup_logging(output_dir):
    """
    Configures logging to output to the console and a plain text file.
    """
    os.makedirs(output_dir, exist_ok=True)

    log_filename_txt = os.path.join(output_dir, f"console_log.txt")

    # --- Create Handlers ---
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))

    file_handler_txt = logging.FileHandler(log_filename_txt, mode='w')
    file_handler_txt.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    json_log_handler = JSONLogHandler()
    json_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    # --- Configure Root Logger ---
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            console_handler,
            file_handler_txt,
            json_log_handler
        ]
    )
    logging.info("Logging configured for console and text file.")