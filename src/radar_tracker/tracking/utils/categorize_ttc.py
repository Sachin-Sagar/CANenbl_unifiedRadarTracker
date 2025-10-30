# src/utils/categorize_ttc.py

import numpy as np

def categorize_ttc(ttc, radial_velocity_relative, track_x_position):
    """
    Converts a Time-to-Collision (TTC) value into a predefined risk category.

    Args:
        ttc (float): Time-to-collision in seconds. Can be np.inf.
        radial_velocity_relative (float): The relative radial velocity of the track.
        track_x_position (float): The Cartesian x-position of the track.

    Returns:
        int: An integer representing the risk category:
             -1: Track is moving away or outside the lateral safety corridor.
              0: Low risk (TTC > 30s)
              1: Medium risk (10s < TTC <= 30s)
              2: High risk (5s < TTC <= 10s)
              3: Critical risk (TTC <= 5s)
    """
    # A positive TTC category is only assigned if the track is within the
    # lateral safety corridor of x = -5m to +5m.
    if radial_velocity_relative >= 0 or abs(track_x_position) > 5:
        return -1  # Moving away, stationary, or outside the safety corridor
    elif np.isinf(ttc) or ttc > 30:
        return 0  # Large positive TTC, low risk
    elif ttc > 10:
        return 1  # Medium risk
    elif ttc > 5:
        return 2  # High risk
    else:  # ttc <= 5
        return 3  # Critical risk