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

def main(shutdown_flag=None, output_dir=None, live_data_dict=None, can_interface_choice='peak', can_logger_ready=None, log_queue=None, can_summary_data=None):
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
    log_file = open(console_log_filepath, 'a', buffering=1) # Line-buffered
    sys.stdout = log_file
    sys.stderr = log_file
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
    print("\n[+] Initializing worker processes and dual pipelines...")
    manager = multiprocessing.Manager()

    # --- DUAL PIPELINE: Create two separate queues for high and low frequency messages ---
    high_freq_raw_queue = multiprocessing.Queue(maxsize=config.HIGH_FREQ_QUEUE_SIZE)
    low_freq_raw_queue = multiprocessing.Queue(maxsize=config.LOW_FREQ_QUEUE_SIZE)
    
    # --- Shared queues for results and metadata ---
    log_queue = multiprocessing.Queue(maxsize=16384)
    worker_signals_queue = multiprocessing.Queue()
    
    perf_tracker = manager.dict()
    
    # --- DUAL PIPELINE: Create two lists to hold processes for each pipeline ---
    high_freq_processes = []
    low_freq_processes = []
    
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
        # --- DUAL PIPELINE: Pass both high and low frequency queues to the dispatcher ---
        dispatcher_thread = CANReader(
            bus_params=bus_params, 
            data_queues={'high': high_freq_raw_queue, 'low': low_freq_raw_queue}, 
            id_to_queue_map=id_to_queue_map, 
            perf_tracker=perf_tracker,
            connection_event=connection_event,
            shutdown_flag=shutdown_flag
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
        log_writer_thread = LogWriter(log_queue=log_queue, filepath=output_filepath, perf_tracker=perf_tracker, shutdown_flag=shutdown_flag)
        log_writer_thread.start()
        print(" -> Log writer thread started.")

        # --- DUAL PIPELINE: Start the high-frequency worker pool ---
        print(f" -> Starting {config.NUM_HIGH_FREQ_WORKERS} high-frequency decoding processes...")
        for i in range(config.NUM_HIGH_FREQ_WORKERS):
            p = multiprocessing.Process(
                target=processing_worker,
                args=(i, decoding_rules, high_freq_raw_queue, log_queue, perf_tracker, live_data_dict, can_logger_ready, shutdown_flag, worker_signals_queue),
                daemon=True,
                name=f"HighFreqWorker-{i}"
            )
            high_freq_processes.append(p)
            p.start()

        # --- DUAL PIPELINE: Start the low-frequency worker pool ---
        print(f" -> Starting {config.NUM_LOW_FREQ_WORKERS} low-frequency decoding processes...")
        for i in range(config.NUM_LOW_FREQ_WORKERS):
            p = multiprocessing.Process(
                target=processing_worker,
                args=(i + config.NUM_HIGH_FREQ_WORKERS, decoding_rules, low_freq_raw_queue, log_queue, perf_tracker, live_data_dict, can_logger_ready, shutdown_flag, worker_signals_queue),
                daemon=True,
                name=f"LowFreqWorker-{i}"
            )
            low_freq_processes.append(p)
            p.start()

        print("\n[+] Logging data... Press Ctrl-C to stop.")
        last_check_time = time.time()
        
        all_processes = high_freq_processes + low_freq_processes
        while not (shutdown_flag and shutdown_flag.is_set()):
            # --- Health Checks for all processes and threads ---
            if not all(p.is_alive() for p in all_processes):
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
                for i, p in enumerate(all_processes):
                    logger.debug(f"[HEALTH CHECK] Worker process {i} (PID: {p.pid}, Name: {p.name}) alive: {p.is_alive()}")
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
        print("\n[+] Initiating graceful shutdown of CAN logger components...")
        if shutdown_flag:
            print(" -> Setting shutdown_flag...")
            shutdown_flag.set()

        print(" -> Stopping CANReader thread...")
        if dispatcher_thread and dispatcher_thread.is_alive():
            dispatcher_thread.stop()
            dispatcher_thread.join(timeout=2)
            if dispatcher_thread.is_alive():
                print(" -> Warning: CANReader thread did not terminate gracefully.")

        print(" -> Stopping worker processes...")
        # --- DUAL PIPELINE: Signal both high and low frequency queues to stop ---
        for _ in high_freq_processes:
            try:
                high_freq_raw_queue.put(None, timeout=0.1)
            except Exception:
                pass
        for _ in low_freq_processes:
            try:
                low_freq_raw_queue.put(None, timeout=0.1)
            except Exception:
                pass

        # --- DUAL PIPELINE: Join all processes from both pools ---
        all_processes = high_freq_processes + low_freq_processes
        for p in all_processes:
            p.join(timeout=2)
        
        for p in all_processes:
            if p.is_alive():
                print(f" -> Warning: Worker process {p.pid} ({p.name}) did not exit gracefully. Terminating.")
                p.terminate()
                p.join()

        print(" -> Stopping LogWriter thread...")
        if log_writer_thread and log_writer_thread.is_alive():
            log_writer_thread.stop()
            log_writer_thread.join(timeout=2)
            if log_writer_thread.is_alive():
                print(" -> Warning: LogWriter thread did not terminate gracefully.")
        
        print(" -> All CAN logger components stopped.")
        
        logged_signals_set = set()
        while not worker_signals_queue.empty():
            try:
                # Each item in this queue is a set of signal names from a worker
                signal_set = worker_signals_queue.get_nowait()
                if isinstance(signal_set, set):
                    logged_signals_set.update(signal_set)
            except Exception:
                break
        
        # --- Final Report: Populate shared summary dict ---
        if can_summary_data is not None:
            # Convert sets to lists for compatibility with Manager.dict
            can_summary_data['logged_signals'] = list(logged_signals_set)
            can_summary_data['all_signals'] = list(all_monitoring_signals)

        # --- Original print statements are removed as the main process will now handle this ---
        
        print(" -> Logging complete.")
        
        print("\n--- Performance Report ---")
        try:
            dispatch_count = perf_tracker.get('dispatch_count', 0)
            if dispatch_count > 0:
                avg_dispatch = (perf_tracker.get('dispatch_total_time', 0) / dispatch_count) * 1_000_000
                print(f"Avg. Dispatch Time : {avg_dispatch:.2f} µs/msg ({dispatch_count} msgs)")

            processing_count = perf_tracker.get('processing_msg_count', 0)
            if processing_count > 0:
                avg_processing = (perf_tracker.get('processing_total_time', 0) / processing_count) * 1_000_000
                print(f"Avg. Processing Time: {avg_processing:.2f} µs/msg ({processing_count} msgs)")

            log_batch_count = perf_tracker.get('log_write_batch_count', 0)
            if log_batch_count > 0:
                avg_log_write = (perf_tracker.get('log_write_total_time', 0) / log_batch_count) * 1_000
                print(f"Avg. Log Write Time : {avg_log_write:.2f} ms/batch ({log_batch_count} batches)")

        except (KeyError, ZeroDivisionError) as e:
            print(f"Could not generate a full performance report: {e}")
        finally:
            # Restore original stdout and stderr
            if log_file:
                log_file.close()
            sys.stdout = original_stdout
            sys.stderr = original_stderr


if __name__ == "__main__":
    # This must be the first thing in the main block
    multiprocessing.freeze_support()
    main()