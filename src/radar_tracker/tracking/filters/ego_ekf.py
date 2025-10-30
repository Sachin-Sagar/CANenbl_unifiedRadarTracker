# src/filters/ego_ekf.py

import numpy as np

def ego_ekf_predict(x, P, Q, dt, ax_dynamics):
    """
    Performs the physics-based prediction step for the ego-motion EKF.
    State vector x: [Vx, Vy, ax, ay, omega]'

    Args:
        x (np.ndarray): The current state vector (5x1).
        P (np.ndarray): The current state covariance matrix (5x5).
        Q (np.ndarray): The process noise covariance matrix (5x5).
        dt (float): The time step (delta_t) in seconds.
        ax_dynamics (float): The longitudinal acceleration from the vehicle dynamics model.

    Returns:
        tuple: A tuple containing (x_pred, P_pred).
    """
    # --- 1. Extract states for clarity ---
    vx, vy, ax, ay, omega = x.flatten()

    # --- 2. Predict the state using the motion model ---
    x_pred = np.zeros_like(x)
    x_pred[0] = vx + (ax - vy * omega) * dt
    x_pred[1] = vy + (ay + vx * omega) * dt
    x_pred[2] = ax_dynamics  # ax is predicted directly by the dynamics model
    x_pred[3] = ay           # Assume lateral acceleration is constant
    x_pred[4] = omega        # Assume yaw rate is constant
    
    # --- 3. Calculate the Jacobian matrix (F) of the motion model ---
    F = np.eye(5)
    
    # Partial derivatives for Vx_pred
    F[0, 1] = -omega * dt  # d(Vx_pred)/d(Vy)
    F[0, 2] = dt           # d(Vx_pred)/d(ax)
    F[0, 4] = -vy * dt     # d(Vx_pred)/d(omega)
    
    # Partial derivatives for Vy_pred
    F[1, 0] = omega * dt   # d(Vy_pred)/d(Vx)
    F[1, 3] = dt           # d(Vy_pred)/d(ay)
    F[1, 4] = vx * dt      # d(Vy_pred)/d(omega)

    # Partial derivatives for ax_pred (ax_dynamics is an external input)
    F[2, :] = 0.0

    # --- 4. Predict the error covariance ---
    P_pred = F @ P @ F.T + Q
    
    return x_pred, P_pred


def ego_ekf_correct(x_pred, P_pred, z, R, grade_rad, roll_rad):
    """
    Performs the correction step for the ego-motion EKF.
    State vector x: [Vx, Vy, ax, ay, omega]'

    Args:
        x_pred (np.ndarray): The predicted state vector (5x1).
        P_pred (np.ndarray): The predicted state covariance matrix (5x5).
        z (np.ndarray): The measurement vector (5x1).
        R (np.ndarray): The measurement noise covariance matrix (5x5).
        grade_rad (float): The vehicle's grade (pitch) in radians.
        roll_rad (float): The vehicle's roll in radians.

    Returns:
        tuple: A tuple containing (x_corr, P_corr).
    """
    g = 9.81  # Acceleration due to gravity in m/s^2

    # --- 1. Predict the measurement using the non-linear model h(x) ---
    vx_p, vy_p, ax_p, ay_p, omega_p = x_pred.flatten()

    h_x = np.array([
        vx_p,
        vy_p,
        ax_p - vy_p * omega_p + g * np.sin(grade_rad),
        ay_p + vx_p * omega_p + g * np.sin(roll_rad),
        omega_p
    ]).reshape(5, 1)

    # --- 2. Calculate the Jacobian matrix (H) of the measurement model ---
    H = np.zeros((5, 5))
    
    H[0, 0] = 1.0  # d(h_Vx)/d(Vx)
    H[1, 1] = 1.0  # d(h_Vy)/d(Vy)
    
    # d(h_ax_imu)/dx
    H[2, 1] = -omega_p    # d/d(Vy)
    H[2, 2] = 1.0         # d/d(ax)
    H[2, 4] = -vy_p       # d/d(omega)

    # d(h_ay_imu)/dx
    H[3, 0] = omega_p     # d/d(Vx)
    H[3, 3] = 1.0         # d/d(ay)
    H[3, 4] = vx_p        # d/d(omega)

    H[4, 4] = 1.0         # d(h_omega_imu)/d(omega)

    # --- 3. Perform the standard EKF correction steps ---
    y = z - h_x
    S = H @ P_pred @ H.T + R
    
    # K = P_pred * H' / S (in MATLAB) becomes this in NumPy
    K = P_pred @ H.T @ np.linalg.inv(S)
    
    x_corr = x_pred + K @ y
    P_corr = (np.eye(x_pred.shape[0]) - K @ H) @ P_pred
    
    return x_corr, P_corr