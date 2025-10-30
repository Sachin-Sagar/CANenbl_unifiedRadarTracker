# src/algorithms/find_jpda_hypotheses.py

import numpy as np
import logging

def find_jpda_hypotheses(validation_matrix, params):
    """
    Recursively generates all valid joint association hypotheses from a
    given validation matrix.
    """
    debug_mode = params.get('debug_mode', False)
    debug_mode1 = params.get('debug_mode1', False)

    num_measurements, num_tracks = validation_matrix.shape
    hypotheses = []

    if debug_mode:
        logging.info(f'[HYP-GEN-DEBUG] Starting hypothesis generation for {num_tracks} tracks and {num_measurements} measurements.')

    def _generate(track_idx, current_hypothesis, used_measurements_mask):
        """
        Nested recursive function to generate hypotheses.
        """
        if track_idx >= num_tracks:
            hypotheses.append(list(current_hypothesis))
            if debug_mode:
                logging.info(f'[HYP-GEN-DEBUG] -> Found complete hypothesis #{len(hypotheses)}: {str(current_hypothesis)}')
            return

        if debug_mode1:
            logging.info(f'[HYP-GEN-DEBUG]   Processing T{track_idx}. Current assignment: {str(current_hypothesis[:track_idx])}')

        if debug_mode1:
            logging.info(f'[HYP-GEN-DEBUG]     Trying T{track_idx} -> M0 (Miss)')
        _generate(track_idx + 1, current_hypothesis, used_measurements_mask)

        for meas_idx in range(num_measurements):
            if validation_matrix[meas_idx, track_idx] and not used_measurements_mask[meas_idx]:
                if debug_mode1:
                    logging.info(f'[HYP-GEN-DEBUG]     Trying T{track_idx} -> M{meas_idx + 1}')
                
                new_hypothesis = list(current_hypothesis)
                new_hypothesis[track_idx] = meas_idx + 1 
                
                new_used_mask = list(used_measurements_mask)
                new_used_mask[meas_idx] = True
                
                _generate(track_idx + 1, new_hypothesis, new_used_mask)

    initial_hypothesis = [0] * num_tracks
    initial_used_mask = [False] * num_measurements
    _generate(0, initial_hypothesis, initial_used_mask)

    return hypotheses