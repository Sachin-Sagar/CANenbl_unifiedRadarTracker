# src/export_to_json.py

import numpy as np
import logging

def _sanitize_for_json(value):
    """
    Helper function to prepare a value for JSON serialization, matching MATLAB's quirks.
    - Converts infinity and NaN to None (which becomes 'null').
    - Extracts the scalar value if it's a single-element list or numpy array.
    """
    if isinstance(value, (list, np.ndarray)):
        if len(value) == 1:
            value = value[0]
        else:
            # If it's still a list/array, return it for the encoder to handle
            return value

    if isinstance(value, (float, np.floating)):
        if np.isinf(value) or np.isnan(value):
            return None
    
    # --- ADDED CHECK ---
    # Explicitly handle the case where the input is already None
    if value is None:
        return None
    
    return value


def create_visualization_data(all_tracks, fhist, params):
    """
    Builds a dictionary with 'radarFrames' and 'tracks' keys, meticulously
    matching the MATLAB JSON schema for downstream applications.
    """
    debug_mode = params.get('debug_mode', False)
    if debug_mode: logging.info("Building final visualization data structure for JSON export...")

    visualization_data = {}

    # --- 1. Process Radar Frames (fHist) ---
    radar_frames_list = []
    for i, frame_data in enumerate(fhist):
        def get_attr_safe(obj, attr, default=None):
            val = getattr(obj, attr, default)
            # Return the value directly if it's not a float that is nan
            if not (isinstance(val, (float, np.floating)) and np.isnan(val)):
                return val
            return None # Return None for NaN floats

        # --- MODIFIED SECTION TO PREVENT CRASH ---
        # Get the gear value safely
        gear_val = get_attr_safe(frame_data, 'ETS_VCU_Gear_Engaged_St_enum', None)
        # Convert to float only if it's a valid number, otherwise keep it None
        if gear_val is not None:
            try:
                gear_val = float(gear_val)
            except (ValueError, TypeError):
                gear_val = None # Handle cases where it might be a non-numeric string
        
        frame_dict = {
            'timestamp': get_attr_safe(frame_data, 'timestamp'), 'frameIdx': i,
            'motionState': get_attr_safe(frame_data, 'motionState'),
            'egoVelocity': [get_attr_safe(frame_data, 'egoVx', 0), get_attr_safe(frame_data, 'egoVy', 0)],
            'canVehSpeed_kmph': get_attr_safe(frame_data, 'ETS_VCU_VehSpeed_Act_kmph'),
            'correctedEgoSpeed_mps': get_attr_safe(frame_data, 'correctedEgoSpeed_mps'),
            'shaftTorque_Nm': get_attr_safe(frame_data, 'ETS_MOT_ShaftTorque_Est_Nm'),
            'engagedGear': gear_val, # Use the safely converted value
            'estimatedAcceleration_mps2': get_attr_safe(frame_data, 'estimatedAcceleration_mps2'),
            'iirFilteredVx_ransac': get_attr_safe(frame_data, 'iirFilteredVx_ransac'),
            'iirFilteredVy_ransac': get_attr_safe(frame_data, 'iirFilteredVy_ransac'),
            'clusters': [], 'pointCloud': []
        }
        
        filtered_barrier = get_attr_safe(frame_data, 'filtered_barrier_x')
        if filtered_barrier is not None and hasattr(filtered_barrier, 'left') and hasattr(filtered_barrier, 'right'):
            frame_dict['filtered_barrier_x'] = [
                get_attr_safe(filtered_barrier, 'left'), 
                get_attr_safe(filtered_barrier, 'right')
            ]
        else:
            frame_dict['filtered_barrier_x'] = None
        
        clusters_info = getattr(frame_data, 'detectedClusterInfo', np.array([]))
        if clusters_info.size > 0:
            cluster_list = []
            for c in clusters_info:
                cluster_obj = {
                    'id': c.get('originalClusterID'), 'radialSpeed': c.get('radialSpeed'),
                    'vx': c.get('vx'), 'vy': c.get('vy'), 'azimuth': c.get('azimuth'), 
                    'isOutlier': c.get('isOutlierCluster'),
                    'isStationaryInBox': c.get('isStationary_inBox', False)
                }
                if c.get('X') is not None: cluster_obj['x'] = c.get('X')
                if c.get('Y') is not None: cluster_obj['y'] = c.get('Y')
                cluster_list.append(cluster_obj)
            frame_dict['clusters'] = cluster_list

        point_cloud_data = getattr(frame_data, 'pointCloud', None)
        if point_cloud_data is not None and point_cloud_data.size > 0:
            num_points = frame_data.posLocal.shape[1]
            frame_dict['pointCloud'] = [
                {'x': frame_data.posLocal[0, j], 'y': frame_data.posLocal[1, j],
                 'velocity': point_cloud_data[3, j] if point_cloud_data.shape[0] > 3 else None,
                 'snr': point_cloud_data[4, j] if point_cloud_data.shape[0] > 4 else None,
                 'clusterNumber': int(frame_data.dbscanClusters[j]) if hasattr(frame_data, 'dbscanClusters') and j < len(frame_data.dbscanClusters) else None,
                 'isOutlier': bool(frame_data.isOutlier[j]) if hasattr(frame_data, 'isOutlier') and j < len(frame_data.isOutlier) else None
                } for j in range(num_points)
            ]
        
        radar_frames_list.append(frame_dict)
    visualization_data['radarFrames'] = radar_frames_list

    # --- 2. Process Tracks (allTracks) ---
    tracks_list = []
    for track in all_tracks:
        track_export_obj = {'id': track.get('id'), 'isConfirmed': track.get('isConfirmed', False), 'historyLog': []}
        if len(all_tracks) > 1:
            track_export_obj['ttcCategoryTimeline'] = []

        if 'historyLog' in track and track['historyLog']:
            for log_entry in track['historyLog']:
                clean_log_entry = {
                    'frameIdx': log_entry.get('frameIdx'),
                    'predictedPosition': log_entry.get('predictedPosition'),
                    'predictedVelocity': log_entry.get('predictedVelocity'),
                    'correctedPosition': log_entry.get('correctedPosition'),
                    'ttc': _sanitize_for_json(log_entry.get('ttc')),
                    'isStationary': log_entry.get('isStationary'),
                    'covarianceP': log_entry.get('covarianceP'),
                    'ellipseRadii': log_entry.get('ellipseRadii'),
                    # Use the _sanitize_for_json helper for the angle as well
                    'ellipseAngle': _sanitize_for_json(log_entry.get('orientationAngle'))
                }
                track_export_obj['historyLog'].append(clean_log_entry)
                
                if 'ttcCategoryTimeline' in track_export_obj:
                    if log_entry.get('ttcCategory') is not None and log_entry.get('frameIdx') is not None:
                        track_export_obj['ttcCategoryTimeline'].append(
                            {'frameIdx': log_entry['frameIdx'], 'ttcCategory': log_entry['ttcCategory']}
                        )
        tracks_list.append(track_export_obj)
    visualization_data['tracks'] = tracks_list
    
    if debug_mode: logging.info("Finished building visualization data with strict schema.")
    return visualization_data