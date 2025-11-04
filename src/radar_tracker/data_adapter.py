# src/data_adapter.py

import numpy as np
from .console_logger import logger
import config
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

        # --- NEW: Raw CAN signals for JSON export ---
        self.ETS_VCU_VehSpeed_Act_kmph = np.nan
        self.ETS_MOT_ShaftTorque_Est_Nm = np.nan
        self.ETS_VCU_Gear_Engaged_St_enum = np.nan

def adapt_frame_data_to_fhist(frame_data, current_timestamp_ms, can_signals=None):
    """
    Converts a real-time FrameData object into an FHistFrame object
    that the tracking algorithms can process.
    
    MODIFIED: Now accepts a dictionary of interpolated CAN signals to populate
    vehicle motion fields.
    MODIFIED: Now accepts a pre-calculated timestamp for the current frame.
    """
    fhist_frame = FHistFrame()
    fhist_frame.timestamp = current_timestamp_ms

    if frame_data.point_cloud is not None and frame_data.point_cloud.size > 0:
        fhist_frame.pointCloud = frame_data.point_cloud
        fhist_frame.posLocal = frame_data.point_cloud[1:3, :]
    else:
        fhist_frame.pointCloud = np.empty((5, 0))
        fhist_frame.posLocal = np.empty((2, 0))

    fhist_frame.isOutlier = np.zeros(frame_data.num_points, dtype=bool)

    # --- NEW: Populate fhist_frame with live CAN data ---
    if config.DEBUG_FLAGS.get('log_can_data_adapter'):
        logger.debug(f"[ADAPTER] Received CAN signals: {can_signals}")

    if can_signals:
        # Convert vehicle speed from km/h to m/s for the tracker
        speed_kmh = can_signals.get('ETS_VCU_VehSpeed_Act_kmph', 0.0)
        speed_mps = speed_kmh / 3.6
        
        fhist_frame.egoVx = speed_mps
        fhist_frame.correctedEgoSpeed_mps = speed_mps

        # --- NEW: Store raw signals for JSON export ---
        fhist_frame.ETS_VCU_VehSpeed_Act_kmph = speed_kmh
        fhist_frame.ETS_MOT_ShaftTorque_Est_Nm = can_signals.get('ETS_MOT_ShaftTorque_Est_Nm', np.nan)
        fhist_frame.ETS_VCU_Gear_Engaged_St_enum = can_signals.get('ETS_VCU_Gear_Engaged_St_enum', np.nan)
        
        if config.DEBUG_FLAGS.get('log_can_data_adapter'):
            logger.debug(f"[ADAPTER] Populated fhist_frame.egoVx with {speed_mps:.2f} m/s")
            logger.debug(f"[ADAPTER] Stored raw CAN signals: Speed={fhist_frame.ETS_VCU_VehSpeed_Act_kmph}, Torque={fhist_frame.ETS_MOT_ShaftTorque_Est_Nm}, Gear={fhist_frame.ETS_VCU_Gear_Engaged_St_enum}")

        # NOTE: Add other signals like yaw rate ('CAN_YAW_RATE') if the tracker uses them.
        # For now, we are only using vehicle speed.

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