import math
import struct
from dataclasses import dataclass, field, fields

# --- UNMISSABLE SCRIPT EXECUTION CHECK ---
# If you do not see this message in your terminal, you are NOT running this version of the file.
print("\n" + "#"*60)
print("### EXECUTING ROBUST PARSING SCRIPT - PYTHON 3.10 COMPATIBLE ###")
print("#"*60 + "\n")


@dataclass
class ProfileCfg:
    startFreq: float = 0.0
    idleTime: list = field(default_factory=lambda: [0.0, 0.0])
    rampEndTime: float = 0.0
    freqSlopeConst: float = 0.0
    numAdcSamples: int = 0
    digOutSampleRate: float = 0.0

@dataclass
class DataPath:
    numTxAnt: int = 0
    numRxAnt: int = 0
    numChirpsPerFrame: int = 0
    numDopplerChirps: int = 0
    numDopplerBins: int = 0
    numRangeBins: int = 0
    numValidRangeBins: int = 0

@dataclass
class FrameCfg:
    numOfChirpsInBurst: int = 0
    numOfBurstsInFrame: int = 0
    numLoops: int = 0
    chirpStartIdx: int = 0
    chirpEndIdx: int = 0
    framePeriodicity: float = 0.0

@dataclass
class RadarParams:
    profileCfg: ProfileCfg = field(default_factory=ProfileCfg)
    dataPath: DataPath = field(default_factory=DataPath)
    frameCfg: FrameCfg = field(default_factory=FrameCfg)
    channelCfg: dict = field(default_factory=dict)
    chirpComnCfg: dict = field(default_factory=dict)

def read_cfg(filename):
    """Reads a radar configuration file."""
    config = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                if line.strip() and not line.strip().startswith('%'):
                    config.append(line.strip())
    except FileNotFoundError:
        print(f'ERROR: File {filename} not found!')
        return []
    return config

def parse_cfg(cli_cfg):
    """Parses the config commands into a structured RadarParams object."""
    params = RadarParams()
    
    # --- Step 1: Parse raw values from the .cfg file ---
    for line in cli_cfg:
        parts = line.split()
        command = parts[0]
        
        if command == 'channelCfg':
            params.channelCfg['txChannelEn'] = int(parts[2])
            params.dataPath.numTxAnt = int(bin(params.channelCfg['txChannelEn']).count('1'))
        
        elif command == 'frameCfg':
            params.frameCfg.numOfChirpsInBurst = int(parts[1])
            params.frameCfg.numOfBurstsInFrame = int(parts[4])

    # --- Step 2: Perform all derived calculations with EXTREME type safety ---
    try:
        print("[DEBUG] Starting derived parameter calculation...")

        # --- Calculation for numLoops ---
        num_tx_ant_int = int(params.dataPath.numTxAnt)
        num_chirps_burst_int = int(params.frameCfg.numOfChirpsInBurst)
        num_bursts_frame_int = int(params.frameCfg.numOfBurstsInFrame)

        if num_tx_ant_int > 0:
            num_loops_float = (num_chirps_burst_int * num_bursts_frame_int) / num_tx_ant_int
            num_loops_int = int(num_loops_float)
        else:
            num_loops_int = 0
        params.frameCfg.numLoops = num_loops_int
        print(f"[DEBUG]   - numLoops calculated as: {num_loops_int} (type: {type(num_loops_int)})")

        # --- Calculation for numChirpsPerFrame ---
        chirp_end_idx = num_tx_ant_int - 1
        num_chirps_per_frame_int = int((chirp_end_idx - 0 + 1) * num_loops_int)
        params.dataPath.numChirpsPerFrame = num_chirps_per_frame_int
        print(f"[DEBUG]   - numChirpsPerFrame calculated as: {num_chirps_per_frame_int} (type: {type(num_chirps_per_frame_int)})")
        
        # --- Calculation for numDopplerChirps ---
        if num_tx_ant_int > 0:
            num_doppler_chirps_int = num_chirps_per_frame_int // num_tx_ant_int
        else:
            num_doppler_chirps_int = 0
        params.dataPath.numDopplerChirps = num_doppler_chirps_int
        print(f"[DEBUG]   - numDopplerChirps calculated as: {num_doppler_chirps_int} (type: {type(num_doppler_chirps_int)})")
        
        # --- THE FAILING OPERATION ---
        print("[DEBUG] About to perform the bit_length operation...")
        
        # Explicitly cast the operand to int again, just to be 100% certain.
        operand = int(params.dataPath.numDopplerChirps) - 1
        
        print(f"[DEBUG]   - Operand for bit_length: {operand} (type: {type(operand)})")
        params.dataPath.numDopplerBins = 1 << operand.bit_length()
        
        print("\n[SUCCESS] Parameter parsing and calculation completed without error.")

    except Exception as e:
        print("\n[FATAL ERROR] An exception occurred during parameter calculation:")
        print(f"  - Error Type: {type(e)}")
        print(f"  - Error Message: {e}")
        # Re-raise the exception to show the original traceback
        raise
    return params

# (Helper functions can remain as they are)
def get_byte_length_from_struct(struct_def):
    return sum(item[1] for item in struct_def.values())

def read_to_struct(byte_array, struct_def):
    result = {}
    format_string = '<' + ''.join(item[0] for item in struct_def.values())
    try:
        unpacked_data = struct.unpack(format_string, byte_array)
        for i, field_name in enumerate(struct_def.keys()):
            result[field_name] = unpacked_data[i]
    except struct.error as e:
        print(f"ERROR: Failed to unpack byte array. {e}")
        return None
    return result