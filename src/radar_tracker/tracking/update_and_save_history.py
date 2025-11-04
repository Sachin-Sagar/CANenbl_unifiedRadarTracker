# src/tracking/update_and_save_history.py

import json
import numpy as np
from ..console_logger import logger
import scipy.io as sio
import config
from .export_to_json import create_visualization_data

class NumpyEncoder(json.JSONEncoder):
    """ Custom encoder for numpy data types """
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        return json.JSONEncoder.default(self, obj)

def _convert_to_matlab_struct(py_list, struct_name=''):
    """
    Converts a Python list of dictionaries or objects into a NumPy object array
    that can be saved as a MATLAB struct array (Nx1), with a defined field order.
    """
    if len(py_list) == 0:
        return np.array([])

    dict_list = []
    if hasattr(py_list[0], '__dict__'):
        for item in py_list:
            dict_list.append(vars(item))
    else:
        dict_list = py_list

    # --- NEW: Define the canonical field order ---
    fhist_order = [
        'timestamp', 'pointCloud', 'posLocal', 'grid_map', 'point_to_grid_idx',
        'motionState', 'egoVx', 'egoVy', 'egoInlierRatio', 'correctedEgoSpeed_mps',
        'estimatedAcceleration_mps2', 'iirFilteredVx_ransac', 'iirFilteredVy_ransac',
        'dynamicStationaryBox', 'filtered_barrier_x', 'isOutlier', 'dbscanClusters',
        'cluster_grid_map', 'detectedClusterInfo'
    ]
    
    alltracks_order = [
        'id', 'immState', 'lastKnownPosition', 'age', 'hits', 'misses',
        'trajectory', 'historyLog', 'isLost', 'isConfirmed', 'ttc',
        'ttcCategory', 'detectionHistory', 'lastSeenFrame', 'stationaryCount'
    ]
    
    all_keys_found = set().union(*(d.keys() for d in dict_list))

    if struct_name == 'fHist':
        ordered_keys = fhist_order
    elif struct_name == 'allTracks':
        ordered_keys = alltracks_order
    else:
        ordered_keys = sorted(list(all_keys_found))

    final_ordered_keys = [key for key in ordered_keys if key in all_keys_found]
    for key in sorted(list(all_keys_found)):
        if key not in final_ordered_keys:
            final_ordered_keys.append(key)

    dtype = [(key, 'O') for key in final_ordered_keys]
    
    mat_struct = np.zeros((len(dict_list), 1), dtype=dtype)

    for i, py_dict in enumerate(dict_list):
        for key in final_ordered_keys:
            value = py_dict.get(key, np.nan)
            
            if value is None:
                value = np.nan
            
            # --- THIS IS THE FIX ---
            # If the value is a custom object (like the barrier struct),
            # convert it to a dictionary before processing.
            if hasattr(value, '__dict__'):
                value = vars(value)
            # --- END OF FIX ---

            is_list_of_dicts = False
            if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                is_list_of_dicts = True

            if is_list_of_dicts:
                mat_struct[i, 0][key] = _convert_to_matlab_struct(value, struct_name=key)
            else:
                mat_struct[i, 0][key] = value
                
    return mat_struct

def update_and_save_history(all_tracks, fhist, json_filename="track_history.json", params=None):
    """
    Saves the final data to a JSON file and a MATLAB-compatible .mat file.
    """
    if params is None:
        params = {}

    if config.DEBUG_FLAGS.get('log_final_history') and fhist:
        logger.debug("--- Final History Pre-Save Inspection ---")
        num_frames = len(fhist)
        sample_indices = sorted(list(set([0, 1, 2, num_frames//2, num_frames-3, num_frames-2, num_frames-1])))
        for i in sample_indices:
            if 0 <= i < num_frames:
                frame = fhist[i]
                ego_vx = getattr(frame, 'egoVx', 'N/A')
                logger.debug(f"[HISTORY] Frame {i}: egoVx = {ego_vx}")

    # --- 1. Save to JSON ---
    try:
        visualization_data = create_visualization_data(all_tracks, fhist, params)
        with open(json_filename, 'w') as f:
            json.dump(visualization_data, f, cls=NumpyEncoder, indent=4)
        logger.info(f"Successfully saved pretty-printed JSON data to {json_filename}")
    except Exception as e:
        logger.error(f"An error occurred while saving the JSON file: {e}")

    # --- 2. Save to .mat ---
    mat_filename = json_filename.replace('.json', '_python.mat')
    try:
        logger.info("Converting Python data to MATLAB-compatible structs...")
        
        allTracks_mat = _convert_to_matlab_struct(all_tracks, struct_name='allTracks')
        fHist_mat = _convert_to_matlab_struct(fhist, struct_name='fHist')

        matlab_export_data = {
            'allTracks': allTracks_mat,
            'fHist': fHist_mat
        }
        
        sio.savemat(mat_filename, matlab_export_data, do_compression=True)
        logger.info(f"Successfully saved data for MATLAB comparison to {mat_filename}")
    except Exception as e:
        logger.error(f"An error occurred while saving the .mat file: {e}")