import serial
import serial.tools.list_ports
from ..console_logger import logger

# Define the 8-byte sync pattern for frame synchronization
SYNC_PATTERN = b'\x02\x01\x04\x03\x06\x05\x08\x07'

def configure_control_port(com_port_num, baud_rate):
    """
    Configures and opens the control serial port with a standard terminator.
    This version is compatible with both Windows (numbers) and Linux (strings).

    Args:
        com_port_num (int or str): The COM port number (e.g., 11) or device path (e.g., '/dev/ttyACM1').
        baud_rate (int): The initial baud rate for communication.

    Returns:
        serial.Serial or None: A pySerial object if successful, otherwise None.
    """
    # --- BUG FIX: Check the type of the port identifier ---
    # If it's an integer, assume Windows and prepend "COM".
    # If it's a string, assume Linux/macOS and use it directly.
    if isinstance(com_port_num, int):
        com_port_string = f'COM{com_port_num}'
    else:
        com_port_string = com_port_num

    try:
        # List available ports and check if the desired port exists
        available_ports = [p.device for p in serial.tools.list_ports.comports()]
        if com_port_string not in available_ports:
            logger.error(f'\nERROR: CONTROL port {com_port_string} is NOT in the list of available ports.')
            logger.info(f'Available ports are: {available_ports}')
            return None

        # Create and open the serial port object
        sphandle = serial.Serial(
            com_port_string,
            baud_rate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0 # Set a timeout for read operations
        )
        logger.info(f'--- Opened serial port {com_port_string} at {baud_rate} baud. ---')
        return sphandle
    except serial.SerialException as e:
        logger.error(f'ERROR: Failed to open serial port {com_port_string}: {e}')
        return None

def reconfigure_port_for_data(sphandle):
    """
    Reconfigures an open serial port for continuous data streaming.
    """
    if sphandle and sphandle.is_open:
        sphandle.reset_input_buffer()
        sphandle.reset_output_buffer()
        logger.info('--- Port configured for data mode (binary streaming). ---')
    return sphandle

def read_frame_header(h_data_serial_port, frame_header_length_bytes):
    """
    Reads from the serial port until a complete frame header is found.
    """
    out_of_sync_bytes = 0
    
    while True:
        try:
            byte = h_data_serial_port.read(1)
            if not byte:
                logger.warning("Timeout occurred while reading from serial port.")
                return None, 0, out_of_sync_bytes
        except serial.SerialException as e:
            logger.error(f"Serial port read failed: {e}")
            return None, 0, out_of_sync_bytes

        if byte == SYNC_PATTERN[0:1]:
            remaining_pattern = h_data_serial_port.read(7)
            
            if len(remaining_pattern) < 7:
                out_of_sync_bytes += 1 + len(remaining_pattern)
                continue

            full_pattern = byte + remaining_pattern
            if full_pattern == SYNC_PATTERN:
                header_rest_len = frame_header_length_bytes - len(SYNC_PATTERN)
                header_rest = h_data_serial_port.read(header_rest_len)

                if len(header_rest) == header_rest_len:
                    rx_header = full_pattern + header_rest
                    return rx_header, frame_header_length_bytes, out_of_sync_bytes
                else:
                    out_of_sync_bytes += len(SYNC_PATTERN) + len(header_rest)
                    continue
            else:
                out_of_sync_bytes += 1
                continue
        else:
            out_of_sync_bytes += 1