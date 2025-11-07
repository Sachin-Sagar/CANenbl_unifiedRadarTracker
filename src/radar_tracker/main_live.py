# src/main_live.py

import sys
import time
from datetime import datetime
import numpy as np
from .console_logger import logger
import psutil
import os
import serial.tools.list_ports
import platform
import copy

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread, pyqtSignal, QObject

# --- Import project modules ---
from .hardware import hw_comms_utils, parsing_utils
from .hardware.read_and_parse_frame import read_and_parse_frame
from .data_adapter import adapt_frame_data_to_fhist
from .tracking.tracker import RadarTracker
from .tracking.parameters import define_parameters
from .tracking.update_and_save_history import update_and_save_history
from .live_visualizer import LiveVisualizer
from .json_logger import DataLogger
from .console_logger import logger
# --- REMOVED LiveCANManager ---
import config as root_config
from .tracking.utils.coordinate_transforms import interp_with_extrap


import serial.tools.list_ports

# --- Configuration ---
CONFIG_FILE_PATH = 'configs/profile_80_m_40mpsec_bsdevm_16tracks_dyClutter.cfg'
INITIAL_BAUD_RATE = 115200

def select_com_port():
    """
    Prompts the user to select a serial port for the radar.
    This function is called only when live mode is active.
    """
    if sys.platform == "win32":
        # You may need to adjust this default for your setup
        default_port = 'COM11'
        ports = serial.tools.list_ports.comports()
        if not any(p.device == default_port for p in ports):
            logger.warning(f"Default port {default_port} not found.")
        return default_port
        
    elif sys.platform == "linux":
        ports = serial.tools.list_ports.comports()
        if not ports:
            logger.error("No serial ports found. Please ensure the radar is connected and you have the necessary permissions (e.g., member of 'dialout' group).")
            return None
        elif len(ports) == 1:
            selected_port = ports[0].device
            logger.info(f"Automatically selected serial port: {selected_port}")
            return selected_port
        else:
            logger.info("Available serial ports:")
            for i, port in enumerate(ports):
                logger.info(f"  {i}: {port.device}")
            while True:
                try:
                    choice = int(input("Please select the serial port for the radar: "))
                    if 0 <= choice < len(ports):
                        return ports[choice].device
                    else:
                        logger.info("Invalid choice.")
                except ValueError:
                    logger.info("Invalid input.")
    else:
        logger.error(f"Unsupported OS '{sys.platform}' detected. Please set COM port manually.")
        return None

class RadarWorker(QObject):
    """
    This worker runs the main radar processing loop and also manages
    the JSON data logger.
    """
    frame_ready = pyqtSignal(object)
    finished = pyqtSignal()
    close_visualizer = pyqtSignal()

    # MODIFIED: Accepts shared_live_can_data dict
    def __init__(self, cli_com_port, config_file, output_dir, shutdown_flag=None, shared_live_can_data=None, can_logger_ready=None):
        super().__init__()
        self.cli_com_port = cli_com_port
        self.config_file = config_file
        self.output_dir = output_dir
        self.is_running = True
        self.params_radar = None
        self.h_data_port = None
        self.tracker = None
        self.fhist_history = []
        self.logger_thread = None
        self.data_logger = None
        self.shutdown_flag = shutdown_flag
        self.can_logger_ready = can_logger_ready
        
        # MODIFIED: Store the shared dictionary, remove CAN manager
        self.shared_live_can_data = shared_live_can_data
        logger.info(f"RadarWorker initialized. Live CAN data sharing is {'ENABLED' if shared_live_can_data is not None else 'DISABLED'}.")


    def run(self):
        """The main processing loop."""
        process = psutil.Process(os.getpid())

        log_filename = os.path.join(self.output_dir, f"radar_log.json")
        self.logger_thread = QThread()
        self.data_logger = DataLogger(log_filename)
        self.data_logger.moveToThread(self.logger_thread)
        self.logger_thread.started.connect(self.data_logger.run)
        self.logger_thread.start()

        # MODIFIED: Removed can_manager.start()
        # The CAN logger process is already running, started by main.py

        # If on Raspberry Pi, blink LED to indicate successful start
        if platform.system() == "Linux":
            try:
                from can_logger_app.gpio_handler import blink_onboard_led
                blink_onboard_led(3)
            except ImportError:
                logger.warning("Could not import gpio_handler to blink LED.")


        self.params_radar, self.h_data_port = self._configure_sensor()
        if not self.params_radar or not self.h_data_port:
            logger.error("Failed to configure sensor. Exiting worker thread.")
            self.stop()
            self.finished.emit()
            self.close_visualizer.emit()
            return

        params_tracker = define_parameters()
        self.tracker = RadarTracker(params_tracker)

        # Wait for the CAN logger to be ready
        if self.can_logger_ready:
            logger.debug("--- RadarWorker: Waiting for CAN logger to be ready... ---")
            ready = self.can_logger_ready.wait(timeout=10.0) # 10-second timeout
            if ready:
                logger.debug("--- RadarWorker: CAN logger is ready. Starting tracking. ---")
            else:
                logger.warning("--- RadarWorker: Timed out waiting for CAN logger. Tracking will proceed without live CAN data. ---")

        logger.info("--- Starting Live Tracking ---")
        while self.is_running:
            if self.shutdown_flag and self.shutdown_flag.is_set():
                self.is_running = False
                continue

            frame_data = read_and_parse_frame(self.h_data_port, self.params_radar)
            if not frame_data or not frame_data.header:
                continue
            
            self.data_logger.add_data(frame_data)

            # --- MODIFIED: Get CAN data *before* adapting the frame ---
            # This allows us to inject the vehicle's speed into the frame history
            # object that the tracker uses for ego motion compensation.
            current_timestamp_ms = self.tracker.last_timestamp_ms + 50.0
            can_data_for_frame = self._interpolate_can_data(current_timestamp_ms)
            fhist_frame = adapt_frame_data_to_fhist(frame_data, current_timestamp_ms, can_signals=can_data_for_frame)
            
            # --- MODIFIED: The can_signals are now inside fhist_frame ---
            updated_tracks, processed_frame = self.tracker.process_frame(fhist_frame)
            self.fhist_history.append(processed_frame)

            num_confirmed_tracks = sum(1 for t in updated_tracks if t.get('isConfirmed') and not t.get('isLost'))
            
            if self.tracker.frame_idx > 0 and self.tracker.frame_idx % 100 == 0:
                mem_info = process.memory_info()
                ram_mb = mem_info.rss / (1024 * 1024) 
                cpu_percent = process.cpu_percent(interval=0.1)
                logger.info(f"[PERFORMANCE] Frame: {self.tracker.frame_idx} | CPU: {cpu_percent:.2f}% | RAM: {ram_mb:.2f} MB")

            logger.info(f"Frame: {self.tracker.frame_idx} | Detections: {frame_data.num_points} | Confirmed Tracks: {num_confirmed_tracks}")

            self.frame_ready.emit(frame_data)

        self._save_tracking_history()
        self.finished.emit()

    def _interpolate_can_data(self, radar_timestamp_ms):
        can_data_for_frame = {}
        # MODIFIED: Read from the shared dict
        if self.shared_live_can_data is None:
            return {}

        # Create a deep copy of the shared data to avoid proxy issues
        try:
            # Convert the ManagerProxy to a regular dict and then deepcopy it
            can_buffers = copy.deepcopy(dict(self.shared_live_can_data))
            if root_config.DEBUG_FLAGS.get('log_can_interpolation'):
                logger.debug(f"[INTERPOLATION] Copied shared data: {can_buffers}")
        except Exception as e:
            logger.error(f"[INTERPOLATION] Failed to deepcopy shared_live_can_data: {e}")
            can_buffers = {}
        radar_posix_timestamp = radar_timestamp_ms / 1000.0

        if root_config.DEBUG_FLAGS.get('log_can_interpolation'):
            # Calculate and log the average of the CAN signals for the frame
            avg_can_data = {}
            for signal_name, buffer in can_buffers.items():
                if buffer:
                    values = [item[1] for item in buffer]
                    avg_can_data[signal_name] = np.mean(values)
            logger.debug(f"[INTERPOLATION] Avg. CAN signals for frame: {avg_can_data}")

        for signal_name, buffer in can_buffers.items():
            if not buffer:
                continue
            
            # The buffer is a list of (timestamp, value) tuples
            timestamps = [item[0] for item in buffer]
            values = [item[1] for item in buffer]

            if len(timestamps) < 2:
                interp_value = values[0] if values else np.nan
            else:
                interp_value = interp_with_extrap(radar_posix_timestamp, timestamps, values)
            
            # --- FIX: Cast the interpolated value to a native float ---
            # This prevents numpy data types from corrupting the data later in the pipeline.
            can_data_for_frame[signal_name] = float(interp_value)

        if root_config.DEBUG_FLAGS.get('log_can_interpolation'):
            logger.debug(f"[INTERPOLATION] Interpolated CAN data for frame: {can_data_for_frame}")
        
        return can_data_for_frame

    def _configure_sensor(self):
        """Reads the config file and sends commands to the radar."""
        cli_cfg = parsing_utils.read_cfg(self.config_file)
        if not cli_cfg: return None, None
        params = parsing_utils.parse_cfg(cli_cfg)
        target_baud_rate = INITIAL_BAUD_RATE
        for command in cli_cfg:
            if command.startswith("baudRate"):
                try: target_baud_rate = int(command.split()[1])
                except (ValueError, IndexError): pass
                break
        logger.info("\n--- Starting Sensor Configuration ---")
        h_port = hw_comms_utils.configure_control_port(self.cli_com_port, INITIAL_BAUD_RATE)
        if not h_port: return None, None
        for command in cli_cfg:
            logger.info(f"> {command}")
            h_port.write((command + '\n').encode())
            time.sleep(0.1)
            if "baudRate" in command:
                time.sleep(0.2)
                try:
                    h_port.baudrate = target_baud_rate
                    logger.info(f"  Baud rate changed to {target_baud_rate}")
                except Exception as e:
                    logger.error(f"ERROR: Failed to change baud rate: {e}")
                    h_port.close()
                    return None, None
        logger.info("--- Configuration complete ---\n")
        hw_comms_utils.reconfigure_port_for_data(h_port)
        return params, h_port

    def _save_tracking_history(self):
        """Saves the final processed tracking history."""
        logger.info("\n--- Saving tracking history ---")
        if self.tracker and self.fhist_history:
            filename = os.path.join(self.output_dir, "track_history.json")
            update_and_save_history(
                self.tracker.all_tracks,
                self.fhist_history,
                filename,
                params=self.tracker.params
            )
        else:
            logger.warning("No frame history was processed, nothing to save.")

    def stop(self):
        """Stops the processing loop and the logger."""
        logger.info("--- Stopping worker thread... ---")
        self.is_running = False

        if self.shutdown_flag:
            self.shutdown_flag.set()
        
        if self.data_logger:
            self.data_logger.stop()
        if self.logger_thread:
            self.logger_thread.quit()
            self.logger_thread.wait()

        # MODIFIED: Removed can_manager.stop()
        
        if self.h_data_port and self.h_data_port.is_open:
            self.h_data_port.close()
            logger.info("--- Serial port closed ---")

# MODIFIED: main() now accepts the shared dict
def main(output_dir, shutdown_flag=None, shared_live_can_data=None, can_logger_ready=None):
    """Main application entry point."""
    cli_com_port = select_com_port()
    if cli_com_port is None:
        logger.error("Could not determine COM port. Exiting live mode.")
        # We need to ensure the QApplication doesn't start, but also that the main script can exit gracefully.
        # A simple return should suffice, as the main script will then terminate.
        return

    app = QApplication(sys.argv)
    worker_thread = QThread()
    
    # MODIFIED: Pass the shared dict to the worker
    radar_worker = RadarWorker(
        cli_com_port, 
        CONFIG_FILE_PATH, 
        output_dir, 
        shutdown_flag,
        shared_live_can_data,
        can_logger_ready
    )
    
    radar_worker.moveToThread(worker_thread)
    visualizer = LiveVisualizer(radar_worker, worker_thread)
    radar_worker.close_visualizer.connect(visualizer.close)
    visualizer.show()
    worker_thread.started.connect(radar_worker.run)
    radar_worker.frame_ready.connect(visualizer.update_plot)
    radar_worker.finished.connect(worker_thread.quit)
    radar_worker.finished.connect(radar_worker.deleteLater)
    worker_thread.finished.connect(worker_thread.deleteLater)
    worker_thread.start()
    app.exec_()

if __name__ == '__main__':
    # This allows the script to be run standalone for testing.
    main()