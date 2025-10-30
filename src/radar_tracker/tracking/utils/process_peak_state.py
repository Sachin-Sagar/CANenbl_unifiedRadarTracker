# src/utils/process_peak_state.py

def process_peak_state(state_in, current_time, current_yaw_rate, min_peak_height, confirmation_samples):
    """
    A stateless function to process one time step of peak detection logic.
    It takes a state dictionary as input and returns the updated state.

    Args:
        state_in (dict): Dictionary representing the current state of the detector.
        current_time (float): The current timestamp.
        current_yaw_rate (float): The current yaw rate.
        min_peak_height (float): The threshold to consider a point as a potential peak.
        confirmation_samples (int): Number of consecutive dropping samples to confirm a peak.

    Returns:
        tuple: A tuple containing (peak_time, peak_value, state_out), where
               peak_time and peak_value are the time and value of a confirmed
               peak, or None if no peak is confirmed. state_out is the
               updated state dictionary.
    """
    # Initialize the state dictionary on the first run
    if 'status' not in state_in:
        state_in = {
            'status': 'RISING',
            'potential_peak': {'time': None, 'value': None},
            'drop_count': 0,
            'prev_time': current_time,
            'prev_yaw_rate': current_yaw_rate
        }

    # Default outputs
    peak_time = None
    peak_value = None
    state_out = state_in.copy() # Work on a copy to avoid modifying the input dict directly

    # --- Main State Machine ---
    status = state_out['status']

    if status == 'RISING':
        if (current_yaw_rate < state_out['prev_yaw_rate'] and
                state_out['prev_yaw_rate'] > min_peak_height):
            state_out['potential_peak']['time'] = state_out['prev_time']
            state_out['potential_peak']['value'] = state_out['prev_yaw_rate']
            state_out['drop_count'] = 1
            state_out['status'] = 'PEAK_UNCERTAIN'
            
    elif status == 'PEAK_UNCERTAIN':
        if current_yaw_rate < state_out['prev_yaw_rate']:
            state_out['drop_count'] += 1
        else:
            state_out['status'] = 'RISING'
            state_out['drop_count'] = 0
            
        if state_out['drop_count'] >= confirmation_samples:
            peak_time = state_out['potential_peak']['time']
            peak_value = state_out['potential_peak']['value']
            state_out['status'] = 'FALLING'
            state_out['drop_count'] = 0
            
    elif status == 'FALLING':
        if current_yaw_rate > state_out['prev_yaw_rate']:
            state_out['status'] = 'RISING'

    # Update previous data for the next call
    state_out['prev_time'] = current_time
    state_out['prev_yaw_rate'] = current_yaw_rate

    return peak_time, peak_value, state_out