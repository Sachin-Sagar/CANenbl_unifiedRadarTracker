# src/algorithms/my_dbscan.py

import numpy as np

def my_dbscan(spatial_points, velocities, epsilon_pos, epsilon_vel, min_pts, grid_map, point_to_grid_idx):
    """
    Performs DBSCAN clustering using a pre-computed spatial grid and a custom
    distance metric that includes both position and velocity.
    """
    # ... (function docstring remains the same) ...

    if spatial_points is None or len(spatial_points) < min_pts:
        return np.array([], dtype=int)

    num_points = spatial_points.shape[0]
    clusters = np.zeros(num_points, dtype=int)
    cluster_id = 0

    for i in range(num_points):
        if clusters[i] != 0:
            continue

        neighbors = _find_neighbors_from_grid(i, spatial_points, velocities, epsilon_pos, epsilon_vel, grid_map, point_to_grid_idx)

        if len(neighbors) < min_pts:
            clusters[i] = -1 # Mark as Noise
        else:
            cluster_id += 1
            clusters[i] = cluster_id
            
            # --- MODIFICATION: Use a list and a head index for the queue ---
            queue = list(neighbors)
            head = 0
            
            while head < len(queue):
                current_point_idx = queue[head]
                head += 1
                
                # If point was marked as noise, it's now a border point.
                # If it's already in a cluster, do nothing.
                if clusters[current_point_idx] in [-1, 0]:
                    clusters[current_point_idx] = cluster_id
                    
                    current_neighbors = _find_neighbors_from_grid(current_point_idx, spatial_points, velocities, epsilon_pos, epsilon_vel, grid_map, point_to_grid_idx)
                    
                    if len(current_neighbors) >= min_pts:
                        # Add new neighbors to the end of the list
                        for n in current_neighbors:
                            if clusters[n] in [-1, 0]:
                                queue.append(n)
            # --- END OF MODIFICATION ---
                        
    clusters[clusters == -1] = 0
    return clusters


def _find_neighbors_from_grid(idx, spatial_points, velocities, epsilon_pos, epsilon_vel, grid_map, point_to_grid_idx):
    """Helper function to find neighbors using the pre-computed grid."""
    # ... (this function is unchanged) ...
    candidate_indices = []
    
    grid_location = point_to_grid_idx[idx, :]
    current_row = grid_location[0]
    current_col = grid_location[1]
    
    if current_row == 0 or current_col == 0:
        return []

    num_rows = len(grid_map)
    num_cols = len(grid_map[0])
    
    for row_offset in range(-1, 2):
        for col_offset in range(-1, 2):
            search_row = current_row + row_offset - 1
            search_col = current_col + col_offset - 1
            
            if 0 <= search_row < num_rows and 0 <= search_col < num_cols:
                candidate_indices.extend(grid_map[search_row][search_col])
    
    if not candidate_indices:
        return []
    candidate_indices = np.unique(candidate_indices)

    candidate_points = spatial_points[candidate_indices, :]
    candidate_velocities = velocities[candidate_indices]
    
    spatial_distances = np.sqrt(np.sum((candidate_points - spatial_points[idx, :])**2, axis=1))
    velocity_diffs = np.abs(candidate_velocities - velocities[idx])
    
    is_neighbor_mask = (spatial_distances <= epsilon_pos) & (velocity_diffs <= epsilon_vel)
    
    return candidate_indices[is_neighbor_mask]