# src/track_management/update_tentative.py

import numpy as np
import logging
from copy import deepcopy
from ..filters.imm_filter import imm_correct
from ..utils.categorize_ttc import categorize_ttc
from ..utils.calculate_ellipse_radii import calculate_ellipse_radii

def update_tentative_tracks(
    current_frame_idx, detected_centroids, detected_cluster_info, all_tracks,
    tentative_track_indices, assigned_detections_flags, kf_measurement_noise,
    assignment_threshold, lifecycle_params, ttc_params, params
):
    """
    Updates tentative tracks using greedy assignment, M-out-of-N confirmation logic,
    and now performs detailed history logging for each update.
    """
    debug_mode = params.get('debug_mode', False)
    confirmation_m = lifecycle_params['confirmation_M']
    confirmation_n = lifecycle_params['confirmation_N']
    max_trajectory_length = lifecycle_params['maxTrajectoryLength']
    collision_radius = ttc_params['collisionRadius']
    
    num_tentative_tracks = len(tentative_track_indices)
    unassigned_detections_indices = np.where(~assigned_detections_flags)[0]
    assigned_tentative_tracks_flags = np.zeros(num_tentative_tracks, dtype=bool)

    if num_tentative_tracks == 0 or not unassigned_detections_indices.size:
        if debug_mode and num_tentative_tracks > 0:
            logging.info('[TENTATIVE] Exiting: No available detections for tentative tracks.')
        return all_tracks, assigned_detections_flags, assigned_tentative_tracks_flags

    # --- Cost Matrix and Greedy Assignment (Logic Unchanged) ---
    num_dets = len(unassigned_detections_indices)
    cost_matrix = np.full((num_dets, num_tentative_tracks), np.inf)

    for j, track_idx in enumerate(tentative_track_indices):
        track = all_tracks[track_idx]
        x_pred, P_pred = track['immState']['x'], track['immState']['P']
        px, py, vx, vy = x_pred[0:4].flatten()
        r = np.linalg.norm([px, py])
        if r < 1e-6: continue
        
        h_x = np.array([r, np.arctan2(px, py), (px*vx + py*vy)/r]).reshape(3,1)
        r_sq, r_cub = r**2, r**3
        H = np.zeros((3, 7))
        H[0, 0]=px/r; H[0, 1]=py/r
        H[1, 0]=py/r_sq; H[1, 1]=-px/r_sq
        H[2, 0]=(vx/r)-(px*(px*vx+py*vy))/r_cub; H[2, 1]=(vy/r)-(py*(px*vx+py*vy))/r_cub
        H[2, 2]=px/r; H[2, 3]=py/r
        
        S = H @ P_pred @ H.T + kf_measurement_noise
        
        for i, det_idx in enumerate(unassigned_detections_indices):
            det_pos = detected_centroids[det_idx]
            z = np.array([np.linalg.norm(det_pos), np.arctan2(det_pos[0], det_pos[1]), 
                          detected_cluster_info[det_idx]['radialSpeed']]).reshape(3, 1)
            y = z - h_x
            y[1] = (y[1] + np.pi) % (2 * np.pi) - np.pi
            try:
                cost = y.T @ np.linalg.inv(S) @ y
                if cost <= assignment_threshold**2:
                    cost_matrix[i, j] = cost
            except np.linalg.LinAlgError:
                continue
    
    assignments = []
    temp_cost_matrix = cost_matrix.copy()
    while np.any(np.isfinite(temp_cost_matrix)):
        min_val = np.min(temp_cost_matrix)
        if np.isinf(min_val): break
        det_list_idx, track_list_idx = np.unravel_index(np.argmin(temp_cost_matrix), temp_cost_matrix.shape)
        original_detection_idx = unassigned_detections_indices[det_list_idx]
        original_track_idx = tentative_track_indices[track_list_idx]
        assignments.append((original_track_idx, original_detection_idx, track_list_idx))
        temp_cost_matrix[det_list_idx, :] = np.inf
        temp_cost_matrix[:, track_list_idx] = np.inf

    if debug_mode and assignments:
        logging.info(f'[TENTATIVE] Found {len(assignments)} valid assignments.')
    
    # --- Update Assigned Tracks ---
    for track_idx, detection_idx, track_list_idx in assignments:
        track = all_tracks[track_idx]
        det_pos = detected_centroids[detection_idx]
        det_info = detected_cluster_info[detection_idx]
        assigned_tentative_tracks_flags[track_list_idx] = True
        assigned_detections_flags[detection_idx] = True

        predicted_state_for_log = deepcopy(track['immState'])

        measurement_z = np.array([np.linalg.norm(det_pos), np.arctan2(det_pos[0], det_pos[1]), det_info['radialSpeed']]).reshape(3, 1)
        track['immState'] = imm_correct(track['immState'], measurement_z, kf_measurement_noise)
        
        track['detectionHistory'].append(True)
        if len(track['detectionHistory']) > confirmation_n:
            track['detectionHistory'].pop(0)
        if not track['isConfirmed'] and sum(track['detectionHistory']) >= confirmation_m:
            track['isConfirmed'] = True
            if debug_mode:
                logging.info(f'[TENTATIVE] Track {track["id"]} CONFIRMED at frame {current_frame_idx} (M/N Hit Ratio: {sum(track["detectionHistory"])}/{len(track["detectionHistory"])}).')
        
        track['hits'] += 1
        track['misses'] = 0
        track['age'] += 1
        track['lastSeenFrame'] = current_frame_idx
        
        # --- THIS IS THE FIX ---
        # A cluster is stationary if it is NOT an "outlier cluster"
        detection_is_stationary = not det_info.get('isOutlierCluster', True)
        if detection_is_stationary:
            track['stationaryCount'] += 1
        else:
            track['stationaryCount'] -= 1
        # --- END OF FIX ---

        corrected_state_comb = track['immState']['x']
        corrected_cov_comb = track['immState']['P']
        
        track['lastKnownPosition'] = corrected_state_comb[0:2].flatten()
        track['trajectory'].append(track['lastKnownPosition'])
        if len(track['trajectory']) > max_trajectory_length:
            track['trajectory'].pop(0)

        current_distance = np.linalg.norm(corrected_state_comb[0:2])
        if current_distance > 0:
            radial_vel = (corrected_state_comb[0] * corrected_state_comb[2] + 
                          corrected_state_comb[1] * corrected_state_comb[3]) / current_distance
            ttc = (current_distance - collision_radius) / abs(radial_vel) if radial_vel < 0 and current_distance > collision_radius else np.inf
        else:
            ttc = np.inf
        track['ttc'] = ttc
        track['ttcCategory'] = categorize_ttc(ttc, radial_vel if current_distance > 0 else 0, corrected_state_comb[0])
        
        prev_angle = track['historyLog'][-1]['orientationAngle'] if track['historyLog'] else None
        radii, angle = calculate_ellipse_radii(corrected_cov_comb[:2, :2], prev_angle)

        log_entry = {
            'frameIdx': current_frame_idx,
            'predictedPosition': predicted_state_for_log['x'][0:2].flatten(),
            'predictedVelocity': predicted_state_for_log['x'][2:4].flatten(),
            'correctedPosition': corrected_state_comb[0:2].flatten(),
            'correctedVelocity': corrected_state_comb[2:4].flatten(),
            'modelProbabilities': track['immState']['modelProbabilities'].flatten(),
            'measuredPosition': det_pos.flatten(),
            'ttc': ttc,
            'ttcCategory': track['ttcCategory'],
            'isStationary': track.get('stationaryCount', 0) > 0, # This will now be correct
            'covarianceP': corrected_cov_comb,
            'ellipseRadii': radii,
            'orientationAngle': angle
        }
        track['historyLog'].append(log_entry)

    if debug_mode and assignments:
        logging.info(f'[TENTATIVE] Updated {len(assignments)} tentative tracks.')
        
    return all_tracks, assigned_detections_flags, assigned_tentative_tracks_flags