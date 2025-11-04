# src/algorithms/my_dbscan.py

import numpy as np
import logging
import config

def my_dbscan(spatial_points, velocities, epsilon_pos, epsilon_vel, min_pts, grid_map, point_to_grid_idx):
    """
    Performs DBSCAN clustering using a pre-computed spatial grid and a custom
    distance metric that includes both position and velocity.
    """
    # ... (function docstring remains the same) ...

    if spatial_points is None or len(spatial_points) < min_pts:
        if config.COMPONENT_DEBUG_FLAGS.get('dbscan'):
            logging.debug(f"[DBSCAN] Not enough points ({len(spatial_points) if spatial_points is not None else 0}) for min_pts ({min_pts}). Returning empty clusters.")
        return np.array([], dtype=int)

    num_points = spatial_points.shape[0]
    clusters = np.zeros(num_points, dtype=int)
    cluster_id = 0

    if config.COMPONENT_DEBUG_FLAGS.get('dbscan'):
        logging.debug(f"[DBSCAN] Starting with epsilon_pos={epsilon_pos}, epsilon_vel={epsilon_vel}, min_pts={min_pts}, num_points={num_points}")

    for i in range(num_points):
        if clusters[i] != 0:
            continue

        neighbors = _find_neighbors_from_grid(i, spatial_points, velocities, epsilon_pos, epsilon_vel, grid_map, point_to_grid_idx)

        if len(neighbors) < min_pts:
            clusters[i] = -1 # Mark as Noise
            if config.COMPONENT_DEBUG_FLAGS.get('dbscan'):
                logging.debug(f"[DBSCAN] Point {i} marked as noise (neighbors: {len(neighbors)} < {min_pts})")
        else:
            cluster_id += 1
            clusters[i] = cluster_id
            if config.COMPONENT_DEBUG_FLAGS.get('dbscan'):
                logging.debug(f"[DBSCAN] New cluster {cluster_id} found with core point {i} (initial neighbors: {len(neighbors)})")
            
            # --- MODIFICATION: Use a list and a head index for the queue ---
            queue = list(neighbors)
            head = 0
            
            while head < len(queue):
                current_point_idx = queue[head]
                head += 1
                
                # If point was marked as noise, it's now a border point.
                # If it's already in a cluster, do nothing.
                if clusters[current_point_idx] in [-1, 0]:
                    if config.COMPONENT_DEBUG_FLAGS.get('dbscan'):
                        logging.debug(f"[DBSCAN] Adding point {current_point_idx} to cluster {cluster_id}")
                    clusters[current_point_idx] = cluster_id
                    
                    current_neighbors = _find_neighbors_from_grid(current_point_idx, spatial_points, velocities, epsilon_pos, epsilon_vel, grid_map, point_to_grid_idx)
                    
                    if len(current_neighbors) >= min_pts:
                        # Add new neighbors to the end of the list
                        for n in current_neighbors:
                            if clusters[n] in [-1, 0]:
                                queue.append(n)
            # --- END OF MODIFICATION ---
                        
    clusters[clusters == -1] = 0
    if config.COMPONENT_DEBUG_FLAGS.get('dbscan'):
        logging.debug(f"[DBSCAN] Finished. Total clusters found: {cluster_id}. Cluster assignments: {clusters}")
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