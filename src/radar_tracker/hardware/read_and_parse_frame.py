import struct
import numpy as np

# MODIFICATION: Changed local imports to be relative
from . import hw_comms_utils
from . import parsing_utils

# --- TLV Type Constants ---
# As defined in read_and_parse_frame.m
MMWDEMO_OUTPUT_EXT_MSG_DETECTED_POINTS = 301
MMWDEMO_OUTPUT_EXT_MSG_STATS = 306
MMWDEMO_OUTPUT_EXT_MSG_TARGET_LIST_2D_BSD = 1035

# --- Structure Definitions ---
# These dictionaries define the binary format of the headers and data payloads.
# Format: { 'field_name': ('struct_format_char', num_bytes) }

FRAME_HEADER_STRUCT = {
    'sync': ('Q', 8),           # uint64
    'version': ('I', 4),        # uint32
    'packetLength': ('I', 4),   # uint32
    'platform': ('I', 4),       # uint32
    'frameNumber': ('I', 4),    # uint32
    'uartOverflow': ('I', 4),   # uint32
    'numDetectObject': ('I', 4),# uint32
    'numTLVs': ('I', 4),        # uint32
    'procOverflow': ('I', 4),   # uint32
}

TLV_HEADER_STRUCT = {
    'type': ('I', 4),           # uint32
    'length': ('I', 4)          # uint32
}

# Point cloud TLV structures
POINT_UNIT_STRUCT = {
    'xyzUnit': ('f', 4),        # single
    'dopplerUnit': ('f', 4),    # single
    'snrUnit': ('f', 4),        # single
    'noiseUnit': ('f', 4),      # single
    'numDetPointsMajor': ('H', 2), # uint16
    'numDetPointsMinor': ('H', 2)  # uint16
}

POINT_STRUCT_CARTESIAN = {
    'x': ('h', 2),              # int16
    'y': ('h', 2),              # int16
    'z': ('h', 2),              # int16
    'doppler': ('h', 2),        # int16
    'snr': ('B', 1),            # uint8
    'noise': ('B', 1)           # uint8
}

# Statistics TLV structures
STATS_TIMING_STRUCT = {
    'interFrameProcessingTime': ('I', 4), # uint32
    'transmitOutputTime': ('I', 4)        # uint32
}
STATS_POWER_STRUCT = {
    'p1v8': ('H', 2), 'p3v3': ('H', 2),
    'p1v2': ('H', 2), 'p1v2rf': ('H', 2)
}
STATS_TEMP_STRUCT = {
    'rx': ('h', 2), 'tx': ('h', 2),
    'pm': ('h', 2), 'dig': ('h', 2)
}


class FrameData:
    """A class to hold the parsed data for a single frame."""
    def __init__(self):
        self.header = {}
        self.point_cloud = np.array([])
        self.num_points = 0
        self.target_list = {}
        self.num_targets = 0
        self.stats_info = {}

def read_and_parse_frame(h_data_port, params):
    """
    Reads and parses one complete data frame from the UART stream.

    Args:
        h_data_port (serial.Serial): The open serial port for data.
        params (RadarParams): The parsed radar configuration parameters.

    Returns:
        FrameData or None: A FrameData object with parsed info, or None on failure.
    """
    frame_header_length = parsing_utils.get_byte_length_from_struct(FRAME_HEADER_STRUCT)
    tlv_header_length = parsing_utils.get_byte_length_from_struct(TLV_HEADER_STRUCT)

    # --- Read Frame Header and Payload ---
    rx_header_bytes, byte_count, _ = hw_comms_utils.read_frame_header(h_data_port, frame_header_length)
    if not rx_header_bytes or byte_count != frame_header_length:
        print("Warning: Incomplete header received.")
        return None

    frame_header = parsing_utils.read_to_struct(rx_header_bytes, FRAME_HEADER_STRUCT)
    if not frame_header:
        print("Warning: Could not parse frame header.")
        return None
        
    data_length = frame_header['packetLength'] - frame_header_length
    
    # Read the rest of the frame (the payload)
    if data_length > 0:
        payload_bytes = h_data_port.read(data_length)
        if len(payload_bytes) != data_length:
            print("Warning: Incomplete payload received.")
            return None
    else:
        payload_bytes = b''

    frame_data = FrameData()
    frame_data.header = frame_header
    
    # --- Parse TLV Data from Payload ---
    offset = 0
    # --- MODIFIED: Changed loop to get index 'i' for debug message ---
    for i in range(frame_header['numTLVs']):
        if offset + tlv_header_length > data_length:
            print("Warning: Not enough data for TLV header.")
            break
        
        # Read TLV header
        tlv_header = parsing_utils.read_to_struct(
            payload_bytes[offset : offset + tlv_header_length], TLV_HEADER_STRUCT
        )
        value_length = tlv_header['length']
        tlv_type = tlv_header['type']

        # --- NEW: Added debug message for TLV header ---
        #print(f"[DEBUG] Found TLV #{i+1} of {frame_header['numTLVs']}: Type={tlv_type}, Length={value_length} bytes, at offset={offset}")

        # --- CRITICAL FIX ---
        # The total length of the TLV is the value_length + the header length.
        # The parser must advance its offset by this total amount.
        total_tlv_length = value_length + tlv_header_length
        if offset + total_tlv_length > data_length:
            print(f"Warning: TLV (type {tlv_type}) length error. Stated length exceeds buffer.")
            break

        value_offset = offset + tlv_header_length
        value_bytes = payload_bytes[value_offset : value_offset + value_length]

        # --- Handle TLVs based on type ---
        if tlv_type == MMWDEMO_OUTPUT_EXT_MSG_DETECTED_POINTS:
            parse_point_cloud_tlv(frame_data, value_bytes, params)

        elif tlv_type == MMWDEMO_OUTPUT_EXT_MSG_STATS:
            parse_stats_tlv(frame_data, value_bytes)

        elif tlv_type == MMWDEMO_OUTPUT_EXT_MSG_TARGET_LIST_2D_BSD:
            parse_target_list_tlv(frame_data, value_bytes)

        # Advance to the next TLV
        offset += total_tlv_length
        
    return frame_data


def parse_point_cloud_tlv(frame_data, value_bytes, params):
    """Parses the point cloud TLV."""
    point_unit_len = parsing_utils.get_byte_length_from_struct(POINT_UNIT_STRUCT)
    point_len = parsing_utils.get_byte_length_from_struct(POINT_STRUCT_CARTESIAN)

    point_unit = parsing_utils.read_to_struct(value_bytes[:point_unit_len], POINT_UNIT_STRUCT)
    num_input_points = (len(value_bytes) - point_unit_len) // point_len
    frame_data.num_points = num_input_points

    # --- NEW: Added debug message for point cloud data ---
    #print(f"[DEBUG] Point Cloud TLV: Found {num_input_points} detected points.")

    if num_input_points > 0:
        points_offset = point_unit_len
        # Create a numpy structured array for efficiency
        dt = np.dtype([('x', 'i2'), ('y', 'i2'), ('z', 'i2'), 
                       ('doppler', 'i2'), ('snr', 'u1'), ('noise', 'u1')])
        
        point_cloud_data = np.frombuffer(
            value_bytes, dtype=dt, count=num_input_points, offset=points_offset
        )
        
        # Scale the raw data to get metric units
        x = point_unit['xyzUnit'] * point_cloud_data['x']
        y = point_unit['xyzUnit'] * point_cloud_data['y']
        z = point_unit['xyzUnit'] * point_cloud_data['z']
        doppler = point_unit['dopplerUnit'] * point_cloud_data['doppler']
        snr = point_unit['snrUnit'] * point_cloud_data['snr']
        
        range_val = np.sqrt(x**2 + y**2 + z**2)
        
        # Store as a (5, N) numpy array: [range, azimuth, elevation, doppler, snr]
        # Note: Azimuth/Elevation calculation is simplified here. The original MATLAB
        # code contains a more complex calculation that can be ported if needed.
        frame_data.point_cloud = np.vstack((range_val, x, y, doppler, snr))


def parse_stats_tlv(frame_data, value_bytes):
    """Parses the statistics TLV."""
    timing_len = parsing_utils.get_byte_length_from_struct(STATS_TIMING_STRUCT)
    power_len = parsing_utils.get_byte_length_from_struct(STATS_POWER_STRUCT)
    temp_len = parsing_utils.get_byte_length_from_struct(STATS_TEMP_STRUCT)
    
    offset = 0
    frame_data.stats_info['timing'] = parsing_utils.read_to_struct(
        value_bytes[offset : offset + timing_len], STATS_TIMING_STRUCT
    )
    offset += timing_len
    
    power_data = parsing_utils.read_to_struct(
        value_bytes[offset : offset + power_len], STATS_POWER_STRUCT
    )
    frame_data.stats_info['power'] = power_data
    offset += power_len
    
    frame_data.stats_info['temperature'] = parsing_utils.read_to_struct(
        value_bytes[offset : offset + temp_len], STATS_TEMP_STRUCT
    )
    # --- NEW: Added debug message for stats data ---
    #print(f"[DEBUG] Stats TLV: Parsed timing, power, and temperature info.")


def parse_target_list_tlv(frame_data, value_bytes):
    """Parses the target list (tracker) TLV."""
    target_length_in_bytes = 72  # As specified in read_and_parse_frame.m
    num_targets = len(value_bytes) // target_length_in_bytes
    frame_data.num_targets = num_targets
    
    # --- NEW: Added debug message for target list data ---
    #print(f"[DEBUG] Target List TLV: Found {num_targets} targets.")

    if num_targets > 0:
        targets = {
            'TID': np.zeros(num_targets, dtype='u4'),
            'S': np.zeros((6, num_targets), dtype='f4'),
            'EC': np.zeros((9, num_targets), dtype='f4'),
            'G': np.zeros(num_targets, dtype='f4'),
            'Conf': np.zeros(num_targets, dtype='f4'),
            'tPos': np.zeros((2, num_targets), dtype='f4')
        }
        offset = 0
        for i in range(num_targets):
            # Unpack each field for the current target
            targets['TID'][i] = struct.unpack('<I', value_bytes[offset : offset+4])[0]
            offset += 4
            targets['S'][:, i] = struct.unpack('<6f', value_bytes[offset : offset+24])
            offset += 24
            targets['EC'][:, i] = struct.unpack('<9f', value_bytes[offset : offset+36])
            offset += 36
            targets['G'][i] = struct.unpack('<f', value_bytes[offset : offset+4])[0]
            offset += 4
            targets['Conf'][i] = struct.unpack('<f', value_bytes[offset : offset+4])[0]
            offset += 4
            
            # Extract 2D position
            targets['tPos'][:, i] = targets['S'][0:2, i]

        frame_data.target_list = targets