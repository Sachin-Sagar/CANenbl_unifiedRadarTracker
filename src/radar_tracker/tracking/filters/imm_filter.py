# src/filters/imm_filter.py

import numpy as np
from .imm_models import cv_predict, ct_predict, ca_predict

def imm_predict(imm_state, imm_params, delta_t, ego_yaw_rate):
    """
    Performs the interaction and prediction steps of the IMM filter.

    Args:
        imm_state (dict): The IMM state from the previous time step.
        imm_params (dict): Struct containing IMM parameters.
        delta_t (float): The time step in seconds.
        ego_yaw_rate (float): The ego-vehicle's yaw rate in rad/s.

    Returns:
        dict: The IMM state containing the predicted states for each model.
    """
    N = 3  # Number of models
    p_ij = imm_params['modelTransitionMatrix']
    mu_prev = imm_state['modelProbabilities']
    
    imm_state_pred = imm_state.copy()

    # --- 1. Interaction / Mixing Step ---
    # Calculate predicted model probabilities (c_bar)
    c_bar = p_ij.T @ mu_prev
    
    # Calculate mixing probabilities (mu_ij)
    mu_ij = (p_ij * mu_prev) / c_bar.T

    # --- THIS IS THE FIX ---
    # Calculate the mixed state and covariance for each model.
    # We explicitly initialize with the correct shape (7, 1) to prevent
    # propagation of shape errors from a previous frame.
    x_mixed = [np.zeros((7, 1)) for _ in range(N)]
    P_mixed = [np.zeros((7, 7)) for _ in range(N)]
    # --- END OF FIX ---

    for j in range(N):
        # This loop correctly populates the (7,1) x_mixed arrays
        for i in range(N):
            # Ensure the input state is reshaped to (7,1) before use
            state_to_mix = imm_state['models'][i]['x'].reshape(7, 1)
            x_mixed[j] += state_to_mix * mu_ij[i, j]
        
        for i in range(N):
            state_to_mix = imm_state['models'][i]['x'].reshape(7, 1)
            diff = state_to_mix - x_mixed[j]
            P_mixed[j] += mu_ij[i, j] * (imm_state['models'][i]['P'] + diff @ diff.T)

    # --- 2. Model-Specific Prediction Step ---
    # Predict using CV, CT, and CA models
    x_pred_cv, P_pred_cv = cv_predict(x_mixed[0], P_mixed[0], imm_params['Q_cv'], delta_t, ego_yaw_rate)
    x_pred_ct, P_pred_ct = ct_predict(x_mixed[1], P_mixed[1], imm_params['Q_ct'], delta_t)
    x_pred_ca, P_pred_ca = ca_predict(x_mixed[2], P_mixed[2], imm_params['Q_ca'], delta_t)

    imm_state_pred['models'] = [
        {'x': x_pred_cv, 'P': P_pred_cv},
        {'x': x_pred_ct, 'P': P_pred_ct},
        {'x': x_pred_ca, 'P': P_pred_ca}
    ]
    imm_state_pred['modelProbabilities'] = c_bar

    # --- 3. Fuse Predicted States and Covariances (for logging/gating) ---
    # --- THIS IS THE FIX (PART 2) ---
    # Enforce the correct shape for the fused state and covariance as well.
    x_fused = np.zeros((7, 1))
    P_fused = np.zeros((7, 7))
    # --- END OF FIX (PART 2) ---

    for j in range(N):
        x_fused += c_bar[j] * imm_state_pred['models'][j]['x']

    for j in range(N):
        diff = imm_state_pred['models'][j]['x'] - x_fused
        P_fused += c_bar[j] * (imm_state_pred['models'][j]['P'] + diff @ diff.T)

    imm_state_pred['x'] = x_fused
    imm_state_pred['P'] = P_fused
    
    return imm_state_pred


def imm_correct(imm_state_pred, z_polar, R_polar):
    """
    Performs the correction/update step of the IMM filter.
    """
    N = 3
    imm_state_corr = imm_state_pred.copy()
    
    likelihoods = np.zeros(N)
    
    # --- 1. Calculate Measurement Likelihood for each Model ---
    for j in range(N):
        x_pred_j = imm_state_pred['models'][j]['x']
        P_pred_j = imm_state_pred['models'][j]['P']
        
        px, py, vx, vy, _, _, _ = x_pred_j.flatten()
        
        r = np.sqrt(px**2 + py**2)
        
        if r < 1e-6:
            h_x = np.zeros((3, 1))
            H = np.zeros((3, 7))
        else:
            h_x = np.array([r, np.arctan2(px, py), (px*vx + py*vy)/r]).reshape(3, 1)
            
            r_sq, r_cub = r**2, r**3
            H = np.zeros((3, 7))
            H[0, 0] = px/r; H[0, 1] = py/r
            H[1, 0] = py/r_sq; H[1, 1] = -px/r_sq
            H[2, 0] = (vx/r) - (px*(px*vx + py*vy))/r_cub
            H[2, 1] = (vy/r) - (py*(px*vx + py*vy))/r_cub
            H[2, 2] = px/r; H[2, 3] = py/r

        y_j = z_polar - h_x
        y_j[1] = (y_j[1] + np.pi) % (2 * np.pi) - np.pi # Wrap angle to [-pi, pi]
        
        S_j = H @ P_pred_j @ H.T + R_polar
        S_j_inv = np.linalg.inv(S_j)
        
        mahalanobis_sq = y_j.T @ S_j_inv @ y_j
        likelihoods[j] = np.exp(-0.5 * mahalanobis_sq) / np.sqrt(np.linalg.det(2 * np.pi * S_j))
        
        # --- 3. Model-Specific State Correction (done inside loop) ---
        K_j = P_pred_j @ H.T @ S_j_inv
        imm_state_corr['models'][j]['x'] = x_pred_j + K_j @ y_j
        imm_state_corr['models'][j]['P'] = (np.eye(7) - K_j @ H) @ P_pred_j

    # --- 2. Update Model Probabilities ---
    mu_pred = imm_state_pred['modelProbabilities']
    mu_new = likelihoods * mu_pred.flatten()
    c_normal = np.sum(mu_new)
    mu_new = mu_new / c_normal if c_normal > 1e-9 else mu_pred
    imm_state_corr['modelProbabilities'] = mu_new.reshape(-1, 1)

    # --- 4. State and Covariance Fusion ---
    x_fused = np.zeros_like(imm_state_corr['models'][0]['x'])
    for j in range(N):
        x_fused += mu_new[j] * imm_state_corr['models'][j]['x']

    P_fused = np.zeros_like(imm_state_corr['models'][0]['P'])
    for j in range(N):
        diff = imm_state_corr['models'][j]['x'] - x_fused
        P_fused += mu_new[j] * (imm_state_corr['models'][j]['P'] + diff @ diff.T)

    imm_state_corr['x'] = x_fused
    imm_state_corr['P'] = P_fused

    return imm_state_corr