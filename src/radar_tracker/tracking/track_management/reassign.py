# src/track_management/reassign.py

import numpy as np
import logging
from ..utils.categorize_ttc import categorize_ttc

def reassign_lost_tracks(
    current_frame_idx, detected_centroids, detected_cluster_info, all_tracks,
    assigned_detections_flags, imm_params, reassignment_params, collision_radius,
    params
):
    """
    Reassigns lost tracks to unassigned detections by re-initializing them
    with a fresh IMM state.
    """
    debug_mode = params.get('debug_mode', False)
    lost_track_indices = [i for i, tr in enumerate(all_tracks) if tr.get('isLost')]
    unassigned_detections_indices = np.where(~assigned_detections_flags)[0]

    eligible_lost_track_indices = [
        idx for idx in lost_track_indices 
        if (current_frame_idx - all_tracks[idx].get('lastSeenFrame', -1)) <= reassignment_params['maxFramesLostForReassignment']
    ]

    if not unassigned_detections_indices.size or not eligible_lost_track_indices:
        return all_tracks, assigned_detections_flags

    num_dets = len(unassigned_detections_indices)
    num_tracks = len(eligible_lost_track_indices)
    cost_matrix = np.full((num_dets, num_tracks), np.inf)

    for i, det_idx in enumerate(unassigned_detections_indices):
        det_pos = detected_centroids[det_idx]
        for j, track_idx in enumerate(eligible_lost_track_indices):
            track = all_tracks[track_idx]
            dist = np.linalg.norm(det_pos - track['lastKnownPosition'])
            if dist <= reassignment_params['reassignmentDistanceThreshold']:
                cost_matrix[i, j] = dist

    reassignments = []
    temp_cost_matrix = cost_matrix.copy()
    while np.any(np.isfinite(temp_cost_matrix)):
        min_val = np.min(temp_cost_matrix)
        if np.isinf(min_val): break
        det_list_idx, track_list_idx = np.unravel_index(np.argmin(temp_cost_matrix), temp_cost_matrix.shape)
        original_detection_idx = unassigned_detections_indices[det_list_idx]
        original_lost_track_idx = eligible_lost_track_indices[track_list_idx]
        reassignments.append((original_lost_track_idx, original_detection_idx))
        temp_cost_matrix[det_list_idx, :] = np.inf
        temp_cost_matrix[:, track_list_idx] = np.inf
    
    if debug_mode and reassignments:
        logging.info(f'[REASSIGN] Made {len(reassignments)} reassignments.')

    for track_idx, detection_idx in reassignments:
        track = all_tracks[track_idx]
        det_info = detected_cluster_info[detection_idx]
        det_pos = detected_centroids[detection_idx]
        
        if debug_mode:
            logging.info(f'[REASSIGN] Track {track["id"]} REASSIGNED at frame {current_frame_idx}.')

        reinit_state_7d = np.array([det_pos[0], det_pos[1], det_info['vx'], det_info['vy'], 0, 0, 0]).reshape(7, 1)
        track['immState']['modelProbabilities'] = imm_params['initialModelProbabilities'].copy()
        for model in track['immState']['models']:
            model['x'] = reinit_state_7d.copy()
            model['P'] = imm_params['P_init'].copy()
        track['immState']['x'] = reinit_state_7d.copy()
        track['immState']['P'] = imm_params['P_init'].copy()

        track['isLost'] = False
        track['misses'] = 0
        track['hits'] += 1 
        track['age'] += 1
        track['lastSeenFrame'] = current_frame_idx
        track['lastKnownPosition'] = det_pos
        track['trajectory'] = [det_pos]

        r = np.linalg.norm(det_pos)
        v_rel_rad = (reinit_state_7d[0]*reinit_state_7d[2] + reinit_state_7d[1]*reinit_state_7d[3]) / r if r > 0 else 0
        ttc = (r - collision_radius) / abs(v_rel_rad) if v_rel_rad < 0 and r > collision_radius else np.inf
        track['ttc'] = ttc
        track['ttcCategory'] = categorize_ttc(ttc, v_rel_rad, det_pos[0])
        
        assigned_detections_flags[detection_idx] = True

    return all_tracks, assigned_detections_flags