# src/can_logger_app/main.py

import os
import time
from datetime import datetime
import multiprocessing
import struct
import signal
import threading # <-- MODIFIED: Import threading
import logging
import logging.handlers
import sys # Import sys for stdout/stderr redirection

# --- NOTE: Only modules needed by all processes remain at the top level ---

def main(shutdown_flag=None, output_dir=None, live_data_dict=None, can_interface_choice='peak', can_logger_ready=None, log_queue=None):
    """
    Main function using a shared memory pipeline and a high-performance queue.
    
    Args:
        shutdown_flag (multiprocessing.Event, optional): Event to signal shutdown. Defaults to None.
        output_dir (str, optional): Directory to save log files. Defaults to None, which uses config.OUTPUT_DIRECTORY.
        live_data_dict (multiprocessing.Manager.dict, optional): Shared dictionary to update with live CAN data.
        can_interface_choice (str, optional): The chosen CAN interface ('peak' or 'kvaser'). Defaults to 'peak'.
    """

    # --- Redirect stdout and stderr to a log file ---
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    target_output_dir = output_dir if output_dir else config.OUTPUT_DIRECTORY
    os.makedirs(target_output_dir, exist_ok=True)
    console_log_filepath = os.path.join(target_output_dir, f"can_logger_console_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log")
    
    try:
        sys.stdout = open(console_log_filepath, 'a', buffering=1) # Line-buffered
        sys.stderr = sys.stdout # Redirect stderr to the same file
        print(f"[INFO] Console output redirected to: {console_log_filepath}")

        if log_queue:
            # Use a named logger for this specific application part
            logger = logging.getLogger('can_logger_app')
            logger.addHandler(logging.handlers.QueueHandler(log_queue))
            logger.setLevel(logging.DEBUG)

        # --- MODIFICATION: Imports are moved inside main() ---
        import can
        import cantools
        from can_logger_app import config
        from can_logger_app import utils
        from .can_handler import CANReader
        from .data_processor import processing_worker, LOG_ENTRY_FORMAT
        from .log_writer import LogWriter
        # --------------------------------------------------------

        import signal
        import platform # Import platform to be used locally

        def signal_handler(signum, frame):
            print("\n[+] SIGTERM received, shutting down gracefully...")
            if shutdown_flag:
                shutdown_flag.set()

        signal.signal(signal.SIGTERM, signal_handler)

        print("--- Real-Time CAN Logger ---")
        print(f"--- (Using CAN Interface: {can_interface_choice}) ---")
        if live_data_dict is not None:
            print("--- (Live Radar Data Sharing ENABLED) ---")


        # --- Pre-flight checks: Determine CAN parameters based on choice ---
        OS_SYSTEM = platform.system()
        if can_interface_choice == 'peak':
            if OS_SYSTEM == "Windows":
                can_interface = "pcan"
                can_channel = "PCAN_USBBUS1"
            else: # Linux
                can_interface = "socketcan"
                can_channel = "can0"
        elif can_interface_choice == 'kvaser':
            can_interface = "kvaser"
            can_channel = 0
        else:
            print(f"Error: Invalid CAN interface choice '{can_interface_choice}'. Exiting.")
            return
            
        # --- Pre-flight checks: Bring up CAN interface on Linux ---
        if OS_SYSTEM == "Linux" and can_interface == 'socketcan':
            print("\n[+] Ensuring CAN interface is up...")
            command = f"sudo ip link set {can_channel} up type can bitrate {config.CAN_BITRATE}"
            print(f" -> Running: {command}")
            
            import subprocess
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                if "Device or resource busy" in result.stderr:
                    print(f" -> Interface '{can_channel}' is already up. Continuing.")
                else:
                    print(f"\nError: Failed to bring up CAN interface '{can_channel}'.")
                    print(f" -> The command 'sudo ip link set {can_channel} up' failed.")
                    print(f" -> STDERR: {result.stderr.strip()}")
                    print(f"\n -> This usually means the device '{can_channel}' does not exist.")
                    print(" -> Please check your CAN hardware connection and drivers.")
                    return 
            else:
                print(f" -> Interface '{can_channel}' brought up successfully.")

        # --- 1. Load Configuration ---
        print("\n[+] Loading configuration...")
        dbc_path = os.path.join(config.INPUT_DIRECTORY, config.DBC_FILE)
        signal_list_path = os.path.join(config.INPUT_DIRECTORY, config.SIGNAL_LIST_FILE)

        try:
            db = cantools.database.load_file(dbc_path)
        except Exception as e:
            print(f"Error: Failed to parse DBC file '{dbc_path}': {e}. Exiting.")
            return

        high_freq_signals, low_freq_signals, id_to_queue_map = utils.load_signals_to_monitor(signal_list_path)
        if id_to_queue_map is None: return

        all_monitoring_signals = {s for group in (high_freq_signals, low_freq_signals) for sig_set in group.values() for s in sig_set}
        
        print(" -> Pre-compiling decoding rules...")
        decoding_rules = utils.precompile_decoding_rules(db, {**high_freq_signals, **low_freq_signals})
        
        output_filepath = os.path.join(target_output_dir, f"can_log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json")
        os.makedirs(target_output_dir, exist_ok=True)
        print(f" -> Output will be saved to: '{output_filepath}'")

        # --- 2. Initialize Multiprocessing Components ---
        print("\n[+] Initializing worker processes...")
        manager = multiprocessing.Manager()
        
        raw_mp_queue = multiprocessing.Queue(maxsize=4000)
        log_queue = multiprocessing.Queue(maxsize=16384)
        
        perf_tracker = manager.dict()
        processes = []
        
        dispatcher_thread = None
        log_writer_thread = None

        try:
            # --- MODIFICATION: Create bus_params dict from user choice ---
            bus_params = {
                "interface": can_interface,
                "channel": can_channel,
                "bitrate": config.CAN_BITRATE,
                "receive_own_messages": False
            }
            
            # --- MODIFICATION: Create connection event ---
            connection_event = threading.Event()
            
            print(" -> Initializing CAN data dispatcher (CANReader) thread...")
            dispatcher_thread = CANReader(
                bus_params=bus_params, 
                data_queues={'high': raw_mp_queue, 'low': raw_mp_queue}, 
                id_to_queue_map=id_to_queue_map, 
                perf_tracker=perf_tracker,
                connection_event=connection_event
            )
            dispatcher_thread.start()
            print(" -> CAN data dispatcher thread started.")
            
            # --- MODIFICATION: Wait for connection ---
            print(" -> Waiting for CANReader thread to connect...")
            connection_success = connection_event.wait(timeout=5.0) # Wait 5s
            
            if not connection_success:
                # The event was not set; CANReader failed to connect
                raise can.CanError(f"Failed to connect on '{can_interface}' channel {can_channel}. CANReader thread failed.")
            
            print(" -> CAN Connection successful. Proceeding with logger setup.")

            print(" -> Initializing log writer thread...")
            log_writer_thread = LogWriter(log_queue=log_queue, filepath=output_filepath, perf_tracker=perf_tracker)
            log_writer_thread.start()
            print(" -> Log writer thread started.")

            num_processes = (os.cpu_count() or 2) - 1
            print(f" -> Starting {num_processes} decoding processes...")
            for i in range(num_processes):
                p = multiprocessing.Process(
                    target=processing_worker,
                    # MODIFIED: Pass the can_logger_ready event to the worker
                    args=(i, decoding_rules, raw_mp_queue, log_queue, perf_tracker, live_data_dict, can_logger_ready),
                    daemon=True
                )
                processes.append(p)
                p.start()

            print("\n[+] Logging data... Press Ctrl-C to stop.")
            last_check_time = time.time()
            while not (shutdown_flag and shutdown_flag.is_set()):
                # --- Health Checks for all processes and threads ---
                if not all(p.is_alive() for p in processes):
                    logger.error("One or more worker processes have died unexpectedly. Shutting down.")
                    break
                if not dispatcher_thread.is_alive():
                    logger.error("CANReader thread has died unexpectedly. Shutting down.")
                    break
                if not log_writer_thread.is_alive():
                    logger.error("LogWriter thread has died unexpectedly. Shutting down.")
                    break

                # --- Periodic status logging ---
                current_time = time.time()
                if current_time - last_check_time >= 5.0: # Log status every 5 seconds
                    logger.debug(f"[HEALTH CHECK] CANReader thread alive: {dispatcher_thread.is_alive()}")
                    logger.debug(f"[HEALTH CHECK] LogWriter thread alive: {log_writer_thread.is_alive()}")
                    for i, p in enumerate(processes):
                        logger.debug(f"[HEALTH CHECK] Worker process {i} (PID: {p.pid}) alive: {p.is_alive()}")
                    last_check_time = current_time

                time.sleep(1) # Main loop check interval

        except (KeyboardInterrupt, SystemExit):
            print("\n\n[+] Ctrl-C detected. Shutting down gracefully...")
        except (can.CanError, OSError, ImportError) as e:
            print("\n" + "="*60)
            print("FATAL: CAN LOGGER FAILED TO INITIALIZE".center(60))
            print("="*60)
            print(f"Error: {e}")
            print("\nTroubleshooting:")
            print(" 1. Is the CAN hardware securely connected?")

            if can_interface_choice == 'peak':
                if OS_SYSTEM == "Windows":
                    print(" 2. Are the PCAN-Basic drivers installed?")
                    print(f" 3. Is the channel name '{can_channel}' correct for your device?")
                else: # Linux
                    print(" 2. Is the 'peak_usb' kernel driver loaded? (check with 'lsmod | grep peak_usb')")
                    print(f" 3. Does the CAN interface '{can_channel}' exist? (check with 'ip link show')")
                    print(f" 4. Did you bring the interface up? (e.g., 'sudo ip link set {can_channel} up')")
            
            elif can_interface_choice == 'kvaser':
                if OS_SYSTEM == "Windows":
                    print(" 2. Are the Kvaser CANlib drivers installed?")
                    print(f" 3. Is channel {can_channel} the correct one for your device?")
                else: # Linux
                    print(" 2. Are the Kvaser linuxcan drivers and CANlib SDK installed correctly?")
                    print(" 3. Does your user have permission to access the device?")

            print("="*60 + "\n")
    finally:
        # Restore original stdout and stderr
        sys.stdout.close()
        sys.stdout = original_stdout
        sys.stderr = original_stderr


if __name__ == "__main__":
    # This must be the first thing in the main block
    multiprocessing.freeze_support()
    main()


if __name__ == "__main__":
    # This must be the first thing in the main block
    multiprocessing.freeze_support()
    main()