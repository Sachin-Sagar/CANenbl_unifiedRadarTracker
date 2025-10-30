# src/track_management/delete.py
import numpy as np
import logging
from ..utils.categorize_ttc import categorize_ttc
from ..utils.calculate_ellipse_radii import calculate_ellipse_radii
from ..utils.coordinate_transforms import cartesian_to_polar

def delete_unassigned_tracks(
    current_frame_idx, all_tracks, unassigned_track_indices, 
    lifecycle_params, ttc_params, params
):
    """
    Handles tracks that were not assigned a detection. It increments their miss 
    counter and, crucially, logs their predicted state to maintain a continuous history.
    """
    debug_mode = params.get('debug_mode', False)
    max_misses = lifecycle_params['maxMisses']
    confirmation_n = lifecycle_params['confirmation_N']
    max_trajectory_length = lifecycle_params['maxTrajectoryLength']
    collision_radius = ttc_params['collisionRadius']
    
    if debug_mode and unassigned_track_indices:
        logging.info(f'[DELETE] Processing {len(unassigned_track_indices)} unassigned tracks.')
        
    for track_idx in unassigned_track_indices:
        track = all_tracks[track_idx]
        
        if not track.get('isConfirmed'):
            if 'detectionHistory' not in track:
                track['detectionHistory'] = []
            track['detectionHistory'].append(False)
            if len(track['detectionHistory']) > confirmation_n:
                track['detectionHistory'].pop(0)
        
        track['misses'] = track.get('misses', 0) + 1
        track['age'] = track.get('age', 0) + 1

        # --- THIS IS THE FIX ---
        # For a missed track, the "corrected" state is the predicted state.
        predicted_state_comb = track['immState']['x']
        predicted_cov_comb = track['immState']['P']
        
        track['lastKnownPosition'] = predicted_state_comb[0:2].flatten()
        track['trajectory'].append(track['lastKnownPosition'])
        if len(track['trajectory']) > max_trajectory_length:
            track['trajectory'].pop(0)

        current_distance = np.linalg.norm(predicted_state_comb[0:2])
        if current_distance > 0:
            radial_vel = (predicted_state_comb[0] * predicted_state_comb[2] + 
                          predicted_state_comb[1] * predicted_state_comb[3]) / current_distance
            if radial_vel < 0 and current_distance > collision_radius:
                ttc = (current_distance - collision_radius) / abs(radial_vel)
            else:
                ttc = np.inf
        else:
            ttc = np.inf
        track['ttc'] = ttc
        track['ttcCategory'] = categorize_ttc(ttc, radial_vel if current_distance > 0 else 0, predicted_state_comb[0])

        prev_angle = track['historyLog'][-1]['orientationAngle'] if track['historyLog'] else None
        radii, angle = calculate_ellipse_radii(predicted_cov_comb[:2, :2], prev_angle)

        log_entry = {
            'frameIdx': current_frame_idx,
            'predictedPosition': predicted_state_comb[0:2].flatten(),
            'predictedVelocity': predicted_state_comb[2:4].flatten(),
            'correctedPosition': predicted_state_comb[0:2].flatten(),
            'correctedVelocity': predicted_state_comb[2:4].flatten(),
            'modelProbabilities': track['immState']['modelProbabilities'].flatten(),
            'measuredPosition': [np.nan, np.nan],
            'ttc': ttc,
            'ttcCategory': track['ttcCategory'],
            'isStationary': track.get('stationaryCount', 0) > 0,
            'covarianceP': predicted_cov_comb,
            'ellipseRadii': radii,
            'orientationAngle': angle
        }
        track['historyLog'].append(log_entry)
        # --- END OF FIX ---

        if track['misses'] > max_misses and not track.get('isLost'):
            track['isLost'] = True
            if debug_mode:
                log_frame = current_frame_idx
                if track.get('isConfirmed'):
                    logging.info(f'[DELETE] Confirmed track {track["id"]} marked as LOST at frame {log_frame}.')
                else:
                    logging.info(f'[DELETE] Tentative track {track["id"]} DELETED at frame {log_frame} (never confirmed).')

    return all_tracks