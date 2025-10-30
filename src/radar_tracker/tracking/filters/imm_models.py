# src/filters/imm_models.py

import numpy as np

def ca_predict(x, P, Q_ca, delta_t):
    """
    Performs the prediction step for the Constant Acceleration (CA) model.
    State vector x: [px, py, vx, vy, ax, ay, omega]'
    """
    F = np.eye(7)
    
    # Update position with velocity and acceleration
    F[0, 2] = delta_t
    F[1, 3] = delta_t
    F[0, 4] = 0.5 * delta_t**2
    F[1, 5] = 0.5 * delta_t**2
    
    # Update velocity with acceleration
    F[2, 4] = delta_t
    F[3, 5] = delta_t

    # Predict state and covariance
    x_pred = F @ x
    P_pred = F @ P @ F.T + Q_ca
    
    return x_pred, P_pred


def cv_predict(x, P, Q_cv, delta_t, ego_yaw_rate):
    """
    Performs the prediction step for the Constant Velocity (CV) model,
    compensating for ego-vehicle rotation.
    State vector x: [px, py, vx, vy, ax, ay, omega]'
    """
    F = np.eye(7)
    F[0, 2] = delta_t
    F[1, 3] = delta_t

    # Linearly predict state
    x_linear_pred = F @ x

    # Compensate for ego-vehicle's rotation
    if abs(ego_yaw_rate) > 1e-4:
        rotation_angle = -ego_yaw_rate * delta_t
        cos_rot = np.cos(rotation_angle)
        sin_rot = np.sin(rotation_angle)
        
        R_mat = np.array([[cos_rot, -sin_rot],
                          [sin_rot,  cos_rot]])

        # Apply rotation to predicted position and velocity
        pos_rotated = R_mat @ x_linear_pred[0:2]
        vel_rotated = R_mat @ x_linear_pred[2:4]
        
        x_pred = np.vstack((pos_rotated, vel_rotated, x_linear_pred[4:7]))
    else:
        x_pred = x_linear_pred

    # Predict covariance
    P_pred = F @ P @ F.T + Q_cv
    
    return x_pred, P_pred


def ct_predict(x, P, Q_ct, delta_t):
    """
    Performs the prediction step for the Constant Turn (CT) model.
    State vector x: [px, py, vx, vy, ax, ay, omega]'
    """
    px, py, vx, vy, ax, ay, omega = x.flatten()
    
    x_pred = np.zeros_like(x)
    
    # --- State Prediction ---
    # Handle the singularity case where omega is close to zero
    if abs(omega) < 0.05: # Using a slightly larger threshold for stability like in MATLAB
        # Fallback to a simple Constant Velocity model
        x_pred[0] = px + vx * delta_t
        x_pred[1] = py + vy * delta_t
        x_pred[2] = vx
        x_pred[3] = vy
    else: # Standard Constant Turn model equations
        sin_wT = np.sin(omega * delta_t)
        cos_wT = np.cos(omega * delta_t)
        
        x_pred[0] = px + (vx * sin_wT - vy * (1 - cos_wT)) / omega
        x_pred[1] = py + (vx * (1 - cos_wT) + vy * sin_wT) / omega
        x_pred[2] = vx * cos_wT - vy * sin_wT
        x_pred[3] = vx * sin_wT + vy * cos_wT
        
    # Acceleration and omega are assumed constant
    x_pred[4], x_pred[5], x_pred[6] = ax, ay, omega

    # --- Jacobian (F) Calculation ---
    F = np.eye(7)
    if abs(omega) < 0.05: # Jacobian for CV fallback
        F[0, 2] = delta_t
        F[1, 3] = delta_t
    else: # Jacobian for standard CT model
        sin_wT = np.sin(omega * delta_t)
        cos_wT = np.cos(omega * delta_t)
        
        # Derivatives with respect to vx
        F[0, 2] = sin_wT / omega
        F[1, 2] = (1 - cos_wT) / omega
        F[2, 2] = cos_wT
        F[3, 2] = sin_wT
        
        # Derivatives with respect to vy
        F[0, 3] = -(1 - cos_wT) / omega
        F[1, 3] = sin_wT / omega
        F[2, 3] = -sin_wT
        F[3, 3] = cos_wT
        
        # >>>>>>>>>>>>>>>>> MODIFICATION START: CORRECTED JACOBIAN <<<<<<<<<<<<<<<<<<<
        # These formulas now directly match the MATLAB implementation for the
        # partial derivatives of the state prediction with respect to omega.
        
        # Derivative of predicted px w.r.t. omega
        term1_px = -vx * sin_wT + vy * cos_wT
        F[0, 6] = (term1_px * omega - (vx * sin_wT - vy * (1-cos_wT))) / omega**2
        
        # Derivative of predicted py w.r.t. omega
        term1_py = vx * cos_wT + vy * sin_wT
        F[1, 6] = (term1_py * omega - (vx * (1-cos_wT) + vy * sin_wT)) / omega**2
        
        # Derivative of predicted vx w.r.t. omega
        F[2, 6] = (-vx * sin_wT - vy * cos_wT) * delta_t
        
        # Derivative of predicted vy w.r.t. omega
        F[3, 6] = (vx * cos_wT - vy * sin_wT) * delta_t
        # >>>>>>>>>>>>>>>>> MODIFICATION END <<<<<<<<<<<<<<<<<<<
        
    # --- Covariance Prediction ---
    P_pred = F @ P @ F.T + Q_ct

    return x_pred, P_pred