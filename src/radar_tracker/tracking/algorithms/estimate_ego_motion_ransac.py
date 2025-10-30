# src/algorithms/estimate_ego_motion_ransac.py

import numpy as np
import warnings

def _solve_least_squares(A, b):
    """
    Solves the linear least-squares problem Ax = b using the normal equation.

    Args:
        A (np.ndarray): The matrix A.
        b (np.ndarray): The vector b.

    Returns:
        np.ndarray: The solution vector x, or None if the system is singular.
    """
    try:
        # Implementation of the normal equation: x = (A^T A)^-1 A^T b
        ata = A.T @ A
        atb = A.T @ b
        # Use np.linalg.inv for the matrix inversion
        x = np.linalg.inv(ata) @ atb
        return x
    except np.linalg.LinAlgError:
        # This occurs if (A^T A) is a singular matrix (not invertible)
        return None

def estimate_ego_motion_ransac(points, radial_speeds, inlier_threshold, min_inlier_ratio, max_iterations):
    """
    Estimates 2D ego-motion (Vx, Vy) from radar points and their radial
    speeds using a vectorized RANSAC algorithm.

    Args:
        points (np.ndarray): Nx2 array of (x, y) coordinates for radar points.
        radial_speeds (np.ndarray): N-element array of radial speeds.
        inlier_threshold (float): The maximum error for a point to be considered an inlier.
        min_inlier_ratio (float): The minimum ratio of inliers required for a valid model.
        max_iterations (int): The number of RANSAC iterations to perform.

    Returns:
        tuple: A tuple containing (estimated_vx, estimated_vy, inlier_ratio, outlier_indices).
    """
    num_points = points.shape[0]

    if num_points < 4:
        return 0.0, 0.0, 0.0, np.arange(num_points)

    best_inlier_count = 0
    best_vx = 0.0
    best_vy = 0.0
    best_inlier_indices = np.array([], dtype=int)

    r_all = np.sqrt(points[:, 0]**2 + points[:, 1]**2)
    valid_indices_mask = r_all > 1e-6
    valid_indices = np.where(valid_indices_mask)[0]

    if len(valid_indices) < 4:
        return 0.0, 0.0, 0.0, np.arange(num_points)

    points_valid = points[valid_indices_mask, :]
    r_valid = r_all[valid_indices_mask]
    
    a_full = np.vstack([-points_valid[:, 0] / r_valid, -points_valid[:, 1] / r_valid]).T

    for _ in range(max_iterations):
        sample_indices = np.random.choice(num_points, 4, replace=False)
        p_sample = points[sample_indices, :]
        r_sample = r_all[sample_indices]

        if np.any(r_sample < 1e-6):
            continue

        a_sample = np.vstack([-p_sample[:, 0] / r_sample, -p_sample[:, 1] / r_sample]).T
        b_sample = radial_speeds[sample_indices]
        
        # --- MODIFICATION: Use custom solver ---
        current_ego_vel = _solve_least_squares(a_sample, b_sample)
        if current_ego_vel is None:
            continue
        # --- END OF MODIFICATION ---

        predicted_radial_speeds = a_full @ current_ego_vel
        errors = np.abs(radial_speeds[valid_indices_mask] - predicted_radial_speeds)
        
        current_inlier_mask = errors < inlier_threshold
        current_inlier_count = np.sum(current_inlier_mask)

        if current_inlier_count > best_inlier_count:
            best_inlier_count = current_inlier_count
            best_vx, best_vy = current_ego_vel
            best_inlier_indices = valid_indices[current_inlier_mask]

    estimated_vx, estimated_vy = best_vx, best_vy
    if len(best_inlier_indices) >= 4:
        a_inliers = a_full[np.isin(valid_indices, best_inlier_indices)]
        b_inliers = radial_speeds[best_inlier_indices]

        # --- MODIFICATION: Use custom solver ---
        refined_ego_vel = _solve_least_squares(a_inliers, b_inliers)
        if refined_ego_vel is not None:
            estimated_vx, estimated_vy = refined_ego_vel
        else:
            warnings.warn("RANSAC-LSQ refinement failed, falling back to best RANSAC estimate.")
        # --- END OF MODIFICATION ---

    inlier_ratio = best_inlier_count / num_points
    all_indices = np.arange(num_points)
    outlier_indices = np.setdiff1d(all_indices, best_inlier_indices, assume_unique=True)

    return estimated_vx, estimated_vy, inlier_ratio, outlier_indices