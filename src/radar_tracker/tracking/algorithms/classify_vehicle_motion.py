# src/algorithms/classify_vehicle_motion.py

# Import the utility function we already ported
from ..utils.process_peak_state import process_peak_state

def classify_vehicle_motion(
    time, 
    yaw_rate, 
    turn_yaw_rate_thrs, 
    confirmation_samples,
    right_finder_state,
    left_finder_state
):
    """
    Classifies the ego vehicle's current motion state (straight, turning, or turn completed).
    Manages two separate state dicts for right and left turn detection.

    Args:
        time (float): The current timestamp.
        yaw_rate (float): The current yaw rate in rad/s.
        turn_yaw_rate_thrs (float): Threshold to consider the vehicle is turning.
        confirmation_samples (int): Number of samples to confirm a turn peak.
        right_finder_state (dict): The state dictionary for the right turn detector.
        left_finder_state (dict): The state dictionary for the left turn detector.

    Returns:
        tuple: A tuple containing:
            - state (int): The current motion state (-2 to 2).
            - updated_right_state (dict): The updated right turn state.
            - updated_left_state (dict): The updated left turn state.
    """
    # --- 1. Check for Confirmed Peaks ---
    # Process the right turn detector
    right_peak_t, _, updated_right_state = process_peak_state(
        right_finder_state, time, yaw_rate, turn_yaw_rate_thrs, confirmation_samples
    )
    
    # Process the left turn detector with an inverted signal
    left_peak_t, _, updated_left_state = process_peak_state(
        left_finder_state, time, -yaw_rate, turn_yaw_rate_thrs, confirmation_samples
    )

    # --- 2. Determine Motion State ---
    if right_peak_t is not None:
        state = 2  # Right turn peak confirmed
    elif left_peak_t is not None:
        state = -2  # Left turn peak confirmed
    else:
        # Check for in-progress turns
        if yaw_rate > turn_yaw_rate_thrs:
            state = 1  # Right turn in-progress
        elif yaw_rate < -turn_yaw_rate_thrs:
            state = -1  # Left turn in-progress
        else:
            state = 0  # Straight
            
    return state, updated_right_state, updated_left_state