# src/main_playback.py

import numpy as np
import logging
from datetime import datetime, timedelta

from .tracking.data_loader import load_fhist_data, load_and_sync_can_data
from .tracking.tracker import RadarTracker
from .tracking.parameters import define_parameters
from .tracking.update_and_save_history import update_and_save_history
from .console_logger import setup_logging
from .data_adapter import adapt_matlab_frame_to_fhist

def interp_with_extrap(x, xp, fp):
    """
    Performs 1D linear interpolation, with extrapolation.
    This version is robust to both scalar and array inputs for x.
    """
    xp = np.asarray(xp)
    fp = np.asarray(fp)

    # Check if the input x is a single number (scalar)
    is_scalar = not isinstance(x, (list, tuple, np.ndarray))
    
    # Temporarily convert scalar to a 1-element array for consistent processing
    if is_scalar:
        x = np.array([x])

    # Perform standard interpolation
    y = np.interp(x, xp, fp)

    # --- Extrapolation for values of x below the xp range ---
    ind_below = x < xp[0]
    if np.any(ind_below):
        # Linearly extrapolate using the slope of the first two points
        y[ind_below] = fp[0] + (x[ind_below] - xp[0]) * (fp[1] - fp[0]) / (xp[1] - xp[0])
        
    # --- Extrapolation for values of x above the xp range ---
    ind_above = x > xp[-1]
    if np.any(ind_above):
        # Linearly extrapolate using the slope of the last two points
        y[ind_above] = fp[-1] + (x[ind_above] - xp[-1]) * (fp[-1] - fp[-2]) / (xp[-1] - xp[-2])
    
    # Return a scalar if the original input was a scalar
    if is_scalar:
        return y[0]
    
    return y

def run_playback():
    """
    Runs the radar tracker in playback mode from pre-recorded files.
    """
    logging.info("--- Starting Radar Tracking in Playback Mode ---")
    
    fhist_path = input("Please enter the path to the radar history file (.mat): ")
    fhist_matlab, radar_start_datetime = load_fhist_data(fhist_path)
    if fhist_matlab is None:
        logging.error("Failed to load fHist file. Exiting playback.")
        return

    can_log_path = input("Please enter the path to the CAN log file (.mat): ")
    snipped_can_signals = load_and_sync_can_data(can_log_path, radar_start_datetime, fhist_matlab)
    if snipped_can_signals is None:
        logging.warning("Proceeding without CAN data.")

    params = define_parameters()
    tracker = RadarTracker(params)
    fhist_history = []
    num_frames = len(fhist_matlab)

    for frame_idx in range(num_frames):
        if frame_idx % 50 == 0:
            logging.info(f"--- Processing frame {frame_idx}/{num_frames} ---")

        # <-- This is the key change: Adapt the frame before processing
        current_frame = adapt_matlab_frame_to_fhist(fhist_matlab[frame_idx])
        
        # --- Interpolate CAN Signals with Extrapolation ---
        can_data_for_frame = {}
        if radar_start_datetime and snipped_can_signals:
            current_radar_posix = (radar_start_datetime + timedelta(milliseconds=current_frame.timestamp)).timestamp()
            for signal_name, signal_data in snipped_can_signals.items():
                timestamps = signal_data['posix_timestamps']
                data = signal_data['data']
                
                if len(timestamps) < 2:
                    interp_value = data[0] if len(data) > 0 else np.nan
                else:
                    interp_value = interp_with_extrap(current_radar_posix, timestamps, data)
                can_data_for_frame[signal_name] = interp_value
        
        # Process the now-adapted frame
        updated_tracks, processed_frame = tracker.process_frame(current_frame, can_signals=can_data_for_frame)
        fhist_history.append(processed_frame)

    # --- Finalization ---
    logging.info(f"\n--- Playback Complete ---")
    logging.info(f"Processed {num_frames} frames. Final number of tracks: {len(tracker.all_tracks)}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"output/track_history_playback_{timestamp}.json"
    update_and_save_history(
        tracker.all_tracks,
        fhist_history,
        filename,
        params=tracker.params
    )

if __name__ == '__main__':
    setup_logging()
    run_playback()