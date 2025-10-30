# src/utils/calculate_vehicle_dynamics.py

import numpy as np
import warnings

def calculate_vehicle_dynamics(
    shaft_torque_nm, 
    engaged_gear, 
    current_vehicle_speed_mps, 
    road_grade_deg, 
    wheel_radius, 
    vehicle_mass, 
    gear_ratios, 
    rolling_resistance_n, 
    drag_coeff_n_per_kmph_sq
):
    """
    Calculates the vehicle's longitudinal acceleration based on shaft torque,
    gear, speed, and road grade.

    Args:
        shaft_torque_nm (float): Shaft torque in Newton-meters (Nm).
        engaged_gear (int): Currently engaged gear (e.g., 1 or 2).
        current_vehicle_speed_mps (float): Current vehicle speed in m/s.
        road_grade_deg (float): Road grade/slope in degrees (positive for uphill).
        wheel_radius (float): Wheel radius in meters (m).
        vehicle_mass (float): Vehicle mass in kilograms (kg).
        gear_ratios (dict): Dictionary containing gear ratios (e.g., {'gear1': 15.8}).
        rolling_resistance_n (float): Constant rolling resistance force in Newtons (N).
        drag_coeff_n_per_kmph_sq (float): Aerodynamic drag coefficient in N/(kmph)^2.

    Returns:
        float: Calculated longitudinal acceleration in m/s^2.
    """
    
    # Determine the active gear ratio
    if engaged_gear == 1:
        active_gear_ratio = gear_ratios.get('gear1', 0)
    elif engaged_gear == 2:
        active_gear_ratio = gear_ratios.get('gear2', 0)
    else:
        warnings.warn(f"Unknown gear {engaged_gear}. Assuming 1st gear.")
        active_gear_ratio = gear_ratios.get('gear1', 0)

    if not active_gear_ratio or np.isnan(active_gear_ratio):
        return 0.0

    # 1. Calculate Tractive Force
    tractive_force_n = (shaft_torque_nm * active_gear_ratio) / wheel_radius

    # 2. Calculate Resistance Forces
    current_vehicle_speed_kmph = current_vehicle_speed_mps * 3.6
    drag_force_n = drag_coeff_n_per_kmph_sq * (current_vehicle_speed_kmph**2)
    
    # Gravitational Force due to Road Grade
    g = 9.81
    if np.isnan(road_grade_deg):
        road_grade_deg = 0.0
    
    road_grade_rad = np.deg2rad(road_grade_deg)
    gravity_force_n = vehicle_mass * g * np.sin(road_grade_rad)
    
    total_resistance_force_n = rolling_resistance_n + drag_force_n + gravity_force_n

    # 3. Calculate Net Force
    net_force_n = tractive_force_n - total_resistance_force_n

    # 4. Calculate Acceleration (F = ma)
    if vehicle_mass > 0:
        acceleration_mps2 = net_force_n / vehicle_mass
    else:
        acceleration_mps2 = 0.0
        
    return acceleration_mps2