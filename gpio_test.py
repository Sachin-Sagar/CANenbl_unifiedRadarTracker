import RPi.GPIO as GPIO
import time
import threading
from src.can_logger_app.gpio_handler import init_gpio, wait_for_switch_on, check_for_switch_off, cleanup_gpio, turn_on_led, turn_off_led

print("GPIO Test Script for Switch and LED")

if __name__ == '__main__':
    shutdown_flag = threading.Event()
    stop_event = threading.Event()
    try:
        init_gpio()
        print("GPIO initialized. Waiting for switch to be ON...")
        wait_for_switch_on()
        turn_on_led()
        print("Switch is ON. LED is ON. Monitoring for switch OFF...")

        # Start the stop signal checker in a separate thread
        stop_thread = threading.Thread(target=check_for_switch_off, args=(stop_event, shutdown_flag))
        stop_thread.start()

        # Keep the main thread alive until shutdown is signaled
        while not shutdown_flag.is_set():
            time.sleep(0.5)

        print("Shutdown signal received. Turning LED OFF.")
        turn_off_led()

    except KeyboardInterrupt:
        print("Test interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        stop_event.set()
        if 'stop_thread' in locals() and stop_thread.is_alive():
            stop_thread.join(timeout=1)
        print("Cleaning up GPIO.")
        cleanup_gpio()
        print("GPIO test finished.")