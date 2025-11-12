# src/tracking/export_to_json.py

import numpy as np
from .utils.calculate_ellipse_radii import calculate_ellipse_radii
from .utils.coordinate_transforms import cartesian_to_polar, polar_to_cartesian

def _convert_track_to_dict(track, params):
    """Converts a single Track object to a JSON-serializable dictionary."""
    
    # --- THIS IS THE FIX ---
    # Use .get() for safe dictionary access and use the correct keys
    
    if track.get('isLost'):
        return None

    # Get the fused covariance 'P' from the immState dictionary
    fused_cov = track.get('immState', {}).get('P')
    if fused_cov is None:
        return None # Not enough data to plot

    radii, angle_rad = calculate_ellipse_radii(fused_cov[:2, :2], 0.95)
    
    # Get the model probabilities (key is 'modelProbabilities', not 'mu')
    model_probs = track.get('immState', {}).get('modelProbabilities')
    if model_probs is None:
        return None # Not enough data

    # Get the list of individual model states (key is 'models', not 'X')
    model_states = track.get('immState', {}).get('models')
    if model_states is None or len(model_states) == 0:
        return None # Not enough data

    # Find the index of the most likely model
    c_model_index = np.argmax(model_probs)
    
    # Get the state vector 'x' from the most likely model in the 'models' list
    state_vec = model_states[c_model_index].get('x')
    if state_vec is None:
        return None # State vector is missing

    # Flatten state_vec in case it's (7,1)
    state_vec = state_vec.flatten()
    
    # Use polar coordinates for the primary state
    r, az, vr, _ = cartesian_to_polar(state_vec[0], state_vec[1], state_vec[2], state_vec[3])

    return {
        "id": track.get('id'),
        "isConfirmed": track.get('isConfirmed'),
        "isLost": track.get('isLost'),
        "age": track.get('age'),
        "hits": track.get('hits'),
        "misses": track.get('misses'),
        "x": float(state_vec[0]),
        "y": float(state_vec[1]),
        "vx": float(state_vec[2]),
        "vy": float(state_vec[3]),
        "ax": float(state_vec[4]) if len(state_vec) > 4 else 0.0,
        "ay": float(state_vec[5]) if len(state_vec) > 5 else 0.0,
        "range": float(r),
        "azimuth": float(np.rad2deg(az)),
        "radialSpeed": float(vr),
        "S_ellipse_radii": [float(radii[0]), float(radii[1])],
        "S_ellipse_angle_deg": float(np.rad2deg(angle_rad)),
        "modelProbabilities": [float(mu) for mu in model_probs.flatten()],
        "ttc": track.get('ttc') if track.get('ttc') is not None else float('inf'),
        "ttcCategory": track.get('ttcCategory')
    }
    # --- END OF FIX ---


def _convert_cluster_to_dict(cluster):
    """Converts a single cluster dictionary to a JSON-serializable dictionary."""
    if cluster is None:
        return None

    # Access data using dictionary .get() method
    x_mean = cluster.get('x_mean', np.nan)
    y_mean = cluster.get('y_mean', np.nan)
    vx_mean = cluster.get('vx_mean', np.nan)
    vy_mean = cluster.get('vy_mean', np.nan)
    
    r, az, vr, _ = cartesian_to_polar(x_mean, y_mean, vx_mean, vy_mean)

    return {
        "id": cluster.get('id', None), # Use .get()
        "radialSpeed": float(vr),
        "vx": float(vx_mean),
        "vy": float(vy_mean),
        "azimuth": float(np.rad2deg(az)),
        "isOutlier": cluster.get('isOutlier', False), # Use .get()
        "isStationaryInBox": cluster.get('isStationaryInBox', False), # Use .get()
        "x": float(x_mean),
        "y": float(y_mean)
    }

def _convert_point_to_dict(point):
    """Converts a single point (as a dictionary) to a JSON-serializable dictionary."""
    if point is None:
        return None

    x = point.get('x', np.nan)
    y = point.get('y', np.nan)
    v = point.get('velocity', np.nan)
    snr = point.get('snr', np.nan)
    cluster_num = point.get('clusterNumber', -1)
    is_outlier = point.get('isOutlier', False)

    return {
        "x": float(x),
        "y": float(y),
        "velocity": float(v),
        "snr": float(snr),
        "clusterNumber": int(cluster_num),
        "isOutlier": bool(is_outlier)
    }

def create_visualization_data(all_tracks, fhist, params=None):
    """
    Creates the final dictionary for JSON export, containing both radar frames
    and confirmed tracks.
    """
    if params is None:
        params = {}
        
    output_data = {
        "radarFrames": [],
        "tracks": []
    }

    # Process all radar frames
    for frame in fhist:
        if frame is None:
            continue
            
        # Handle ego velocity (which might be None or NaN)
        ego_vx = getattr(frame, 'egoVx', None)
        ego_vy = getattr(frame, 'egoVy', None)
        if not np.isfinite(ego_vx): ego_vx = None
        if not np.isfinite(ego_vy): ego_vy = None

        # 1. Safely get the can_signals dictionary from the frame object
        can_signals = getattr(frame, 'can_signals', {})

        road_grade = getattr(frame, 'EstimatedGrade_Est_Deg', None)
        if road_grade is not None and not np.isfinite(road_grade):
            road_grade = None

        # 2. Build the frame_output dictionary using getattr for frame object properties
        #    and .get() for the can_signals dictionary
        frame_output = {
            "timestamp": getattr(frame, 'timestamp', None),
            "frameIdx": getattr(frame, 'frameIdx', None),
            "motionState": getattr(frame, 'motionState', None),
            "egoVelocity": [ego_vx, ego_vy],
            
            # --- Read all CAN values from the stored dictionary ---
            "canVehSpeed_kmph": can_signals.get('ETS_VCU_VehSpeed_Act_kmph', None),
            "AccelPedal_Act_perc": can_signals.get('ETS_VCU_AccelPedal_Act_perc', None),
            "shaftTorque_Nm": can_signals.get('ETS_MOT_ShaftTorque_Est_Nm', None),
            "engagedGear": can_signals.get('ETS_VCU_Gear_Engaged_St_enum', None),
            "roadGrade_Deg": road_grade,
            
            # --- Non-CAN fields ---
            "correctedEgoSpeed_mps": getattr(frame, 'correctedEgoSpeed_mps', None),
            "estimatedAcceleration_mps2": getattr(frame, 'estimatedAcceleration_mps2', None),
            "iirFilteredVx_ransac": getattr(frame, 'iirFilteredVx_ransac', 0.0),
            "iirFilteredVy_ransac": getattr(frame, 'iirFilteredVy_ransac', 0.0),
            "clusters": [],
            "pointCloud": [],
            # Safely access nested barrier object properties
            "filtered_barrier_x": getattr(getattr(frame, 'filtered_barrier_x', {}), 'x', [params.get('barrierXMin'), params.get('barrierXMax')])
        }

        # 3. Add all other CAN signals that aren't already manually placed
        for signal_name, value in can_signals.items():
            if signal_name not in frame_output:
                frame_output[signal_name] = value
        
        # Add clusters
        point_cloud_data = getattr(frame, 'pointCloud', None)
        cluster_info = getattr(frame, 'detectedClusterInfo', None)

        is_cluster_info_non_empty = False
        if cluster_info is not None:
            if isinstance(cluster_info, np.ndarray):
                is_cluster_info_non_empty = cluster_info.size > 0
            elif hasattr(cluster_info, '__len__'):
                is_cluster_info_non_empty = len(cluster_info) > 0

        if is_cluster_info_non_empty:
            for cluster in cluster_info:
                cluster_dict = _convert_cluster_to_dict(cluster)
                if cluster_dict:
                    frame_output["clusters"].append(cluster_dict)

        # Add point cloud
        is_point_cloud_non_empty = False
        if point_cloud_data is not None and isinstance(point_cloud_data, dict) and 'x' in point_cloud_data:
            point_x_array = point_cloud_data.get('x')
            if point_x_array is not None:
                if isinstance(point_x_array, np.ndarray):
                    is_point_cloud_non_empty = point_x_array.size > 0
                elif hasattr(point_x_array, '__len__'):
                    is_point_cloud_non_empty = len(point_x_array) > 0

        if is_point_cloud_non_empty:
            for i in range(len(point_cloud_data['x'])):
                point = {
                    'x': point_cloud_data['x'][i],
                    'y': point_cloud_data['y'][i],
                    'velocity': point_cloud_data['velocity'][i],
                    'snr': point_cloud_data['snr'][i],
                    'clusterNumber': point_cloud_data['clusterNumber'][i],
                    'isOutlier': point_cloud_data['isOutlier'][i]
                }
                point_dict = _convert_point_to_dict(point)
                if point_dict:
                    frame_output["pointCloud"].append(point_dict)

        output_data["radarFrames"].append(frame_output)

    # Process all tracks
    for track in all_tracks:
        track_dict = _convert_track_to_dict(track, params)
        if track_dict:
            output_data["tracks"].append(track_dict)

    return output_data