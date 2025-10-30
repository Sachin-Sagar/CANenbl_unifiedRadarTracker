# src/track_management/assign.py

import numpy as np
import logging
from ..utils.categorize_ttc import categorize_ttc
from ..utils.calculate_ellipse_radii import calculate_ellipse_radii

def assign_new_tracks(
    current_frame_idx, detected_centroids, detected_cluster_info, all_tracks,
    assigned_detections_flags, next_track_id, imm_params, gating_params,
    collision_radius, track_stationary, params
):
    """
    Creates new tracks from unassigned detections using the IMM filter structure.
    """
    debug_mode = params.get('debug_mode', False)
    unassigned_detections = np.where(~assigned_detections_flags)[0]

    if debug_mode and unassigned_detections.size > 0:
        logging.info(f'[ASSIGN] Checking {unassigned_detections.size} unassigned detections for new tracks.')

    for detection_idx in unassigned_detections:
        det_info = detected_cluster_info[detection_idx]
        det_x_rel, det_y_rel = detected_centroids[detection_idx]
        det_radius_rel = np.sqrt(det_x_rel**2 + det_y_rel**2)
        angle_det_rel_deg = np.rad2deg(np.arctan2(det_x_rel, det_y_rel))

        is_reliable = (gating_params['minAngle'] <= angle_det_rel_deg <= gating_params['maxAngle']) and \
                      (det_radius_rel < gating_params['maxRadius'])
        is_not_too_fast = abs(det_info['radialSpeed']) <= gating_params['maxRadialSpeedThreshold']
        
        # --- THIS IS THE CORRECTED LOGIC ---
        # A track should be created if the cluster is MOVING,
        # OR if it is a special stationary cluster that has been flagged as being "in the box".
        is_moving_cluster = det_info.get('isOutlierCluster', False) # True if moving
        is_stationary_target_in_box = det_info.get('isStationary_inBox', False)
        
        can_be_tracked = is_moving_cluster or is_stationary_target_in_box
        # --- END OF CORRECTION ---
        
        if is_reliable and is_not_too_fast and can_be_tracked:
            if debug_mode:
                logging.info(f'  -> ACCEPTED: Creating new track {next_track_id} from detection {detection_idx}.')
            
            # This flag is used for history logging; a cluster is stationary if it's not moving.
            is_stationary_cluster_for_log = not is_moving_cluster

            initial_state_7d = np.array([det_x_rel, det_y_rel, det_info['vx'], det_info['vy'], 0, 0, 0]).reshape(7, 1)
            initial_imm_state = {
                'modelProbabilities': imm_params['initialModelProbabilities'].copy(),
                'models': [{'x': initial_state_7d.copy(), 'P': imm_params['P_init'].copy()} for _ in range(3)],
                'x': initial_state_7d.copy(),
                'P': imm_params['P_init'].copy()
            }
            r, v_rel_rad = det_radius_rel, (initial_state_7d[0]*initial_state_7d[2] + initial_state_7d[1]*initial_state_7d[3]) / det_radius_rel if det_radius_rel > 0 else 0
            ttc = (r - collision_radius) / abs(v_rel_rad) if v_rel_rad < 0 and r > collision_radius else np.inf
            ttc_category = categorize_ttc(ttc, v_rel_rad, det_x_rel)
            radii, angle = calculate_ellipse_radii(initial_imm_state['P'][:2, :2])
            
            new_track = {
                'id': next_track_id, 'immState': initial_imm_state,
                'lastKnownPosition': initial_state_7d[0:2].flatten(),
                'age': 1, 'hits': 1, 'misses': 0,
                'trajectory': [initial_state_7d[0:2].flatten()],
                'isLost': False, 'isConfirmed': False,
                'ttc': ttc, 'ttcCategory': ttc_category,
                'detectionHistory': [True], 'lastSeenFrame': current_frame_idx,
                'stationaryCount': 1 if is_stationary_cluster_for_log else -1,
                'historyLog': [{'frameIdx': current_frame_idx, 'predictedPosition': initial_state_7d[0:2],
                                'correctedPosition': initial_state_7d[0:2], 'modelProbabilities': initial_imm_state['modelProbabilities'],
                                'covarianceP': initial_imm_state['P'], 'ellipseRadii': radii, 'orientationAngle': angle,
                                'ttc': ttc, 'ttcCategory': ttc_category, 'isStationary': is_stationary_cluster_for_log}]
            }
            
            all_tracks.append(new_track)
            assigned_detections_flags[detection_idx] = True
            next_track_id += 1
            
    return all_tracks, next_track_id, assigned_detections_flags