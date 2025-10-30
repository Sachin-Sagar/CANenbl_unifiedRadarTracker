# src/utils/slot_points_to_grid.py

import numpy as np

def slot_points_to_grid(cartesian_pos_data, grid_config):
    """
    Assigns radar points to a fixed-size grid.

    Args:
        cartesian_pos_data (np.ndarray): A 2xN NumPy array of Cartesian points.
        grid_config (dict): A dictionary with grid parameters:
            'X_RANGE': [min_x, max_x]
            'Y_RANGE': [min_y, max_y]
            'NUM_COLS': number of columns
            'NUM_ROWS': number of rows

    Returns:
        tuple: A tuple containing:
            - grid_map (list of lists of lists): A 2D list where each cell
              contains a list of point indices.
            - point_to_grid_idx (np.ndarray): An Nx2 array mapping each point
              index to its [row, col].
    """
    num_points = cartesian_pos_data.shape[1]
    
    grid_cell_width = (grid_config['X_RANGE'][1] - grid_config['X_RANGE'][0]) / grid_config['NUM_COLS']
    grid_cell_height = (grid_config['Y_RANGE'][1] - grid_config['Y_RANGE'][0]) / grid_config['NUM_ROWS']

    # Initialize a 2D list of lists to act as the grid map
    grid_map = [[[] for _ in range(grid_config['NUM_COLS'])] for _ in range(grid_config['NUM_ROWS'])]
    
    # Initialize the mapping array with zeros
    point_to_grid_idx = np.zeros((num_points, 2), dtype=int)

    for point_idx in range(num_points):
        point_x = cartesian_pos_data[0, point_idx]
        point_y = cartesian_pos_data[1, point_idx]

        is_in_x_range = grid_config['X_RANGE'][0] <= point_x < grid_config['X_RANGE'][1]
        is_in_y_range = grid_config['Y_RANGE'][0] <= point_y < grid_config['Y_RANGE'][1]

        if is_in_x_range and is_in_y_range:
            # Calculate column and row index (0-indexed in Python)
            col_idx = int((point_x - grid_config['X_RANGE'][0]) / grid_cell_width)
            row_idx = int((point_y - grid_config['Y_RANGE'][0]) / grid_cell_height)
            
            # Append the point's original index (0-indexed) to the correct cell
            grid_map[row_idx][col_idx].append(point_idx)
            
            # Store the mapping (using 1-based indexing to match MATLAB for now)
            # Note: We can change this to 0-based later if we prefer.
            point_to_grid_idx[point_idx, :] = [row_idx + 1, col_idx + 1]
            
    return grid_map, point_to_grid_idx