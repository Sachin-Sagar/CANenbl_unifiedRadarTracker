import sys
from .console_logger import setup_logging

def main(output_dir, shutdown_flag=None):
    """
    Main entry point for the Unified Radar Tracker application.
    Allows the user to select between live tracking and playback mode.
    """
    print("--- Welcome to the Unified Radar Tracker ---")
    
    while True:
        mode = input("Select mode: (1) Live Tracking or (2) Playback from File\nEnter choice (1 or 2): ")
        if mode in ['1', '2']:
            break
        else:
            print("Invalid choice. Please enter 1 or 2.")

    if mode == '1':
        print("\nStarting in LIVE mode...")
        # We import here to avoid PyQt5 dependency if only running playback
        from .main_live import main as main_live
        main_live(output_dir, shutdown_flag)
    elif mode == '2':
        print("\nStarting in PLAYBACK mode...")
        from .main_playback import run_playback
        run_playback(output_dir)

if __name__ == '__main__':
    # This is now handled by the root main.py
    # setup_logging()
    main()
