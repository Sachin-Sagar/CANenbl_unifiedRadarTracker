# src/data_adapter.py

import numpy as np
from .hardware.read_and_parse_frame import FrameData

class FHistFrame:
    """A class to mimic the structure of a single fHist frame from the .mat file."""
    def __init__(self):
        self.timestamp = 0.0
        self.pointCloud = np.array([])
        self.posLocal = np.array([])
        # --- Initialize other fields used by the tracker with default values ---
        self.motionState = 0
        self.isOutlier = np.array([], dtype=bool)
        self.egoVx = 0.0
        self.egoVy = 0.0
        self.correctedEgoSpeed_mps = 0.0
        self.estimatedAcceleration_mps2 = np.nan
        self.iirFilteredVx_ransac = 0.0
        self.iirFilteredVy_ransac = 0.0
        self.grid_map = []
        self.dbscanClusters = np.array([])
        self.detectedClusterInfo = np.array([])
        self.filtered_barrier_x = None # Will be populated by the tracker

def adapt_frame_data_to_fhist(frame_data, last_timestamp_ms):
    """
    Converts a real-time FrameData object into an FHistFrame object
    that the tracking algorithms can process.
    """
    fhist_frame = FHistFrame()
    fhist_frame.timestamp = last_timestamp_ms + 50.0

    if frame_data.point_cloud is not None and frame_data.point_cloud.size > 0:
        fhist_frame.pointCloud = frame_data.point_cloud
        fhist_frame.posLocal = frame_data.point_cloud[1:3, :]
    else:
        fhist_frame.pointCloud = np.empty((5, 0))
        fhist_frame.posLocal = np.empty((2, 0))

    fhist_frame.isOutlier = np.zeros(frame_data.num_points, dtype=bool)
    return fhist_frame

def adapt_matlab_frame_to_fhist(matlab_frame):
    """
    Converts a single frame loaded from a fHist.mat file (as a mat_struct)
    into the FHistFrame class structure used by the tracker.
    """
    fhist_frame = FHistFrame()
    
    # Directly map the fields that already exist
    fhist_frame.timestamp = getattr(matlab_frame, 'timestamp', 0.0)
    fhist_frame.pointCloud = getattr(matlab_frame, 'pointCloud', np.empty((5, 0)))
    
    # --- MODIFICATION START: Robustly handle posLocal data ---
    pos_local_data = getattr(matlab_frame, 'posLocal', np.empty((2, 0)))
    
    # This is the crucial fix: ensure we only take the X and Y coordinates (first 2 rows)
    if pos_local_data.ndim > 1 and pos_local_data.shape[0] > 2:
        pos_local_data = pos_local_data[:2, :]
        
    fhist_frame.posLocal = pos_local_data
    # --- MODIFICATION END ---

    # Ensure posLocal is correctly shaped if it's empty or 1D
    if fhist_frame.posLocal.ndim == 1:
        fhist_frame.posLocal = fhist_frame.posLocal.reshape(2, -1)

    # Initialize the 'isOutlier' array with the correct size, which the tracker will populate
    num_points = fhist_frame.posLocal.shape[1]
    fhist_frame.isOutlier = np.zeros(num_points, dtype=bool)
    
    return fhist_frame