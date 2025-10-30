# src/algorithms/detect_and_filter_reflections.py

import numpy as np

def detect_and_filter_reflections(grid_map, detected_cluster_info, dbscan_clusters_full, point_cloud, speed_similarity_threshold):
    """
    Identifies and filters clusters that are likely radar reflections.
    This version uses standard nested loops for pairing clusters.
    """
    # ... (function docstring remains the same) ...

    cluster_ids_to_remove = set()
    num_rows = len(grid_map)

    cluster_id_to_info_idx = {info['originalClusterID']: i for i, info in enumerate(detected_cluster_info)}

    for row in range(num_rows):
        point_indices_in_row = [idx for cell in grid_map[row] for idx in cell]
        if not point_indices_in_row:
            continue
        
        cluster_ids_in_row = np.unique(dbscan_clusters_full[point_indices_in_row])
        cluster_ids_in_row = [cid for cid in cluster_ids_in_row if cid > 0]

        if len(cluster_ids_in_row) < 2:
            continue

        # --- MODIFICATION: Use nested for loops to create pairs ---
        # This logic now directly mirrors the MATLAB implementation.
        for i in range(len(cluster_ids_in_row)):
            for j in range(i + 1, len(cluster_ids_in_row)):
                cid1 = cluster_ids_in_row[i]
                cid2 = cluster_ids_in_row[j]

                info_idx1 = cluster_id_to_info_idx.get(cid1)
                info_idx2 = cluster_id_to_info_idx.get(cid2)

                if info_idx1 is None or info_idx2 is None:
                    continue

                speed1 = detected_cluster_info[info_idx1]['radialSpeed']
                speed2 = detected_cluster_info[info_idx2]['radialSpeed']
                
                if abs(speed1 - speed2) < speed_similarity_threshold:
                    points_mask1 = (dbscan_clusters_full == cid1)
                    points_mask2 = (dbscan_clusters_full == cid2)
                    
                    snr1 = np.mean(point_cloud[4, points_mask1])
                    snr2 = np.mean(point_cloud[4, points_mask2])
                    
                    if snr1 < snr2:
                        cluster_ids_to_remove.add(cid1)
                    else:
                        cluster_ids_to_remove.add(cid2)
        # --- END OF MODIFICATION ---

    return list(cluster_ids_to_remove)