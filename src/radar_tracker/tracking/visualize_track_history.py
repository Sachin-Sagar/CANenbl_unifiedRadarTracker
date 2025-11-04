# src/visualize_track_history.py

import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
from matplotlib.patches import Ellipse
from ..console_logger import logger

def load_track_history(filename="track_history.json"):
    """Loads the track history from a JSON file."""
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        logger.info(f"Successfully loaded data from {filename}")
        return data
    except FileNotFoundError:
        logger.error(f"Error: {filename} not found. Please run the main tracking script first.")
        return None
    except Exception as e:
        logger.error(f"Error loading JSON file: {e}")
        return None

def plot_covariance_ellipse(ax, position, radii, angle_deg, color='r'):
    """Plots a covariance ellipse on the given axes."""
    if any(np.isnan(position)) or any(np.isnan(radii)) or np.isnan(angle_deg):
        return
    
    # Matplotlib's Ellipse takes width and height (diameter), not radii
    width = radii[1] * 2  # Major axis
    height = radii[0] * 2 # Minor axis
    
    ellipse = Ellipse(xy=position, width=width, height=height, angle=angle_deg,
                      edgecolor=color, fc='None', lw=1.5, label='95% Confidence Ellipse')
    ax.add_patch(ellipse)


def visualize_track_history():
    # --- 1. Load Data ---
    # We load the JSON file created by update_and_save_history.py
    # Note: The visualizer will need the fHist data as well, which should be saved
    # alongside the tracks. For now, we focus on visualizing the track object.
    track_data = load_track_history()
    if track_data is None:
        return

    all_tracks = track_data # Assuming the JSON root is the list of tracks

    # --- 2. Get User Input for Track ID ---
    available_ids = [track['id'] for track in all_tracks]
    logger.info(f"Available track IDs are: {available_ids}")
    
    try:
        track_id_to_plot = int(input("Enter the track ID you want to visualize: "))
        selected_track = next((t for t in all_tracks if t['id'] == track_id_to_plot), None)
        if selected_track is None:
            logger.error(f"Error: Track ID {track_id_to_plot} not found.")
            return
    except ValueError:
        logger.error("Invalid input. Please enter a number.")
        return

    history_log = selected_track.get('historyLog', [])
    if not history_log:
        logger.error(f"Error: Track ID {track_id_to_plot} has no history log.")
        return

    num_history_points = len(history_log)

    # --- 3. Create Figure and UI Elements ---
    fig, ax = plt.subplots(figsize=(10, 8))
    plt.subplots_adjust(left=0.1, bottom=0.25, right=0.75)

    # Main plot
    ax.set_xlabel("X Position (m)")
    ax.set_ylabel("Y Position (m)")
    ax.set_xlim([-40, 40])
    ax.set_ylim([0, 80])
    ax.set_aspect('equal', adjustable='box')
    ax.grid(True)

    # Info box text area
    info_text = fig.text(0.78, 0.9, 'Track Information', 
                         transform=fig.transFigure, va='top', ha='left',
                         bbox=dict(boxstyle='round,pad=0.5', fc='wheat', alpha=0.5))

    # Slider
    ax_slider = plt.axes([0.1, 0.1, 0.65, 0.03])
    slider = Slider(
        ax=ax_slider,
        label='History Step',
        valmin=0,
        valmax=num_history_points - 1,
        valinit=0,
        valstep=1
    )

    # Pre-extract full trajectory for efficiency
    full_trajectory = np.array([log['correctedPosition'] for log in history_log if 'correctedPosition' in log and log['correctedPosition'] is not None]).reshape(-1, 2)

    # --- 4. Update Function and Initial Plot ---
    def update(val):
        history_idx = int(slider.val)
        log_entry = history_log[history_idx]

        ax.clear()
        ax.set_xlabel("X Position (m)"); ax.set_ylabel("Y Position (m)")
        ax.set_xlim([-40, 40]); ax.set_ylim([0, 80])
        ax.set_aspect('equal', adjustable='box'); ax.grid(True)
        
        # Plot full path
        ax.plot(full_trajectory[:, 0], full_trajectory[:, 1], '-', color='gray', linewidth=1, label='Full Path')
        
        # Plot current trajectory
        current_trajectory = full_trajectory[:history_idx+1]
        ax.plot(current_trajectory[:, 0], current_trajectory[:, 1], '-b', linewidth=2, label='Current Trajectory')

        # Plot predicted and corrected positions
        pred_pos = log_entry.get('predictedPosition')
        if pred_pos and not any(np.isnan(pred_pos)):
            ax.plot(pred_pos[0], pred_pos[1], 'rx', markersize=10, mew=1.5, label='Predicted Position')

        corr_pos = log_entry.get('correctedPosition')
        if corr_pos and not any(np.isnan(corr_pos)):
            ax.plot(corr_pos[0], corr_pos[1], 'go', markersize=8, label='Corrected Position')

        # Plot covariance ellipse
        if log_entry.get('ellipseRadii') and log_entry.get('orientationAngle'):
            plot_covariance_ellipse(ax, corr_pos, log_entry['ellipseRadii'], log_entry['orientationAngle'])
        
        ax.legend(loc='upper left')
        ax.set_title(f"Track ID: {track_id_to_plot} / Frame: {log_entry['frameIdx']}")

        # Update info text box
        info_str = f"History Step: {history_idx+1}/{num_history_points}\n"
        info_str += f"Frame Index: {log_entry['frameIdx']}\n"
        info_str += "--- State ---\n"
        info_str += f"Pos (Pred): [{pred_pos[0]:.2f}, {pred_pos[1]:.2f}] m\n"
        info_str += f"Pos (Corr): [{corr_pos[0]:.2f}, {corr_pos[1]:.2f}] m\n"
        info_str += "--- IMM Probs ---\n"
        probs = log_entry.get('modelProbabilities', [np.nan, np.nan, np.nan])
        info_str += f"  CV: {probs[0]:.3f}\n"
        info_str += f"  CT: {probs[1]:.3f}\n"
        info_str += f"  CA: {probs[2]:.3f}\n"
        
        info_text.set_text(info_str)
        fig.canvas.draw_idle()

    slider.on_changed(update)
    update(0) # Initial plot
    plt.show()


if __name__ == '__main__':
    visualize_track_history()