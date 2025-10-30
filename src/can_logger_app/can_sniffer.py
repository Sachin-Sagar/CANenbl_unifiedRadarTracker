# can_sniffer.py
# A minimal script to diagnose message reception issues with python-can.

import can
import time
import platform

# --- Automatically configure the CAN interface based on the OS ---
# We assume a PCAN adapter is being used.

CAN_BITRATE = 500000
OS_SYSTEM = platform.system()

if OS_SYSTEM == "Windows":
    CAN_INTERFACE = "pcan"
    CAN_CHANNEL = "PCAN_USBBUS1"
elif OS_SYSTEM == "Linux":
    CAN_INTERFACE = "socketcan"
    CAN_CHANNEL = "can0"
else:
    print(f"Warning: Unsupported OS '{OS_SYSTEM}'. Defaulting to 'kvaser'.")
    CAN_INTERFACE = "kvaser"
    CAN_CHANNEL = 0
# ----------------------------------------------------------------

def main():
    """Connects to the CAN bus and prints every message received."""
    
    print("--- CAN Bus Sniffer ---")
    print(f"Attempting to connect to {CAN_INTERFACE} channel {CAN_CHANNEL} at {CAN_BITRATE} bps...")
    
    bus = None
    # --- Performance Tracking Variables ---
    total_recv_time = 0
    total_print_time = 0
    msg_count = 0
    start_time = 0
    # ------------------------------------

    try:
        bus = can.interface.Bus(
            interface=CAN_INTERFACE,
            channel=CAN_CHANNEL,
            bitrate=CAN_BITRATE,
            receive_own_messages=False
        )
        
        print("Connection successful. Listening for messages...")
        print("Press Ctrl+C to stop.")
        
        start_time = time.time()
        
        while True:
            # --- Time the bus.recv() call ---
            recv_start = time.perf_counter()
            msg = bus.recv(timeout=1.0)
            recv_end = time.perf_counter()
            total_recv_time += (recv_end - recv_start)
            # ---------------------------------
            
            if msg:
                msg_count += 1
                
                # --- Time the print operation ---
                print_start = time.perf_counter()
                print(f"Received: ID=0x{msg.arbitration_id:03x} ({msg.arbitration_id:4d}) | Timestamp={msg.timestamp:.4f}")
                print_end = time.perf_counter()
                total_print_time += (print_end - print_start)
                # --------------------------------
            else:
                print(" -> No messages received in the last second.")

    except can.CanError as e:
        print(f"Error connecting to or reading from CAN bus: {e}")
    except KeyboardInterrupt:
        print("\n\n--- Sniffer stopped ---")
    finally:
        if bus:
            bus.shutdown()
        
        end_time = time.time()
        duration = end_time - start_time
        if duration > 0 and msg_count > 0:
            rate = msg_count / duration
            print(f"\nReceived {msg_count} messages in {duration:.2f} seconds ({rate:.2f} msg/s).")

            # --- Performance Report ---
            avg_recv = (total_recv_time / msg_count) * 1_000_000 # to microseconds
            avg_print = (total_print_time / msg_count) * 1_000_000 # to microseconds
            print("\n--- Performance Report ---")
            print(f"Avg. Receive Time: {avg_recv:.2f} µs/msg")
            print(f"Avg. Print Time  : {avg_print:.2f} µs/msg")
            print("--------------------------")


if __name__ == "__main__":
    main()
