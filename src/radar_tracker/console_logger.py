# src/console_logger.py

import logging
from datetime import datetime
import os  # <-- 1. Import the os module

def setup_logging():
    """
    Configures logging to output to the console and a plain text file.
    """
    # --- 2. Create the output directory if it doesn't exist ---
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    # --------------------------------------------------------

    log_filename_txt = os.path.join(output_dir, f"console_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

    # --- Create Handlers ---
    # 1. Console Handler (for live viewing)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))

    # 2. Text File Handler (for easy reading)
    file_handler_txt = logging.FileHandler(log_filename_txt, mode='w')
    file_handler_txt.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    # --- Configure Root Logger ---
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            console_handler,
            file_handler_txt
        ]
    )
    logging.info("Logging configured for console and text file.")