# src/live_visualizer.py

from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QApplication
import pyqtgraph as pg
from .console_logger import logger

class LiveVisualizer(QMainWindow):
    """
    This class creates the main window for the real-time visualization.
    It contains a pyqtgraph plot to display the radar's point cloud.
    """
    def __init__(self, worker, worker_thread):
        super().__init__()
        # --- Store references to the worker and its thread ---
        self.worker = worker
        self.worker_thread = worker_thread

        self.setWindowTitle("Unified Radar Tracker - Live View")
        self.setGeometry(100, 100, 1000, 800)

        # --- Main Widget and Layout ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # --- Create the Plot Widget ---
        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)

        # --- Configure Plot Aesthetics ---
        self.plot_widget.setBackground('k')
        self.plot_widget.setTitle("Live Radar Point Cloud", color="w", size="20pt")
        styles = {'color':'w', 'font-size':'15px'}
        self.plot_widget.setLabel('left', 'Y Position (m)', **styles)
        self.plot_widget.setLabel('bottom', 'X Position (m)', **styles)
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setAspectLocked(True)

        # --- Set Initial Axis Ranges ---
        self.plot_widget.setXRange(-40, 40)
        self.plot_widget.setYRange(0, 80)

        # --- Create a Plot Data Item ---
        self.plot_data_item = self.plot_widget.plot(
            [], [], pen=None, symbol='o', symbolSize=5,
            symbolBrush=(255, 255, 255, 150)
        )

    def update_plot(self, frame_data):
        """
        Updates the plot with new point cloud data.
        """
        # --- NEW: Update the title with the current frame number ---
        if self.worker and self.worker.tracker:
            frame_idx = self.worker.tracker.frame_idx
            self.plot_widget.setTitle(f"Live Radar View - Frame: {frame_idx}", color="w", size="20pt")

        if frame_data and frame_data.point_cloud is not None and frame_data.point_cloud.size > 0:
            x_coords = frame_data.point_cloud[1, :]
            y_coords = frame_data.point_cloud[2, :]
            self.plot_data_item.setData(x_coords, y_coords)
        else:
            self.plot_data_item.clear()

    def closeEvent(self, event):
        """
        This method is called when the user closes the window.
        It handles the graceful shutdown of the worker thread.
        """
        logger.info("--- Window closed. Initiating shutdown... ---")
        
        # 1. Signal the worker to stop its loop
        self.worker.stop()
        
        # 2. Tell the QThread to quit its event loop if it's still running
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()
        
        logger.info("--- Shutdown complete. ---")
        event.accept() # Allow the window to close