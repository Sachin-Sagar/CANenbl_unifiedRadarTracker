# src/main_live.py

import sys
import time
from datetime import datetime
import numpy as np
import logging
import psutil
import os
import serial.tools.list_ports
import platform

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
from .console_logger import setup_logging
from can_service.live_can_manager import LiveCANManager
import config as root_config
from .tracking.utils.coordinate_transforms import interp_with_extrap


import serial.tools.list_ports

# --- Configuration ---
if sys.platform == "win32":
    CLI_COMPORT_NUM = 'COM11'
elif sys.platform == "linux":
    ports = serial.tools.list_ports.comports()
    if not ports:
        logging.error("No serial ports found. Please ensure the radar is connected and you have the necessary permissions (e.g., member of 'dialout' group).")
        sys.exit(1)
    elif len(ports) == 1:
        CLI_COMPORT_NUM = ports[0].device
        logging.info(f"Automatically selected serial port: {CLI_COMPORT_NUM}")
    else:
        print("Available serial ports:")
        for i, port in enumerate(ports):
            print(f"  {i}: {port.device}")
        while True:
            try:
                choice = int(input("Please select the serial port for the radar: "))
                if 0 <= choice < len(ports):
                    CLI_COMPORT_NUM = ports[choice].device
                    break
                else:
                    print("Invalid choice.")
            except ValueError:
                print("Invalid input.")
else:
    logging.error(f"Unsupported OS '{sys.platform}' detected. Please set COM port manually.")
    CLI_COMPORT_NUM = None

CONFIG_FILE_PATH = 'configs/profile_80_m_40mpsec_bsdevm_16tracks_dyClutter.cfg'
INITIAL_BAUD_RATE = 115200

class RadarWorker(QObject):
    """
    This worker runs the main radar processing loop and also manages
    the JSON data logger.
    """
    frame_ready = pyqtSignal(object)
    finished = pyqtSignal()
    close_visualizer = pyqtSignal()

    def __init__(self, cli_com_port, config_file, output_dir, shutdown_flag=None):
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
        
        # Initialize CAN Manager
        dbc_path = os.path.join(root_config.INPUT_DIRECTORY, root_config.DBC_FILE)
        signal_list_path = os.path.join(root_config.INPUT_DIRECTORY, root_config.SIGNAL_LIST_FILE)
        self.can_manager = LiveCANManager(root_config, dbc_path, signal_list_path)

    def run(self):
        """The main processing loop."""
        process = psutil.Process(os.getpid())

        log_filename = os.path.join(self.output_dir, f"radar_log.json")
        self.logger_thread = QThread()
        self.data_logger = DataLogger(log_filename)
        self.data_logger.moveToThread(self.logger_thread)
        self.logger_thread.started.connect(self.data_logger.run)
        self.logger_thread.start()

        # Start CAN service
        self.can_manager.start()

        # If on Raspberry Pi, blink LED to indicate successful start
        if platform.system() == "Linux":
            from can_logger_app.gpio_handler import blink_onboard_led
            blink_onboard_led(3)

        self.params_radar, self.h_data_port = self._configure_sensor()
        if not self.params_radar or not self.h_data_port:
            logging.error("Failed to configure sensor. Exiting worker thread.")
            self.stop()
            self.finished.emit()
            self.close_visualizer.emit()
            return

        params_tracker = define_parameters()
        self.tracker = RadarTracker(params_tracker)

        logging.info("--- Starting Live Tracking ---")
        while self.is_running:
            if self.shutdown_flag and self.shutdown_flag.is_set():
                self.is_running = False
                continue

            frame_data = read_and_parse_frame(self.h_data_port, self.params_radar)
            if not frame_data or not frame_data.header:
                continue
            
            self.data_logger.add_data(frame_data)

            fhist_frame = adapt_frame_data_to_fhist(frame_data, self.tracker.last_timestamp_ms)
            
            # Get and interpolate CAN data
            can_data_for_frame = self._interpolate_can_data(fhist_frame.timestamp)

            updated_tracks, processed_frame = self.tracker.process_frame(fhist_frame, can_signals=can_data_for_frame)
            self.fhist_history.append(processed_frame)

            num_confirmed_tracks = sum(1 for t in updated_tracks if t.get('isConfirmed') and not t.get('isLost'))
            
            if self.tracker.frame_idx > 0 and self.tracker.frame_idx % 100 == 0:
                mem_info = process.memory_info()
                ram_mb = mem_info.rss / (1024 * 1024) 
                cpu_percent = process.cpu_percent(interval=0.1)
                logging.info(f"[PERFORMANCE] Frame: {self.tracker.frame_idx} | CPU: {cpu_percent:.2f}% | RAM: {ram_mb:.2f} MB")

            logging.info(f"Frame: {self.tracker.frame_idx} | Detections: {frame_data.num_points} | Confirmed Tracks: {num_confirmed_tracks}")

            self.frame_ready.emit(frame_data)

        self._save_tracking_history()
        self.finished.emit()

    def _interpolate_can_data(self, radar_timestamp_ms):
        can_data_for_frame = {}
        can_buffers = self.can_manager.get_signal_buffers()
        radar_posix_timestamp = radar_timestamp_ms / 1000.0

        for signal_name, buffer in can_buffers.items():
            if not buffer:
                continue

            timestamps = [item[0] for item in buffer]
            values = [item[1] for item in buffer]

            if len(timestamps) < 2:
                interp_value = values[0] if values else np.nan
            else:
                interp_value = interp_with_extrap(radar_posix_timestamp, timestamps, values)
            
            can_data_for_frame[signal_name] = interp_value
        
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
        logging.info("\n--- Starting Sensor Configuration ---")
        h_port = hw_comms_utils.configure_control_port(self.cli_com_port, INITIAL_BAUD_RATE)
        if not h_port: return None, None
        for command in cli_cfg:
            logging.info(f"> {command}")
            h_port.write((command + '\n').encode())
            time.sleep(0.1)
            if "baudRate" in command:
                time.sleep(0.2)
                try:
                    h_port.baudrate = target_baud_rate
                    logging.info(f"  Baud rate changed to {target_baud_rate}")
                except Exception as e:
                    logging.error(f"ERROR: Failed to change baud rate: {e}")
                    h_port.close()
                    return None, None
        logging.info("--- Configuration complete ---\n")
        hw_comms_utils.reconfigure_port_for_data(h_port)
        return params, h_port

    def _save_tracking_history(self):
        """Saves the final processed tracking history."""
        logging.info("\n--- Saving tracking history ---")
        if self.tracker and self.fhist_history:
            filename = os.path.join(self.output_dir, "track_history.json")
            update_and_save_history(
                self.tracker.all_tracks,
                self.fhist_history,
                filename,
                params=self.tracker.params
            )
        else:
            logging.warning("No frame history was processed, nothing to save.")

    def stop(self):
        """Stops the processing loop and the logger."""
        logging.info("--- Stopping worker thread... ---")
        self.is_running = False
        
        if self.data_logger:
            self.data_logger.stop()
        if self.logger_thread:
            self.logger_thread.quit()
            self.logger_thread.wait()

        if self.can_manager:
            self.can_manager.stop()

        if self.h_data_port and self.h_data_port.is_open:
            self.h_data_port.close()
            logging.info("--- Serial port closed ---")

def main(output_dir, shutdown_flag=None):
    """Main application entry point."""
    # --- THIS IS THE FIX ---
    # The setup_logging() call is removed from here to prevent double-logging.
    # It is now only called once in the main.py entry point.
    # --- END OF FIX ---
    app = QApplication(sys.argv)
    worker_thread = QThread()
    radar_worker = RadarWorker(CLI_COMPORT_NUM, CONFIG_FILE_PATH, output_dir, shutdown_flag)
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
    sys.exit(app.exec_())

if __name__ == '__main__':
    # This allows the script to be run standalone for testing.
    setup_logging()
    main()