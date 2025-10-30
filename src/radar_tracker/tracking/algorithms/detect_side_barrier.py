# src/algorithms/detect_side_barrier.py

import numpy as np

def detect_side_barrier(points, inlier_indices, params, prev_filtered_positions):
    """
    Finds dominant vertical barriers, applies IIR filtering, and calculates
    the final dynamic X-range for the stationary box.

    Args:
        points (np.ndarray): The 2xN Cartesian point cloud.
        inlier_indices (np.ndarray): Indices of points identified as static.
        params (dict): A struct with parameters for barrier detection.
        prev_filtered_positions (dict): The previous filtered barrier struct {'left': x, 'right': x}.

    Returns:
        tuple: A tuple containing (dynamic_x_range, filtered_barrier_positions).
    """
    filtered_barrier_positions = prev_filtered_positions.copy()
    
    if inlier_indices.size == 0:
        return np.array(params['default_x_range']), filtered_barrier_positions

    # Isolate static points and transpose to be Nx2
    static_points = points[:, inlier_indices].T
    
    # Filter points to be within the longitudinal ROI
    valid_y_mask = (static_points[:, 1] >= params['longitudinal_range'][0]) & \
                   (static_points[:, 1] <= params['longitudinal_range'][1])
    roi_points = static_points[valid_y_mask]

    # Separate points into left and right sides
    right_points = roi_points[roi_points[:, 0] > 0]
    left_points = roi_points[roi_points[:, 0] < 0]

    # --- Process Left Barrier ---
    if left_points.shape[0] >= params['min_pts_for_barrier']:
        raw_left_x = np.median(left_points[:, 0])
        
        # Apply IIR filter
        if np.isnan(filtered_barrier_positions['left']):
            filtered_barrier_positions['left'] = raw_left_x
        else:
            alpha = params['iir_alpha_barrier']
            filtered_barrier_positions['left'] = alpha * raw_left_x + \
                                                 (1 - alpha) * filtered_barrier_positions['left']

    # --- Process Right Barrier ---
    if right_points.shape[0] >= params['min_pts_for_barrier']:
        raw_right_x = np.median(right_points[:, 0])
        
        # Apply IIR filter
        if np.isnan(filtered_barrier_positions['right']):
            filtered_barrier_positions['right'] = raw_right_x
        else:
            alpha = params['iir_alpha_barrier']
            filtered_barrier_positions['right'] = alpha * raw_right_x + \
                                                  (1 - alpha) * filtered_barrier_positions['right']
    
    # --- Construct Final Dynamic X-Range ---
    dynamic_x_range = np.array(params['default_x_range'], dtype=float)

    if not np.isnan(filtered_barrier_positions['left']):
        dynamic_x_range[0] = filtered_barrier_positions['left'] + params['safety_margin']
    
    if not np.isnan(filtered_barrier_positions['right']):
        dynamic_x_range[1] = filtered_barrier_positions['right'] - params['safety_margin']
        
    return dynamic_x_range, filtered_barrier_positions