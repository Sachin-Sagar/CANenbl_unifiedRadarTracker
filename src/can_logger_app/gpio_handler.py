
import RPi.GPIO as GPIO
import time
from config import BUTTON_PIN

def init_gpio():
    """Initializes GPIO pins for button."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def wait_for_switch_on():
    """Waits for the switch to be turned on (pin low)."""
    print("Waiting for switch ON...")
    while GPIO.input(BUTTON_PIN) == GPIO.HIGH:
        time.sleep(0.1)
    print("Switch is ON!")
    time.sleep(0.2)  # Debounce

def turn_on_led():
    """Turns the onboard LED on continuously."""
    led_path = "/sys/class/leds/led0/brightness"
    try:
        with open(led_path, 'w') as f:
            f.write("1")
            f.flush()
    except IOError:
        print("Could not control onboard LED. Are you running as root?")

def turn_off_led():
    """Turns the onboard LED off."""
    led_path = "/sys/class/leds/led0/brightness"
    try:
        with open(led_path, 'w') as f:
            f.write("0")
            f.flush()
    except IOError:
        print("Could not control onboard LED. Are you running as root?")

def blink_onboard_led(n=3, delay=0.2):
    """Blinks the onboard LED n times."""
    led_path = "/sys/class/leds/led0/brightness"
    try:
        with open(led_path, 'w') as f:
            for _ in range(n):
                f.write("1")
                f.flush()
                time.sleep(delay)
                f.write("0")
                f.flush()
                time.sleep(delay)
    except IOError:
        print("Could not control onboard LED. Are you running as root?")

def check_for_switch_off(shutdown_flag):
    """Detects when the switch is turned off (pin high) to signal shutdown."""
    while not shutdown_flag.is_set():
        if GPIO.input(BUTTON_PIN) == GPIO.HIGH:
            print("Switch is OFF! Stopping...")
            shutdown_flag.set()
            break
        time.sleep(0.1)

def cleanup_gpio():
    """Cleans up GPIO resources."""
    GPIO.cleanup()
