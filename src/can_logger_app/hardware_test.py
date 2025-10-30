import can

def main():
    """
    Lists available python-can interfaces and channels.
    """
    print("--- CAN Hardware Test ---")
    print("Searching for available CAN interfaces...")

    try:
        configs = can.detect_available_configs()
        if not configs:
            print("No CAN interfaces found.")
        else:
            for config in configs:
                print(f"Interface: {config['interface']}, Channel: {config['channel']}")
    except Exception as e:
        print(f"An error occurred while searching for interfaces: {e}")

if __name__ == "__main__":
    main()