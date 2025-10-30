# src/utils/calculate_ellipse_radii.py

import numpy as np

def calculate_ellipse_radii(p_pos_cart, prev_orientation_deg=None):
    """
    Computes the properties of the 95% confidence ellipse from the 2x2
    Cartesian position covariance matrix.

    Args:
        p_pos_cart (np.ndarray): The 2x2 Cartesian position covariance matrix.
        prev_orientation_deg (float, optional): The orientation from the
            previous frame, used to prevent angle wrapping/flipping.
            Defaults to None.

    Returns:
        tuple: A tuple containing (radii, orientation_angle_deg), where radii
               is a 1x2 NumPy array [minor_radius, major_radius].
    """
    # Symmetrize to ensure real eigenvalues for stability
    p_pos_symmetric = (p_pos_cart + p_pos_cart.T) / 2

    # Eigenvalue decomposition to find the ellipse axes lengths
    eigenvalues, _ = np.linalg.eig(p_pos_symmetric)
    
    # Chi-squared value for 95% confidence with 2 degrees of freedom
    chi2_val = 5.991
    
    # Radii are the square root of the eigenvalues scaled by the chi2 value
    # Use np.abs to handle potential minor negative eigenvalues from numerical instability
    radii = np.sqrt(chi2_val * np.abs(eigenvalues))
    radii = np.sort(radii) # Ensure [minor, major]

    # Use the stable direct formula for the base orientation
    p11 = p_pos_symmetric[0, 0]
    p12 = p_pos_symmetric[0, 1]
    p22 = p_pos_symmetric[1, 1]
    
    # This calculates the angle in the range [-90, 90] degrees
    current_orientation_deg = np.rad2deg(0.5 * np.arctan2(2 * p12, p11 - p22))

    # --- Unwrap Angle for Visual Continuity ---
    if prev_orientation_deg is not None and not np.isnan(prev_orientation_deg):
        angle_diff = current_orientation_deg - prev_orientation_deg
        
        # Wrap the angle difference to the range [-180, 180]
        angle_diff = (angle_diff + 180) % 360 - 180
        
        # If the shortest angular distance is > 90 degrees, it means the
        # principal axis has flipped. Correct the angle by 180 degrees.
        if abs(angle_diff) > 90:
            current_orientation_deg -= 180 * np.sign(angle_diff)
            
    return radii, current_orientation_deg