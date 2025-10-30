
import sys
import os

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from radar_tracker.main import main as radar_main
from radar_tracker.console_logger import setup_logging

if __name__ == '__main__':
    # Configure logging for the entire application
    setup_logging()
    
    # Launch the radar application
    radar_main()
