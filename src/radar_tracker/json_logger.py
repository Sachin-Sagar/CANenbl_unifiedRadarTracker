# src/json_logger.py

import json
import numpy as np
import queue
from PyQt5.QtCore import QObject, pyqtSignal
from .console_logger import logger

# Import the FrameData class definition
from .hardware.read_and_parse_frame import FrameData

class CustomEncoder(json.JSONEncoder):
    """
    A robust JSON encoder that can handle FrameData objects and NumPy types.
    """
    def default(self, obj):
        if isinstance(obj, FrameData):
            # Manually build a dictionary from the FrameData object
            serializable_dict = {
                "header": obj.header,
                "num_points": obj.num_points,
                "num_targets": obj.num_targets,
                "stats_info": obj.stats_info,
                "point_cloud": obj.point_cloud.tolist(), # Convert numpy array to list
                "target_list": {}
            }
            # Also convert any numpy arrays inside the target_list dictionary
            if obj.target_list:
                for key, value in obj.target_list.items():
                    if isinstance(value, np.ndarray):
                        serializable_dict["target_list"][key] = value.tolist()
                    else:
                        serializable_dict["target_list"][key] = value
            return serializable_dict

        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)

class DataLogger(QObject):
    """
    A threaded logger that saves incoming radar data to a JSON file.
    """
    finished = pyqtSignal()

    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self.data_queue = queue.Queue()
        self.is_running = True
        self.log_file = None
        self.first_frame = True

    def run(self):
        """This method runs in the background and handles all file I/O."""
        try:
            self.log_file = open(self.filename, 'w')
            self.log_file.write('[') # Start of the JSON array
            logger.info(f"--- Logging raw radar data to {self.filename} ---")

            while self.is_running or not self.data_queue.empty():
                try:
                    # Wait for data with a timeout to remain responsive
                    frame = self.data_queue.get(timeout=0.1)
                    
                    if not self.first_frame:
                        self.log_file.write(',\n') # Add comma for valid JSON
                    
                    # Use our custom encoder to write the FrameData object
                    json.dump(frame, self.log_file, cls=CustomEncoder, indent=4)
                    self.first_frame = False
                    self.data_queue.task_done()

                except queue.Empty:
                    continue # No data, just loop again

        except Exception as e:
            logger.error(f"ERROR in logger thread: {e}")
        finally:
            if self.log_file:
                self.log_file.write(']') # End of the JSON array
                self.log_file.close()
                logger.info(f"--- Raw data log file {self.filename} finalized. ---")
            self.finished.emit()

    def add_data(self, frame_data):
        """Adds a new frame to the queue to be logged."""
        self.data_queue.put(frame_data)

    def stop(self):
        """Signals the logger to finish writing and stop."""
        logger.info("--- Stopping data logger... ---")
        self.is_running = False