# src/tracking/parameters.py

import numpy as np

def define_parameters():
    """
    Defines all parameters for the radar tracking system.
    """
    params = {}

    # --- IMM Filter Parameters ---
    params['imm_params'] = {
        'initialModelProbabilities': np.array([0.8, 0.1, 0.1]),
        'modelTransitionMatrix': np.array([[0.98, 0.01, 0.01],
                                           [0.01, 0.98, 0.01],
                                           [0.01, 0.01, 0.98]]),
        'P_init': np.diag([1.0, 1.0, 2.0, 2.0, 1.0, 1.0, 0.5]),
        'Q_cv': np.diag([0.1, 0.1, 0.2, 0.2, 0.01, 0.01, 0.01]),
        'Q_ct': np.diag([0.1, 0.1, 0.2, 0.2, 0.01, 0.01, 0.1]),
        'Q_ca': np.diag([0.2, 0.2, 1.0, 1.0, 2.0, 2.0, 0.05])
    }

    # --- Kalman Filter Measurement Noise ---
    params['kf_measurement_noise'] = np.diag([0.5, np.deg2rad(2.0), 0.5])

    # --- Gating and Assignment Parameters ---
    params['gating_params'] = {
        'positionGatingThreshold': 5.0, # meters
        'minAngle': -45, # degrees
        'maxAngle': 45,  # degrees
        'maxRadius': 80, # meters
        'maxRadialSpeedThreshold': 20 # m/s
    }
    params['assignment_params'] = {'assignmentThreshold': 10.0} # Mahalanobis distance squared
    params['jpda_params'] = {'PD': 0.9, 'lambda_c': 0.1, 'gating_chi2': 9.21}

    # --- Track Lifecycle Parameters ---
    params['lifecycle_params'] = {
        'confirmation_M': 3,
        'confirmation_N': 5,
        'maxMisses': 5,
        'maxTrajectoryLength': 50,
        'trackStationary': False
    }
    params['reassignment_params'] = {
        'reassignmentDistanceThreshold': 4.0, # meters
        'maxFramesLostForReassignment': 10
    }

    # --- TTC (Time to Collision) Parameters ---
    params['ttc_params'] = {'collisionRadius': 2.5} # meters

    # --- Ego Motion and RANSAC Parameters ---
    params['ego_motion_params'] = {
        'stationarySpeedThreshold': 0.5, # m/s
        'ransacInlierThreshold': 0.5, # m/s
        'ransacMinInlierRatio': 0.5,
        'ransacMaxIterations': 20,
        'iir_alpha': 0.4,
        'increasedMeasurementNoiseFactor': 10
    }
    params['ego_motion_classification_params'] = {
        'turn_yawRate_thrs': np.deg2rad(3.0),
        'confirmation_samples': 3
    }

    # --- Clustering and Grid Parameters ---
    params['dbscan_params'] = {'epsilon_pos': 2.0, 'epsilon_vel': 2.0, 'min_pts': 3}
    params['grid_config'] = {'X_RANGE': [-40, 40], 'Y_RANGE': [0, 80], 'NUM_COLS': 40, 'NUM_ROWS': 40}
    params['cluster_filter_params'] = {'min_outlierClusterRatio_thrs': 0.6}
    params['stationary_cluster_box'] = {'X_RANGE': [-3, 3], 'Y_RANGE': [0.5, 7.5]}

    # --- Barrier Detection Parameters ---
    params['barrier_detect_params'] = {
        'default_x_range': [-3.0, 3.0],
        'longitudinal_range': [10, 50],
        'min_pts_for_barrier': 10,
        'iir_alpha_barrier': 0.2,
        'safety_margin': 0.5
    }

    # --- Reflection Filtering Parameters ---
    params['reflection_detection_params'] = {
        'speed_similarity_threshold_mps': 0.5
    }

    # --- Vehicle Physical Parameters ---
    params['vehicle_params'] = {
        'WHEEL_RADIUS': 0.35, # meters
        'VEHICLE_MASS': 2000, # kg
        'GEAR_RATIOS': {'gear1': 15.0, 'gear2': 8.0},
        'ROLLING_RESISTANCE_N': 150,
        'DRAG_COEFF_N_PER_KMPH_SQ': 0.4
    }

    # --- Debugging ---
    params['debug_mode'] = True
    params['debug_mode1'] = True # For more verbose logging

    return params