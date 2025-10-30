# src/algorithms/estimate_ego_motion.py

import numpy as np
import numbers # <-- Import the numbers module

# Import the modules we have already ported
from .estimate_ego_motion_ransac import estimate_ego_motion_ransac
from ..utils.calculate_vehicle_dynamics import calculate_vehicle_dynamics
from ..filters.ego_ekf import ego_ekf_predict, ego_ekf_correct

def estimate_ego_motion(
    spatial_points, raw_radial_speeds, can_veh_speed_kmph, shaft_torque_nm, 
    engaged_gear, can_road_grade_deg, imu_ax_mps2, imu_ay_mps2, 
    imu_omega_radps, grade_rad, roll_rad, ego_kf_state, 
    filtered_vx_ego_iir, filtered_vy_ego_iir, delta_t, 
    vehicle_params, ego_motion_params, original_ego_kf_r
):
    """
    Estimates the ego vehicle's state using a 5D Extended Kalman Filter.
    It fuses information from radar (RANSAC), CAN bus, a dynamics model, and an IMU.
    """
    # --- MODIFICATION START: Add a robust function to sanitize inputs ---
    def get_numeric(value, default):
        """Returns the value if it's a valid number, otherwise returns the default."""
        if not isinstance(value, numbers.Number) or np.isnan(value):
            return default
        return value
    
    # Sanitize all potentially problematic inputs at the beginning of the function
    can_veh_speed_kmph = get_numeric(can_veh_speed_kmph, np.nan)
    shaft_torque_nm = get_numeric(shaft_torque_nm, np.nan)
    engaged_gear = get_numeric(engaged_gear, np.nan)
    can_road_grade_deg = get_numeric(can_road_grade_deg, 0.0)
    imu_ax_mps2 = get_numeric(imu_ax_mps2, 0.0)
    imu_ay_mps2 = get_numeric(imu_ay_mps2, 0.0)
    imu_omega_radps = get_numeric(imu_omega_radps, 0.0)
    # --- MODIFICATION END ---

    # --- 0. Initialize Outputs ---
    ransac_vx, ransac_vy, ego_inlier_ratio = 0.0, 0.0, 0.0
    ransac_successful = False
    ax_dynamics = np.nan
    outlier_indices = np.array([], dtype=int)
    
    # --- 1. RANSAC Ego-Motion Estimation ---
    # This line will now work correctly because can_veh_speed_kmph is guaranteed to be a number (or np.nan)
    is_vehicle_moving = not np.isnan(can_veh_speed_kmph) and \
                        (can_veh_speed_kmph / 3.6) > ego_motion_params['stationarySpeedThreshold']
    
    if is_vehicle_moving and spatial_points.shape[0] >= 4:
        ransac_vx, ransac_vy, ego_inlier_ratio, outlier_indices = estimate_ego_motion_ransac(
            spatial_points, raw_radial_speeds,
            ego_motion_params['ransacInlierThreshold'],
            ego_motion_params['ransacMinInlierRatio'],
            ego_motion_params['ransacMaxIterations']
        )
        if ego_inlier_ratio >= ego_motion_params['ransacMinInlierRatio']:
            ransac_successful = True
    else:
        if spatial_points.shape[0] > 0:
            outlier_indices = np.arange(spatial_points.shape[0])

    # --- 2. IIR Filter RANSAC Outputs ---
    iir_alpha = ego_motion_params['iir_alpha']
    if ransac_successful:
        filtered_vx_ego_iir = iir_alpha * ransac_vx + (1 - iir_alpha) * filtered_vx_ego_iir
        filtered_vy_ego_iir = iir_alpha * ransac_vy + (1 - iir_alpha) * filtered_vy_ego_iir
    
    # --- 3. Vehicle Dynamics Model ---
    has_torque_data = not np.isnan(shaft_torque_nm)
    has_gear_data = not np.isnan(engaged_gear)
    
    if has_torque_data and has_gear_data:
        current_predicted_vx_mps = ego_kf_state['x'][0, 0]
        ax_dynamics = calculate_vehicle_dynamics(
            shaft_torque_nm, engaged_gear, current_predicted_vx_mps, can_road_grade_deg,
            vehicle_params['WHEEL_RADIUS'], vehicle_params['VEHICLE_MASS'],
            vehicle_params['GEAR_RATIOS'], vehicle_params['ROLLING_RESISTANCE_N'],
            vehicle_params['DRAG_COEFF_N_PER_KMPH_SQ']
        )
    else:
        ax_dynamics = ego_kf_state['x'][2, 0] # Use previous acceleration

    # --- 4. EKF Prediction Step ---
    x_pred, P_pred = ego_ekf_predict(
        ego_kf_state['x'], ego_kf_state['P'], ego_kf_state['Q'], delta_t, ax_dynamics
    )
    
    # --- 5. Assemble EKF Measurement Vector (z) and Noise Matrix (R) ---
    z = np.zeros((5, 1))
    R_current = original_ego_kf_r.copy()
    
    z[2] = imu_ax_mps2
    z[3] = imu_ay_mps2
    z[4] = imu_omega_radps
    
    # Dynamically adjust measurements and noise based on availability
    increased_noise = ego_motion_params['increasedMeasurementNoiseFactor']
    
    if not is_vehicle_moving: # Stationary
        z[0] = 0.0 # Vx
        z[1] = 0.0 # Vy
        R_current[0, 0] = 0.001
        R_current[1, 1] = 0.001
    else: # Moving
        if not np.isnan(can_veh_speed_kmph):
            z[0] = can_veh_speed_kmph / 3.6
        else:
            R_current[0, 0] *= increased_noise

        if ransac_successful:
            # RANSAC's 'Vx' is the ego vehicle's lateral velocity 'Vy'
            z[1] = filtered_vx_ego_iir
        else:
            R_current[1, 1] *= increased_noise
            
    # --- 6. EKF Correction Step ---
    x_corr, P_corr = ego_ekf_correct(x_pred, P_pred, z, R_current, grade_rad, roll_rad)
    
    # --- 7. Package updated state and results ---
    updated_kf_state = {'x': x_corr, 'P': P_corr, 'Q': ego_kf_state['Q']}
    
    return (updated_kf_state, filtered_vx_ego_iir, filtered_vy_ego_iir, 
            ransac_vx, ransac_vy, ego_inlier_ratio, ax_dynamics, outlier_indices)