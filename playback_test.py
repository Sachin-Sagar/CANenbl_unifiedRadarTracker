# playback_test.py

import os
import time
from datetime import datetime
import multiprocessing
import signal
import threading
import json
import queue

def main_playback(input_filepath):
    """
    Main function to run the CAN logger in playback mode from a log file.
    """
    # --- Imports from the can_logger_app ---
    from src.can_logger_app import config, utils
    from src.can_logger_app.data_processor import processing_worker
    from src.can_logger_app.log_writer import LogWriter

    # --- 1. Load Configuration ---
    print("\n[+] Loading configuration for playback...")
    dbc_path = os.path.join(config.INPUT_DIRECTORY, config.DBC_FILE)
    signal_list_path = os.path.join(config.INPUT_DIRECTORY, config.SIGNAL_LIST_FILE)

    try:
        import cantools
        db = cantools.database.load_file(dbc_path)
    except Exception as e:
        print(f"Error: Failed to parse DBC file '{dbc_path}': {e}. Exiting.")
        return

    high_freq_signals, low_freq_signals, id_to_queue_map = utils.load_signals_to_monitor(signal_list_path)
    if id_to_queue_map is None: return

    print(" -> Pre-compiling decoding rules...")
    decoding_rules = utils.precompile_decoding_rules(db, {**high_freq_signals, **low_freq_signals})

    # --- Setup output directory for the test run ---
    timestamp_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    output_dir = os.path.join(config.OUTPUT_DIRECTORY, f"playback_test_{timestamp_str}")
    os.makedirs(output_dir, exist_ok=True)
    output_filepath = os.path.join(output_dir, f"can_log_playback_output.json")
    print(f" -> Playback output will be saved to: '{output_filepath}'")

    # --- 2. Initialize Multiprocessing Components ---
    print("\n[+] Initializing worker processes and dual pipelines for playback...")
    manager = multiprocessing.Manager()
    shutdown_flag = multiprocessing.Event()

    high_freq_raw_queue = multiprocessing.Queue(maxsize=config.HIGH_FREQ_QUEUE_SIZE)
    low_freq_raw_queue = multiprocessing.Queue(maxsize=config.LOW_FREQ_QUEUE_SIZE)
    log_queue = multiprocessing.Queue(maxsize=16384)
    worker_signals_queue = multiprocessing.Queue()
    perf_tracker = manager.dict()

    high_freq_processes = []
    low_freq_processes = []
    
    playback_dispatcher_thread = None
    log_writer_thread = None

    # --- Graceful Shutdown Handler ---
    def signal_handler(signum, frame):
        print("\n[+] Shutdown signal received, stopping playback...")
        shutdown_flag.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # --- 3. Start Playback Dispatcher ---
        print(" -> Initializing CAN Playback Dispatcher thread...")
        playback_dispatcher_thread = CANPlaybackReader(
            input_filepath=input_filepath,
            data_queues={'high': high_freq_raw_queue, 'low': low_freq_raw_queue},
            id_to_queue_map=id_to_queue_map,
            perf_tracker=perf_tracker,
            shutdown_flag=shutdown_flag
        )
        playback_dispatcher_thread.start()
        print(" -> CAN Playback Dispatcher thread started.")

        # --- 4. Start Log Writer ---
        print(" -> Initializing log writer thread...")
        log_writer_thread = LogWriter(log_queue=log_queue, filepath=output_filepath, perf_tracker=perf_tracker, shutdown_flag=shutdown_flag)
        log_writer_thread.start()
        print(" -> Log writer thread started.")

        # --- 5. Start Worker Pools ---
        print(f" -> Starting {config.NUM_HIGH_FREQ_WORKERS} high-frequency decoding processes...")
        for i in range(config.NUM_HIGH_FREQ_WORKERS):
            p = multiprocessing.Process(
                target=processing_worker,
                args=(i, decoding_rules, high_freq_raw_queue, log_queue, perf_tracker, None, None, shutdown_flag, worker_signals_queue),
                daemon=True, name=f"HighFreqWorker-{i}"
            )
            high_freq_processes.append(p)
            p.start()

        print(f" -> Starting {config.NUM_LOW_FREQ_WORKERS} low-frequency decoding processes...")
        for i in range(config.NUM_LOW_FREQ_WORKERS):
            p = multiprocessing.Process(
                target=processing_worker,
                args=(i + config.NUM_HIGH_FREQ_WORKERS, decoding_rules, low_freq_raw_queue, log_queue, perf_tracker, None, None, shutdown_flag, worker_signals_queue),
                daemon=True, name=f"LowFreqWorker-{i}"
            )
            low_freq_processes.append(p)
            p.start()

        print("\n[+] Running playback... Press Ctrl-C to stop.")
        
        # --- Wait for playback to finish ---
        playback_dispatcher_thread.join()
        print("\n[+] Playback file finished.")

        # --- Signal workers to finish ---
        print("[+] Sending shutdown signal to workers...")
        for _ in high_freq_processes:
            high_freq_raw_queue.put(None)
        for _ in low_freq_processes:
            low_freq_raw_queue.put(None)

        # --- Wait for all queues to be empty ---
        all_processes = high_freq_processes + low_freq_processes
        for p in all_processes:
            p.join()

        # --- Wait for log queue to be empty ---
        while not log_queue.empty():
            time.sleep(0.1)
        
        print("[+] All workers finished.")
        shutdown_flag.set() # Signal log writer to stop

    except (KeyboardInterrupt, SystemExit):
        print("\n\n[+] Ctrl-C detected. Shutting down gracefully...")
        shutdown_flag.set()
    finally:
        print("\n[+] Initiating graceful shutdown of playback components...")

        if playback_dispatcher_thread and playback_dispatcher_thread.is_alive():
            playback_dispatcher_thread.join(timeout=2)

        all_processes = high_freq_processes + low_freq_processes
        for p in all_processes:
            if p.is_alive():
                p.terminate()
                p.join()

        if log_writer_thread and log_writer_thread.is_alive():
            log_writer_thread.join(timeout=2)
        
        print(" -> All playback components stopped.")
        print(f"\n--- Playback Test Complete ---")
        print(f" -> Input file: {input_filepath}")
        print(f" -> Output file: {output_filepath}")
        print("---------------------------------")


class CANPlaybackReader(threading.Thread):
    """
    A thread that reads a raw CAN log file (candump format) and simulates a CAN bus
    by dispatching messages to the processing queues.
    """
    def __init__(self, input_filepath, data_queues, id_to_queue_map, perf_tracker, shutdown_flag, playback_speed=1.0):
        super().__init__(daemon=True)
        self.input_filepath = input_filepath
        self.data_queues = data_queues
        self.id_to_queue_map = id_to_queue_map
        self.perf_tracker = perf_tracker
        self.shutdown_flag = shutdown_flag
        self.playback_speed = playback_speed
        self.messages_sent = 0
        # Regex to parse candump format: (timestamp) interface id#data
        self.log_pattern = re.compile(r'\s*\((?P<timestamp>[\d.]+)\)\s+(?P<interface>\w+)\s+(?P<id>[A-F0-9]+)#(?P<data>[A-F0-9]*)')

    def run(self):
        print(f" -> [PlaybackReader] Starting raw CAN playback from: {self.input_filepath}")
        try:
            with open(self.input_filepath, 'r') as f:
                for line in f:
                    if self.shutdown_flag.is_set():
                        break
                    
                    match = self.log_pattern.match(line)
                    if not match:
                        if line.strip():
                            print(f"Warning: Skipping malformed line in input file: {line.strip()}")
                        continue

                    try:
                        log_entry = match.groupdict()
                        msg_id_int = int(log_entry['id'], 16)
                        queue_name = self.id_to_queue_map.get(msg_id_int)

                        if queue_name:
                            # Reconstruct the message with real raw data
                            data_to_queue = {
                                "timestamp": float(log_entry['timestamp']),
                                "arbitration_id": msg_id_int,
                                "data": bytes.fromhex(log_entry['data'])
                            }
                            
                            self.data_queues[queue_name].put(data_to_queue)
                            self.messages_sent += 1
                        
                        # Optional: Add a sleep to simulate real-time playback
                        time.sleep(0.001 / self.playback_speed)

                    except (ValueError, KeyError) as e:
                        print(f"Warning: Error processing line: {line.strip()} ({e})")
                        continue
        
        except FileNotFoundError:
            print(f"FATAL [PlaybackReader]: Input file not found at '{self.input_filepath}'")
        except Exception as e:
            print(f"FATAL [PlaybackReader]: An error occurred: {e}")
        finally:
            print(f" -> [PlaybackReader] Finished. Sent {self.messages_sent} messages.")


if __name__ == "__main__":
    import argparse
    import re # Import re for the pattern
    parser = argparse.ArgumentParser(description="Run a playback test of the CAN logger using a pre-recorded raw CAN log file (candump format).")
    parser.add_argument("input_file", nargs='?', help="Optional: Path to the input raw_can.log file. If not provided, you will be prompted.")
    args = parser.parse_args()

    input_filepath = args.input_file
    if input_filepath is None:
        while True:
            input_filepath = input("Please enter the path to the raw_can.log file: ").strip()
            if os.path.exists(input_filepath):
                break
            else:
                print(f"Error: File not found at '{input_filepath}'. Please try again.")

    if not os.path.exists(input_filepath):
        print(f"Error: Input file not found: {input_filepath}")
    else:
        multiprocessing.freeze_support()
        main_playback(input_filepath)
