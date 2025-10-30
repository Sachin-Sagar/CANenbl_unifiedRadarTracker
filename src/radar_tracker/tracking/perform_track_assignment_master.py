import numpy as np
import logging
from copy import deepcopy

# MODIFICATION: Changed all imports to use a single dot (.) for correct relative path
from .filters.imm_filter import imm_predict, imm_correct
from .track_management.jpda_assignment import jpda_assignment
from .track_management.update_tentative import update_tentative_tracks
from .track_management.reassign import reassign_lost_tracks
from .track_management.assign import assign_new_tracks
from .track_management.delete import delete_unassigned_tracks
from .utils.categorize_ttc import categorize_ttc
from .utils.calculate_ellipse_radii import calculate_ellipse_radii


def perform_track_assignment_master(
    current_frame_idx, detected_centroids, detected_cluster_info, all_tracks, 
    next_track_id, delta_t, ego_yaw_rate, params
):
    """
    The main orchestrator for the track management process for a single frame.
    """
    debug_mode = params.get('debug_mode', False)
    num_detections = detected_centroids.shape[0] if detected_centroids is not None else 0
    assigned_detections_flags = np.zeros(num_detections, dtype=bool)

    if debug_mode:
        logging.info(f'\n\n--- MASTER FRAME {current_frame_idx} ---')

    # --- 1. Separate tracks by state ---
    confirmed_indices = [i for i, t in enumerate(all_tracks) if t.get('isConfirmed') and not t.get('isLost')]
    tentative_indices = [i for i, t in enumerate(all_tracks) if not t.get('isConfirmed') and not t.get('isLost')]
    lost_indices = [i for i, t in enumerate(all_tracks) if t.get('isLost')]

    if debug_mode:
        logging.info(f'[MASTER] Start: {num_detections} detections, {len(confirmed_indices)} confirmed, {len(tentative_indices)} tentative, {len(lost_indices)} lost tracks.')

    # --- 2. Predict states for all active tracks ---
    active_indices = confirmed_indices + tentative_indices
    predicted_states = {} # Store pre-update states for logging
    if active_indices:
        if debug_mode:
            logging.info(f'\n[MASTER] -> Predicting states for {len(active_indices)} active tracks using IMM filter...')
        for track_idx in active_indices:
            # Store a deepcopy for logging later
            predicted_states[track_idx] = deepcopy(all_tracks[track_idx]['immState'])
            all_tracks[track_idx]['immState'] = imm_predict(
                all_tracks[track_idx]['immState'], params['imm_params'], delta_t, ego_yaw_rate
            )

    # --- 3. Maintain Confirmed Tracks (JPDA) ---
    assigned_confirmed_flags = np.zeros(len(confirmed_indices), dtype=bool)
    if confirmed_indices:
        if debug_mode:
            logging.info(f'\n[MASTER] -> Calling MAINTAIN for {len(confirmed_indices)} confirmed tracks...')
        
        # --- THIS IS THE FIX ---
        all_tracks, miss_flags, validation_matrix, beta, most_likely_meas_indices = jpda_assignment(
            all_tracks, confirmed_indices, detected_centroids, detected_cluster_info,
            params['kf_measurement_noise'], params['jpda_params']['PD'], 
            params['jpda_params']['lambda_c'], params['jpda_params']['gating_chi2'],
            params['gating_params']['positionGatingThreshold'], params
        )
        # --- END OF FIX ---

        assigned_confirmed_flags = ~miss_flags
        
        if num_detections > 0 and validation_matrix.size > 0:
            used_detections_mask = np.any(validation_matrix[:, ~miss_flags], axis=1) if np.any(~miss_flags) else np.zeros(num_detections, dtype=bool)
            assigned_detections_flags[used_detections_mask] = True

        for i, track_idx in enumerate(confirmed_indices):
            if not miss_flags[i]: # Only update assigned tracks
                track = all_tracks[track_idx]
                track['age'] += 1
                track['lastSeenFrame'] = current_frame_idx
                track['hits'] += 1
                track['misses'] = 0
                
                corrected_state_comb = track['immState']['x']
                track['lastKnownPosition'] = corrected_state_comb[0:2].flatten()
                track['trajectory'].append(track['lastKnownPosition'])
                if len(track['trajectory']) > params['lifecycle_params']['maxTrajectoryLength']:
                    track['trajectory'].pop(0)

                predicted_state_for_log = predicted_states[track_idx]
                current_distance = np.linalg.norm(corrected_state_comb[0:2])
                if current_distance > 0:
                    radial_vel = (corrected_state_comb[0] * corrected_state_comb[2] + 
                                  corrected_state_comb[1] * corrected_state_comb[3]) / current_distance
                    ttc = (current_distance - params['ttc_params']['collisionRadius']) / abs(radial_vel) if radial_vel < 0 else np.inf
                else:
                    ttc = np.inf

                prev_angle = track['historyLog'][-1]['orientationAngle'] if track['historyLog'] else None
                radii, angle = calculate_ellipse_radii(track['immState']['P'][:2, :2], prev_angle)
                
                # --- THIS IS THE FIX ---
                # Get the measured position from the most likely detection
                meas_idx = most_likely_meas_indices[i]
                measured_pos = detected_centroids[meas_idx].flatten() if meas_idx != -1 else [np.nan, np.nan]
                # --- END OF FIX ---

                log_entry = {
                    'frameIdx': current_frame_idx,
                    'predictedPosition': predicted_state_for_log['x'][0:2].flatten(),
                    'correctedPosition': corrected_state_comb[0:2].flatten(),
                    'modelProbabilities': track['immState']['modelProbabilities'].flatten(),
                    'ttc': ttc, 'ttcCategory': categorize_ttc(ttc, radial_vel if current_distance > 0 else 0, corrected_state_comb[0]),
                    'isStationary': track.get('stationaryCount', 0) > 0,
                    'covarianceP': track['immState']['P'], 'ellipseRadii': radii, 'orientationAngle': angle,
                    'measuredPosition': measured_pos # Add the measured position to the log
                }
                track['historyLog'].append(log_entry)

    # --- 4. Update Tentative Tracks ---
    assigned_tentative_flags = np.zeros(len(tentative_indices), dtype=bool)
    if tentative_indices:
        if debug_mode:
            logging.info(f'\n[MASTER] -> Calling UPDATE_TENTATIVE for {len(tentative_indices)} tentative tracks...')
        all_tracks, assigned_detections_flags, assigned_tentative_flags = update_tentative_tracks(
            current_frame_idx, detected_centroids, detected_cluster_info, all_tracks,
            tentative_indices, assigned_detections_flags, params['kf_measurement_noise'],
            params['assignment_params']['assignmentThreshold'],
            params['lifecycle_params'], params['ttc_params'], params
        )

    # --- 5. Reassign Lost Tracks ---
    if lost_indices:
        if debug_mode:
            logging.info('\n[MASTER] -> Calling REASSIGN for lost tracks...')
        all_tracks, assigned_detections_flags = reassign_lost_tracks(
            current_frame_idx, detected_centroids, detected_cluster_info, all_tracks,
            assigned_detections_flags, params['imm_params'],
            params['reassignment_params'], params['ttc_params']['collisionRadius'],
            params
        )

    # --- 6. Assign New Tracks ---
    if not np.all(assigned_detections_flags):
        if debug_mode:
            logging.info('\n[MASTER] -> Calling ASSIGN for new tracks...')
        all_tracks, next_track_id, assigned_detections_flags = assign_new_tracks(
            current_frame_idx, detected_centroids, detected_cluster_info, all_tracks,
            assigned_detections_flags, next_track_id, params['imm_params'], 
            params['gating_params'], params['ttc_params']['collisionRadius'],
            params['lifecycle_params']['trackStationary'], params
        )

    # --- 7. Handle Missed Tracks ---
    unassigned_confirmed_indices = [idx for i, idx in enumerate(confirmed_indices) if not assigned_confirmed_flags[i]]
    unassigned_tentative_indices = [idx for i, idx in enumerate(tentative_indices) if not assigned_tentative_flags[i]]
    all_unassigned_indices = unassigned_confirmed_indices + unassigned_tentative_indices
    
    if all_unassigned_indices:
        if debug_mode:
            logging.info(f'\n[MASTER] -> Calling DELETE for {len(all_unassigned_indices)} unassigned tracks...')
        all_tracks = delete_unassigned_tracks(
            current_frame_idx, all_tracks, all_unassigned_indices, 
            params['lifecycle_params'], params['ttc_params'], params
        )

    # --- 8. Final Count ---
    num_confirmed_tracks = sum(1 for t in all_tracks if t.get('isConfirmed') and not t.get('isLost'))
    if debug_mode:
        logging.info(f'\n[MASTER] End: Final confirmed tracks: {num_confirmed_tracks}.')
        logging.info(f'--- END MASTER FRAME {current_frame_idx} ---')

    return all_tracks, next_track_id, num_confirmed_tracks, assigned_detections_flags