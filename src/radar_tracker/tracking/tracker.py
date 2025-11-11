# src/tracking/tracker.py

import numpy as np
import numbers # <-- Import the numbers module for type checking
from ..console_logger import logger
import config

# Import all the necessary components from the tracking module
from .perform_track_assignment_master import perform_track_assignment_master
from .algorithms.estimate_ego_motion import estimate_ego_motion
from .algorithms.classify_vehicle_motion import classify_vehicle_motion
from .algorithms.detect_side_barrier import detect_side_barrier
from .algorithms.my_dbscan import my_dbscan
from .algorithms.detect_and_filter_reflections import detect_and_filter_reflections # <--- ADDED
from .utils.slot_points_to_grid import slot_points_to_grid

class RadarTracker:
    def __init__(self, params):
        """Initializes the tracker's state."""
        self.params = params
        self.all_tracks = []
        self.next_track_id = 1
        self.frame_idx = 0
        self.last_timestamp_ms = 0.0

        # Initialize filter states
        self.ego_kf_state = {
            'x': np.zeros((5, 1)), 'P': np.diag([10.0, 10.0, 5.0, 5.0, 1.0]),
            'Q': np.diag([0.1, 0.1, 0.5, 0.5, 0.2]),
        }
        self.original_ego_kf_r = np.diag([0.2, 5.0, 1.0, 1.0, 0.3])
        self.filtered_vx_ego_iir = 0.0
        self.filtered_vy_ego_iir = 0.0
        self.right_turn_state = {}
        self.left_turn_state = {}
        
        default_x_range = self.params['barrier_detect_params']['default_x_range']
        self.filtered_barrier_x = {'left': default_x_range[0], 'right': default_x_range[1]}

    def process_frame(self, current_frame):
        """
        Processes a single frame of radar data and updates the tracks.
        This contains the logic from the loop in the original tracker's main.py.
        MODIFIED: The 'can_signals' parameter has been removed. The necessary ego
        motion data (like egoVx) is now expected to be pre-populated in the
        'current_frame' object by the data adapter.
        """
        if config.DEBUG_FLAGS.get('log_tracker_entry'):
            logger.debug(f"[TRACKER] Frame {self.frame_idx}: Entry egoVx = {current_frame.egoVx:.2f} m/s")

        # Calculate delta_t
        delta_t = (current_frame.timestamp - self.last_timestamp_ms) / 1000.0 if self.frame_idx > 0 else 0.05
        if delta_t <= 0: delta_t = 0.05
        self.last_timestamp_ms = current_frame.timestamp

        if config.COMPONENT_DEBUG_FLAGS.get('tracker_core'):
            logger.debug(f"[TRACKER_CORE] Processing Frame: {self.frame_idx}, Delta_t: {delta_t:.4f}s")

        # --- CAN and IMU data is now part of current_frame ---
        # Default values are used if not provided by the adapter.
        can_speed = current_frame.correctedEgoSpeed_mps * 3.6 # Convert m/s back to km/h for the function
        
        # --- THIS IS THE FIX (PART 1) ---
        # Read live CAN data from the frame object instead of using np.nan
        can_torque = current_frame.ETS_MOT_ShaftTorque_Est_Nm
        can_gear = current_frame.ETS_VCU_Gear_Engaged_St_enum
        
        # --- THIS IS THE STEP 4 FIX ---
        # Read the road grade from the frame object
        can_grade = current_frame.EstimatedGrade_Est_Deg
        # --- END OF STEP 4 FIX ---

        imu_ax, imu_ay, imu_omega = 0.0, 0.0, 0.0
        
        cartesian_pos_data = current_frame.posLocal
        point_cloud = current_frame.pointCloud
        num_points = cartesian_pos_data.shape[1]

        # --- Pre-processing Block (Motion Classification, Ego-Motion, Barriers) ---
        current_time_s = current_frame.timestamp / 1000.0
        motion_state, self.right_turn_state, self.left_turn_state = classify_vehicle_motion(
            current_time_s, imu_omega,
            self.params['ego_motion_classification_params']['turn_yawRate_thrs'],
            self.params['ego_motion_classification_params']['confirmation_samples'],
            self.right_turn_state, self.left_turn_state
        )
        current_frame.motionState = motion_state
        if config.COMPONENT_DEBUG_FLAGS.get('tracker_core'):
            logger.debug(f"[TRACKER_CORE] Motion State: {motion_state}")

        (self.ego_kf_state, self.filtered_vx_ego_iir, self.filtered_vy_ego_iir,
         ransac_vx, ransac_vy, _, ax_dynamics, outlier_indices) = estimate_ego_motion(
             cartesian_pos_data.T, point_cloud[3, :] if num_points > 0 else np.array([]),
             can_speed, can_torque, can_gear, can_grade, imu_ax, imu_ay, imu_omega,
             np.deg2rad(can_grade), 0.0, self.ego_kf_state,
             self.filtered_vx_ego_iir, self.filtered_vy_ego_iir, delta_t,
             self.params['vehicle_params'], self.params['ego_motion_params'], self.original_ego_kf_r
         )
        
        # --- THIS IS THE FIX (PART 2) ---
        # Save the calculated acceleration back to the frame for logging.
        current_frame.estimatedAcceleration_mps2 = ax_dynamics
        # --- END OF FIX (PART 2) ---

        if outlier_indices.size > 0: current_frame.isOutlier[outlier_indices] = True
        # The egoVx value is now populated from the CAN signal in the data_adapter.
        # The ego-motion estimator uses the CAN speed as a primary input, but we
        # preserve the original CAN value in the final history. We only take the
        # estimated lateral velocity (egoVy) from the filter.
        current_frame.egoVy = self.ego_kf_state['x'][1, 0]
        if config.COMPONENT_DEBUG_FLAGS.get('tracker_core'):
            logger.debug(f"[TRACKER_CORE] EgoVx (CAN-derived): {current_frame.egoVx:.2f}, EgoVy (EKF-derived): {current_frame.egoVy:.2f}")

        all_indices = np.arange(num_points)
        static_inlier_indices = np.setdiff1d(all_indices, outlier_indices, assume_unique=True)
        is_vehicle_moving = np.abs(current_frame.egoVx) > self.params['ego_motion_params']['stationarySpeedThreshold']
        
        static_box = self.params['stationary_cluster_box']
        
        dynamic_box = None
        if static_inlier_indices.size > 0 and is_vehicle_moving and motion_state == 0:
            dynamic_x_range, self.filtered_barrier_x = detect_side_barrier(
                cartesian_pos_data, static_inlier_indices,
                self.params['barrier_detect_params'], self.filtered_barrier_x
            )
            dynamic_box = {
                'X_RANGE': dynamic_x_range,
                'Y_RANGE': self.params['barrier_detect_params']['longitudinal_range']
            }
        
        current_frame.filtered_barrier_x = type('barrier_struct', (object,), self.filtered_barrier_x)()

        # --- Clustering and Filtering ---
        detected_centroids, detected_cluster_info = np.empty((0, 2)), []
        if config.COMPONENT_DEBUG_FLAGS.get('tracker_core'):
            logger.debug(f"[TRACKER_CORE] Number of points for clustering: {num_points}")
        if num_points >= self.params['dbscan_params']['min_pts']:
            grid_map, point_to_grid_idx = slot_points_to_grid(cartesian_pos_data, self.params['grid_config'])
            current_frame.grid_map = grid_map
            
            dbscan_clusters = my_dbscan(cartesian_pos_data.T, point_cloud[3, :],
                                         self.params['dbscan_params']['epsilon_pos'], 
                                         self.params['dbscan_params']['epsilon_vel'], 
                                         self.params['dbscan_params']['min_pts'], 
                                         grid_map, point_to_grid_idx)
            current_frame.dbscanClusters = dbscan_clusters
            unique_ids = np.unique(dbscan_clusters)
            unique_ids = unique_ids[unique_ids > 0]
            if config.COMPONENT_DEBUG_FLAGS.get('tracker_core'):
                logger.debug(f"[TRACKER_CORE] DBSCAN found {len(unique_ids)} unique clusters.")

            if unique_ids.size > 0:
                # --- Refactored Cluster Processing (Restored Two-Loop Structure) ---

                # --- Loop 1: Aggregate all cluster data first ---
                all_cluster_info = []
                for cid in unique_ids:
                    cluster_indices = np.where(dbscan_clusters == cid)[0]
                    centroid = np.mean(cartesian_pos_data[:, cluster_indices], axis=1)
                    mean_radial_speed = np.mean(point_cloud[3, cluster_indices])
                    all_cluster_info.append({
                        'X': centroid[0], 'Y': centroid[1], 'radialSpeed': mean_radial_speed,
                        'originalClusterID': cid
                    })

                # --- Reflection Filtering (operates on all clusters) ---
                cluster_ids_to_remove = detect_and_filter_reflections(
                    grid_map, all_cluster_info, dbscan_clusters, point_cloud,
                    self.params['reflection_detection_params']['speed_similarity_threshold_mps']
                )

                # --- Loop 2: Filter and select final clusters ---
                temp_centroids, temp_cluster_info = [], []
                stationary_speed_threshold = self.params['ego_motion_params']['stationarySpeedThreshold']

                for info in all_cluster_info:
                    if info['originalClusterID'] in cluster_ids_to_remove:
                        continue

                    cluster_indices = np.where(dbscan_clusters == info['originalClusterID'])[0]
                    centroid = np.array([info['X'], info['Y']])
                    
                    if is_vehicle_moving:
                        outlier_ratio = np.sum(current_frame.isOutlier[cluster_indices]) / len(cluster_indices)
                        is_moving_cluster = outlier_ratio > self.params['cluster_filter_params']['min_outlierClusterRatio_thrs']
                    else:
                        is_moving_cluster = abs(info['radialSpeed']) > stationary_speed_threshold

                    if dynamic_box is not None:
                        is_in_dynamic_box = (dynamic_box['X_RANGE'][0] <= centroid[0] <= dynamic_box['X_RANGE'][1]) and \
                                            (dynamic_box['Y_RANGE'][0] <= centroid[1] <= dynamic_box['Y_RANGE'][1])
                        if not is_moving_cluster and is_in_dynamic_box:
                            continue 
                    
                    is_in_static_box = (static_box['X_RANGE'][0] <= centroid[0] <= static_box['X_RANGE'][1]) and \
                                       (static_box['Y_RANGE'][0] <= centroid[1] <= static_box['Y_RANGE'][1])
                    
                    is_stationary_in_box_flag = (not is_moving_cluster) and is_in_static_box
                    
                    azimuth_rad = np.arctan2(centroid[0], centroid[1])
                    temp_centroids.append(centroid)
                    temp_cluster_info.append({
                        'X': centroid[0], 'Y': centroid[1], 'radialSpeed': info['radialSpeed'],
                        'vx': info['radialSpeed'] * np.sin(azimuth_rad), 
                        'vy': info['radialSpeed'] * np.cos(azimuth_rad),
                        'isOutlierCluster': is_moving_cluster,
                        'isStationary_inBox': is_stationary_in_box_flag
                    })

                if temp_centroids:
                    detected_centroids = np.array(temp_centroids)
                    detected_cluster_info = temp_cluster_info


        current_frame.detectedClusterInfo = np.array(detected_cluster_info, dtype=object) if detected_cluster_info else np.array([])
        
        # --- Perform Tracking ---
        if config.COMPONENT_DEBUG_FLAGS.get('tracker_core'):
            logger.debug(f"[TRACKER_CORE] Performing track assignment. Detected centroids: {len(detected_centroids)}, Existing tracks: {len(self.all_tracks)}")
        self.all_tracks, self.next_track_id, _, _ = perform_track_assignment_master(
            self.frame_idx, detected_centroids, detected_cluster_info,
            self.all_tracks, self.next_track_id, delta_t, imu_omega, self.params
        )
        if config.COMPONENT_DEBUG_FLAGS.get('tracker_core'):
            logger.debug(f"[TRACKER_CORE] Track assignment complete. Total tracks: {len(self.all_tracks)}")

        self.frame_idx += 1
        return self.all_tracks, current_frame