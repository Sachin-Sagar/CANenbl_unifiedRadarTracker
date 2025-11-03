# src/radar_tracker/json_log_handler.py

import logging

class JSONLogHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log_records = []

    def emit(self, record):
        self.log_records.append(self.format(record))
