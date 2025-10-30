# src/utils/coordinate_transforms.py

import numpy as np

def polar_to_cartesian(r, th, r_dot, v_tan):
    """
    Converts a polar state to a Cartesian state.
    Note the coordinate system: 0 radians is along the +Y axis.

    Args:
        r (float or np.ndarray): Range.
        th (float or np.ndarray): Angle (theta) in radians.
        r_dot (float or np.ndarray): Range rate.
        v_tan (float or np.ndarray): Tangential velocity.

    Returns:
        tuple: A tuple containing (x_cart, y_cart, vx_cart, vy_cart).
    """
    x_cart = r * np.sin(th)
    y_cart = r * np.cos(th)

    vx_cart = r_dot * np.sin(th) + v_tan * np.cos(th)
    vy_cart = r_dot * np.cos(th) - v_tan * np.sin(th)

    return x_cart, y_cart, vx_cart, vy_cart


def cartesian_to_polar(x_cart, y_cart, vx_cart, vy_cart):
    """
    Converts a Cartesian state to a polar state.
    Note the coordinate system: 0 radians is along the +Y axis.

    Args:
        x_cart (float or np.ndarray): X position.
        y_cart (float or np.ndarray): Y position.
        vx_cart (float or np.ndarray): X velocity.
        vy_cart (float or np.ndarray): Y velocity.

    Returns:
        tuple: A tuple containing (r, th, r_dot, v_tan).
    """
    r = np.sqrt(x_cart**2 + y_cart**2)
    
    # atan2(x, y) is used because 0 radians/degrees is along the +Y axis
    th = np.arctan2(x_cart, y_cart)

    # Handle the case where the object is at the origin to avoid division by zero
    if np.isscalar(r):
        if r > 1e-6:
            r_dot = (x_cart * vx_cart + y_cart * vy_cart) / r
            v_tan = (y_cart * vx_cart - x_cart * vy_cart) / r
        else:
            r_dot = 0.0
            v_tan = 0.0
    else:
        # Vectorized implementation for NumPy arrays
        r_dot = np.zeros_like(r)
        v_tan = np.zeros_like(r)
        
        valid_indices = r > 1e-6
        
        r_dot[valid_indices] = (x_cart[valid_indices] * vx_cart[valid_indices] + 
                                y_cart[valid_indices] * vy_cart[valid_indices]) / r[valid_indices]
        
        v_tan[valid_indices] = (y_cart[valid_indices] * vx_cart[valid_indices] - 
                                x_cart[valid_indices] * vy_cart[valid_indices]) / r[valid_indices]

    return r, th, r_dot, v_tan

def interp_with_extrap(x, xp, fp):
    """
    Performs 1D linear interpolation, with extrapolation.
    This version is robust to both scalar and array inputs for x.
    """
    xp = np.asarray(xp)
    fp = np.asarray(fp)

    # Check if the input x is a single number (scalar)
    is_scalar = not isinstance(x, (list, tuple, np.ndarray))
    
    # Temporarily convert scalar to a 1-element array for consistent processing
    if is_scalar:
        x = np.array([x])

    # Perform standard interpolation
    y = np.interp(x, xp, fp)

    # --- Extrapolation for values of x below the xp range ---
    ind_below = x < xp[0]
    if np.any(ind_below):
        # Linearly extrapolate using the slope of the first two points
        y[ind_below] = fp[0] + (x[ind_below] - xp[0]) * (fp[1] - fp[0]) / (xp[1] - xp[0])
        
    # --- Extrapolation for values of x above the xp range ---
    ind_above = x > xp[-1]
    if np.any(ind_above):
        # Linearly extrapolate using the slope of the last two points
        y[ind_above] = fp[-1] + (x[ind_above] - xp[-1]) * (fp[-1] - fp[-2]) / (xp[-1] - xp[-2])
    
    # Return a scalar if the original input was a scalar
    if is_scalar:
        return y[0]
    
    return y