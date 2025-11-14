# **NOTE: This document describes the initial plan for merging the radar tracker and CAN logger projects. The plan was later modified. The `can_logger_app` directory contains the final, active code for the CAN logger, and the `src/can_service` directory is deprecated and contains outdated code.**

1. Project Goal

We aim to combine your two projects: the unified-radar-tracker (which processes radar data) and the read_can_rt_strip (which logs CAN bus data). The final, merged project, CAN_enbl_unifiedRadarTracker, will enhance the radar tracker's live mode. It will run the CAN logger's logic in the background to read live CAN signals, decode them using your VCU.dbc file and master_sigList.txt, and then feed this real-time vehicle data directly into the radar tracker's processing function. This replaces the placeholder data previously used in the live radar mode.

2. Core Architectural Challenge & Solution

    The Challenge: Your radar tracker's live mode uses PyQt's threading (QThread), suitable for GUI updates. Your CAN logger uses Python's multiprocessing to achieve high performance and avoid data loss by utilizing multiple CPU cores. These two approaches (threading vs. multiprocessing) don't mix easily within the same part of an application.

    The Solution: We'll transform the CAN logger from a standalone program into a background data service.

        We'll create a new LiveCANManager component. This manager will run as a separate process, controlled by the main radar application.

        The LiveCANManager will be responsible for starting and managing the original CAN logger's key parts: the CANReader (which reads from the hardware) and the pool of processing_workers (which decode the data).

        We'll modify the processing_workers. Instead of writing decoded signals to a file, they will send the data (timestamp, signal name, value) to a special shared queue managed by the LiveCANManager.

        The LiveCANManager will have its own internal buffer-filler thread. This thread's job is to read from the shared queue and keep a shared dictionary updated with the latest few values and timestamps for each CAN signal (acting like a small, accessible history buffer).

        The radar tracker's main RadarWorker (running in the QThread) will start this LiveCANManager service when the application launches.

        During its main loop, the RadarWorker will read the latest signal histories from the shared dictionary, interpolate the values to match the exact timestamp of the incoming radar frame, and then pass this live, synchronized CAN data into the tracker's processing function.

3. Phase 1: Project Scaffolding (File Setup)

First, let's organize the files for the new combined project.

    Create Directories: Make the main project folder CAN_enbl_unifiedRadarTracker. Inside it, create an src folder.

    Copy & Rename Packages:

        Copy the contents of the original unified-radar-tracker/src folder into a new folder named src/radar_tracker.

        Copy the Python files from the original read_can_rt_strip project into a temporary holding folder, src/can_logger_app.

    Create New can_service Package: Make a new, empty folder called src/can_service.

    Populate can_service: Copy the essential CAN handling Python files (can_handler.py, data_processor.py, utils.py) from the temporary src/can_logger_app folder into the new src/can_service folder.

    Organize Configuration:

        Copy the configs directory (containing the radar profile .cfg file) from the radar tracker project into the new project's root.

        Copy the config.py file (containing CAN hardware settings) from the CAN logger project into the new project's root.

        Copy the input directory (containing VCU.dbc and master_sigList.txt ) from the CAN logger project into the new project's root.

    Enable Imports: Create empty __init__.py files inside src, src/radar_tracker, and src/can_service. These files tell Python to treat these folders as importable packages.

    Create Root main.py: Create an empty main.py file in the project's root. This will be the final application launcher.

    Merge Dependencies: Create a requirements.txt file in the project's root. List all the Python libraries needed by both original projects (found in their respective requirements.txt and pyproject.toml files).

4. Phase 2: Refactor can_logger into can_service

This is the core refactoring work, turning the file-writing logger into a data provider.

Task 2.1: Create the LiveCANManager Component

Create a new Python file: src/can_service/live_can_manager.py. Define the LiveCANManager class within it.

This class needs to:

    Use Python's multiprocessing.Manager to create data structures (queues, dictionaries, lists) that can be safely shared between the main radar process and the CAN service process.

    Set up the shared output queue where worker processes will send decoded data.

    Set up the shared data buffer dictionary (e.g., mapping signal names to lists of recent (timestamp, value) pairs).

    Implement the buffer-filler thread logic: continuously read from the output queue and update the shared dictionary, keeping only the latest N entries per signal.

    Have start() and stop() methods:

        start(): Connects to the CAN hardware, starts the CANReader thread, starts the pool of processing_worker processes, and starts the internal buffer-filler thread.

        stop(): Coordinates the graceful shutdown of all threads and processes.

    Have a get_signal_buffers() method: Allows the radar tracker to request a safe copy of the current contents of the shared data buffer dictionary.

Task 2.2: Modify the processing_worker

Adapt the data_processor.py file you copied into src/can_service.

    Adjust Function Arguments: The worker function will no longer receive arguments related to shared memory arrays or index queues. It will receive the new shared output queue from the LiveCANManager.

    Modify Output Logic: After decoding a signal, instead of packing it into binary format for shared memory, the worker will simply put a tuple (timestamp, signal_name, value) into the shared output queue.

5. Phase 3: Integrate can_service into radar_tracker

Now, connect the newly created can_service to the radar tracker's live mode.

Task 3.1: Add Interpolation Helper

Make the CAN data interpolation function (found in the original main_playback.py ) reusable.

    Copy this function.

    Place it in a utility file within the radar tracker package, such as src/radar_tracker/utils.py.

Task 3.2: Modify the RadarWorker

Update the RadarWorker class in src/radar_tracker/main_live.py:

    Initialization (__init__):

        Import the LiveCANManager.

        Create an instance of LiveCANManager, passing necessary configuration paths (DBC file, signal list, CAN settings from the root config.py).

    Start-up (run method, beginning):

        Call the can_manager.start() method to launch the CAN service process.

    Main Loop (inside run):

        After receiving a radar frame, get the current time (as a POSIX timestamp).

        Call can_manager.get_signal_buffers() to fetch the latest CAN data histories.

        Create a new helper method (e.g., _interpolate_can_data) within RadarWorker. This method will take the signal buffers and the radar timestamp, use the interp_with_extrap function, and return a dictionary of interpolated CAN values valid for that specific radar timestamp.

        Call this interpolation method.

        Pass the resulting dictionary of live, interpolated CAN data to the tracker.process_frame() method.

    Shutdown (stop method):

        Add a call to can_manager.stop() to ensure the CAN service shuts down cleanly when the GUI window is closed.

    Update Imports: Change all imports within main_live.py to use relative syntax (e.g., from .hardware import ...) because it now resides within the radar_tracker package.

6. Phase 4: Create Final Entry Point

Establish the main script to launch the combined application.

Task 4.1: Write the Root main.py

Edit the main.py file in the project's root directory.

    Set Python Path: Add code to automatically find the src directory and add it to Python's import path (sys.path). This makes radar_tracker and can_service importable.

    Import Main Components: After setting the path, import the main function from src.radar_tracker.main and the setup_logging function from src.radar_tracker.console_logger.

    Configure Logging: Call setup_logging() once here to initialize the application-wide logger.

    Launch: Call the imported main function from the radar tracker to start the application.

Task 4.2: Modify src/radar_tracker/main.py

Update the radar tracker's original entry point script (now located at src/radar_tracker/main.py ).

    Use Relative Imports: Change its imports for main_live, main_playback, and console_logger to use relative syntax (e.g., from .main_live import ...).

    (Optional but Recommended): Remove the setup_logging() call from within this file, as logging is now handled by the root main.py.