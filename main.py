import sys
import os
import platform
import subprocess

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))


from radar_tracker.console_logger import logger
from datetime import datetime
if platform.system() == "Linux":
        from can_logger_app.gpio_handler import init_gpio, wait_for_switch_on, check_for_switch_off, cleanup_gpio, turn_on_led, turn_off_led
import threading
import multiprocessing


import logging
from logging.handlers import QueueHandler, QueueListener
from src.radar_tracker.json_log_handler import JSONLogHandler

if __name__ == '__main__':
    # --- Imports are deferred to here to prevent issues with multiprocessing on Windows ---
    from can_logger_app.main import main as can_logger_main
    from radar_tracker.main_live import main as main_live
    from radar_tracker.main_playback import run_playback
    multiprocessing.freeze_support()
    
    # --- Create the Manager and shared data structures FIRST ---
    manager = multiprocessing.Manager()
    shutdown_flag = multiprocessing.Event()
    can_logger_ready = multiprocessing.Event() # Event to signal CAN logger readiness
    shared_live_can_data = manager.dict() # This dict will be shared

    # Create a timestamped output directory
    output_dir = os.path.join("output", datetime.now().strftime('%Y%m%d_%H%M%S'))
    os.makedirs(output_dir, exist_ok=True)

    # --- Setup File-based and Multiprocessing Logging ---
    log_queue = multiprocessing.Queue()

    # Create a directory for console logs
    console_out_dir = os.path.join(output_dir, "console_out")
    os.makedirs(console_out_dir, exist_ok=True)

    # Define filters for different log categories
    class CANFilter(logging.Filter):
        def filter(self, record):
            return 'can_logger_app' in record.pathname

    class RadarProcessingFilter(logging.Filter):
        def filter(self, record):
            return 'radar_tracker' in record.pathname and 'tracking' not in record.name

    class TrackingFilter(logging.Filter):
        def filter(self, record):
            return 'tracking' in record.name

    # Create handlers for each category
    can_handler = logging.FileHandler(os.path.join(console_out_dir, 'can_processing.log'), mode='w')
    can_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
    can_handler.addFilter(CANFilter())

    radar_handler = logging.FileHandler(os.path.join(console_out_dir, 'radar_processing.log'), mode='w')
    radar_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
    radar_handler.addFilter(RadarProcessingFilter())

    tracking_handler = logging.FileHandler(os.path.join(console_out_dir, 'tracking.log'), mode='w')
    tracking_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
    tracking_handler.addFilter(TrackingFilter())

    # Configure the listener to handle logs from the queue
    from src.radar_tracker.console_logger import json_log_handler
    
    listener = QueueListener(log_queue, can_handler, radar_handler, tracking_handler)
    listener.start()

    # The main process's root logger sends to the queue
    root_logger = logging.getLogger()
    root_logger.addHandler(QueueHandler(log_queue))
    root_logger.setLevel(logging.DEBUG)

    # --- Ask for mode ---
    logger.info("--- Welcome to the Unified Radar Tracker ---")
    while True:
        mode = input("Select mode: (1) Live Tracking or (2) Playback from File\nEnter choice (1 or 2): ")
        if mode in ['1', '2']:
            break
        else:
            logger.info("Invalid choice. Please enter 1 or 2.")

    can_interface = None # Initialize can_interface
    effective_can_logger_ready = can_logger_ready # Assume CAN is used by default

    if mode == '1':
        # --- Ask for CAN interface ---
        logger.info("\n--- CAN Interface Selection ---")
        while True:
            can_interface_choice = input("Select CAN interface: (1) PEAK (pcan), (2) Kvaser, or (3) No CAN\nEnter choice (1, 2, or 3): ").lower().strip()
            if can_interface_choice in ['1', 'peak', 'pcan']:
                can_interface = 'peak'
                break
            elif can_interface_choice in ['2', 'kvaser']:
                can_interface = 'kvaser'
                break
            elif can_interface_choice in ['3', 'no can', 'none']:
                can_interface = None
                effective_can_logger_ready = None # Set to None for "No CAN" mode
                break
            else:
                logger.info("Invalid choice. Please enter 1, 2, or 3.")

    # If on Raspberry Pi, wait for switch to be turned on
    if platform.system() == "Linux":
        
        can_logger_process = None
        try:
            init_gpio()
            logger.info("Waiting for switch ON...")
            wait_for_switch_on()
            logger.info("Switch is ON!")
            turn_on_led()

            # Start the CAN logger in a separate process for live mode
            if mode == '1' and can_interface is not None:
                # MODIFIED: Pass the shared dict and can_interface to the logger
                can_logger_process = multiprocessing.Process(
                    target=can_logger_main, 
                    args=(shutdown_flag, output_dir, shared_live_can_data, can_interface, can_logger_ready, log_queue)
                )
                can_logger_process.start()

                # Start the stop signal checker in a separate thread
                stop_thread = threading.Thread(target=check_for_switch_off, args=(shutdown_flag,))
                stop_thread.start()

            # Launch the appropriate mode
            if mode == '1':
                logger.info("\nStarting in LIVE mode...")
                # MODIFIED: Pass the shared dict and ready event to the live radar main
                main_live(output_dir, shutdown_flag, shared_live_can_data, effective_can_logger_ready)
            elif mode == '2':
                logger.info("\nStarting in PLAYBACK mode...")
                run_playback(output_dir)

        finally:
            shutdown_flag.set() # Signal all processes to shutdown

            if 'stop_thread' in locals() and stop_thread.is_alive():
                stop_thread.join(timeout=2)

            if can_logger_process and can_logger_process.is_alive():
                logger.info("Signaling CAN logger to shut down...")
                can_logger_process.join(timeout=5)
                if can_logger_process.is_alive():
                    logger.info("CAN logger did not shut down, terminating...")
                    can_logger_process.terminate()
                    can_logger_process.join()

            if platform.system() == "Linux":
                turn_off_led()
            
            cleanup_gpio()
            logger.info("Application shut down.")

    else: # Not on Linux
        
        can_logger_process = None
        live_thread = None
        try:
            if mode == '1':
                logger.info("\nStarting in LIVE mode...")
                # Start the CAN logger process only if an interface is selected
                if can_interface is not None:
                    # MODIFIED: Pass the shared dict and can_interface to the logger
                    can_logger_process = multiprocessing.Process(
                        target=can_logger_main, 
                        args=(shutdown_flag, output_dir, shared_live_can_data, can_interface, can_logger_ready, log_queue)
                    )
                    can_logger_process.start()
                
                # Start the main_live function in a separate thread
                # MODIFIED: Pass the shared dict and ready event to the live radar main
                live_thread = threading.Thread(
                    target=main_live, 
                    args=(output_dir, shutdown_flag, shared_live_can_data, effective_can_logger_ready)
                )
                live_thread.start()
                
                # Wait for the live thread to finish, allowing for Ctrl+C
                live_thread.join()

            elif mode == '2':
                logger.info("\nStarting in PLAYBACK mode...")
                run_playback(output_dir)

        except KeyboardInterrupt:
            logger.info("\nCtrl+C detected. Shutting down...")
        finally:
            shutdown_flag.set() # Signal all processes to shutdown

            if live_thread and live_thread.is_alive():
                logger.info("Waiting for live tracker to finish...")
                live_thread.join(timeout=5)

            if can_logger_process and can_logger_process.is_alive():
                logger.info("Signaling CAN logger to shut down gracefully...")
                can_logger_process.join(timeout=5) 

                if can_logger_process.is_alive():
                    logger.info("CAN logger did not shut down, terminating...")
                    can_logger_process.terminate()
                    can_logger_process.join()
            logger.info("Application shut down.")

    listener.stop()
