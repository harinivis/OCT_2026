import scipy.io  # libray to inport .mat files in python
import socket
import struct
import time
import numpy as np # so we can convert to ints
import glob


'''
num_scans, num_samples = real_data.shape
print('real data shape is:')
print(real_data.shape)

print('combined bytes is:')
print(combined_bytes)

'''

#Open UDP port
FPGA_IP = "192.168.10.50" # replace with FPGA IP
FPGA_PORT = 5001 # UDP port FPGA is listening to

PC_BIND_IP = "0.0.0.0"      
PC_BIND_PORT = 5001         
SOCKET_TIMEOUT_SEC = 2.0
INTER_PACKET_DELAY_SEC = 0.001  # not entirely sure if packet backlog will 
                                # be an issue. integrate delay for now

#ROW_ID = 7

BATCH_SAMPLES = 256 #change to 256
PACKETS_PER_ROW = 4
ROW_SAMPLES = BATCH_SAMPLES * PACKETS_PER_ROW #i.e 512 --> now is 1024

HEADER_MAGIC= 0xFF
HEADER_DATA = 0xFF
HEADER_CALI = 0xFE

def build_header(row_id: int, batch_id: int, msg_type: int) -> bytes:
    
    # Header word:
    #   [31:24] = Header Magic 0xFF
    #   [23:16] = Message Type [0xFF, 0xFE]
    #   [15:14] = batch_id
    #   [13:10] = 0
    #   [9:0]   = row_id

    # Wire order is LSB-first, so pack as little-endian uint32.

    if not (0 <= row_id < 1024): # change to max number of rows
        raise ValueError("row_id must be 0..1023")
    if not (0 <= batch_id < 4):
        raise ValueError("batch_id must be 0..3")
    

    if msg_type not in (HEADER_DATA, HEADER_CALI):
        raise ValueError("Invalid message type")

    header_word = (HEADER_MAGIC << 24) | (msg_type << 16) | ((batch_id & 0x3) << 14) | (row_id & 0x3FF)
    return struct.pack("<I", header_word)


def build_payload(samples):
    """
    samples: list of (re, im), length must be 128
    each re/im is int32, serialized little-endian
    """
    if len(samples) != BATCH_SAMPLES:
        raise ValueError(f"payload must contain exactly {BATCH_SAMPLES} complex samples")

    payload = bytearray()
    for re in samples:
        payload += struct.pack("<i", int(re)) #remove imag
    return bytes(payload)


def build_packet(row_id: int, batch_id: int, msg_type: int, samples):
    # stack header with payload data
    return build_header(row_id, batch_id, msg_type) + build_payload(samples)


def parse_packet(pkt: bytes):
    """
    Parse one returned FPGA packet.
    Returns: dict with row_id, batch_id, samples
    """
    if len(pkt) != 4 + 1024:
        raise ValueError(f"expected 1028 bytes, got {len(pkt)}")

    header_word = struct.unpack("<I", pkt[:4])[0]

    magic_hi = (header_word >> 24) & 0xFF
    magic_lo = (header_word >> 16) & 0xFF
    batch_id = (header_word >> 14) & 0x3
    row_id = header_word & 0x3FF

    if magic_hi != 0xFF or magic_lo != 0xFF:
        raise ValueError(f"bad header magic: {magic_hi:02X} {magic_lo:02X}")

    samples = []
    payload = pkt[4:]
    for i in range(0, len(payload), 8):
        re = struct.unpack("<i", payload[i:i+4])[0] #before we had  re, im = struct.unpack("<ii", payload[i:i+8]), 8 is for 8 bytes, cuz i =32 bit, and real and imag is 32 bits each so 4 x 2 = 8
        samples.append((re))

    return {
        "row_id": row_id,
        "batch_id": batch_id,
        "samples": samples,
    }

'''
def make_test_row():
    """
    Simple deterministic test pattern.
    Sample k = (re=k, im=-k)
    """
    return [(k, -k) for k in range(ROW_SAMPLES)]

'''

def send_row_and_receive_reply(sock, row_id: int, row_samples):
    if len(row_samples) != ROW_SAMPLES: #ensures the row passed 512 samples only 
        raise ValueError(f"row must contain exactly {ROW_SAMPLES} samples")

    # Send 4 packets: batch 0,1,2,3
    for batch_id in range(PACKETS_PER_ROW): #batch id is are we on first, second, third, etc batch
        start = batch_id * BATCH_SAMPLES
        end = start + BATCH_SAMPLES
        batch_samples = row_samples[start:end] #batch 1 would be 0:128, batch 2 would be 128:256, batch 3 would be 384:511
        pkt = build_packet(row_id, batch_id, HEADER_CALI, batch_samples)

        print(f"Sending row={row_id}, batch={batch_id}, bytes={len(pkt)}")
        sock.sendto(pkt, (FPGA_IP, FPGA_PORT))
        time.sleep(INTER_PACKET_DELAY_SEC)

    # Receive 4 reply packets
    replies = {}
    deadline = time.time() + SOCKET_TIMEOUT_SEC

    while len(replies) < PACKETS_PER_ROW and time.time() < deadline:
        remaining = max(0.01, deadline - time.time())
        sock.settimeout(remaining)

        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            break

        print(f"Received {len(data)} bytes from {addr}")
        try:
            parsed = parse_packet(data)
        except Exception as e:
            print(f"  Ignoring malformed packet: {e}")
            continue

        if parsed["row_id"] != row_id:
            print(f"  Ignoring packet for unexpected row_id={parsed['row_id']}")
            continue

        replies[parsed["batch_id"]] = parsed
        print(f"  Accepted reply row={parsed['row_id']} batch={parsed['batch_id']}")

    return replies


def main():
    
    
    #OPEN THe UDP Socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # The arguments passed to socket() are constants used to specify the address family and socket type.
    # AF_INET is the Internet address family for IPv4. SOCK_STREAM is the socket type for TCP (it is SOCK_DGRAM FOR UDP!!!), the protocol that will be used to transport messages in the network.

    #load the calibraion data and convert to int32 AND SEND BEFORE SENDING ACTUAL DATA FILES


    # Load mat file
    calib_data = scipy.io.loadmat(r"C:\Users\Harin\OneDrive\Capstone\calibration_data.mat")
    print(calib_data.keys())
    bg_row = calib_data['mybg'].astype(np.int32)  # shape (1, 1024)

    # Load dymmy mat file
    calib_dummy = scipy.io.loadmat(r"C:\Users\Harin\OneDrive\Capstone\calibration_dummy.mat")
    print(calib_dummy.keys())
    k_rows = calib_dummy['k'].astype(np.int32)     # shape (5, 1024)
    disp_rows = calib_dummy['disp'].astype(np.int32) # shape (2, 1024)

    # Combine rows
    calibration_rows = np.vstack([bg_row, k_rows, disp_rows])  # (8, 1024)

    #cuz we want specfific row ids 
    calib_row_ids = [0] + list(range(24,29))+ [20, 21]
    
    for row_samples, row_id in zip (calibration_rows, calib_row_ids):
        row_samples = row_samples.astype(np.int32)  #just in case lmao
        replies = send_row_and_receive_reply(sock, row_id, row_samples)
        print(f"Sent calibration row {row_id}, received {len(replies)}/{PACKETS_PER_ROW} packets")


    # load the data
    #r treats backslashes literally
    files = sorted(glob.glob(r"C:\Users\Harin\OneDrive\Capstone\raw_signals_optimal*.bin"))
    
       
       
    #sock.bind((PC_BIND_IP, PC_BIND_PORT)) # OSError: [WinError 10048] Only one usage of each socket address (protocol/network address/port) is normally permitted


    print("Files found:", files)
    for file in files:
        print("File opened", file)

        # read raw data
        real_data = np.fromfile(file, dtype="<i4")  # int32 little-endian

    # split into rows of ROW_SAMPLES
        rows = real_data.reshape(768, 1024)

    #  #FOR THIS FILE, SEND EACH ROW IN THE BATCHES 
        for row_id, row_samples in enumerate(rows):
            row_samples = row_samples.astype(np.int32) #just making sure its acc int32 
            replies = send_row_and_receive_reply(sock, row_id, row_samples)
            print()
            print(f"Received {len(replies)}/{PACKETS_PER_ROW} reply packets")
            print()

    

        #print(data_bytes + data_complex_bytes)
        #doing shape (A scans, num of samples, 2) --> to get them in pairs as (real and imaginary)
        #combined_bytes = np.stack((data_bytes, data_complex_bytes), axis = -1) #use axis = -1 to add another dimension so u can do pairs per element https://numpy.org/doc/stable/reference/generated/numpy.stack.html
        #get number of scans
   
        #num_scans = real_data.shape[0] #get the first dimension of the combined bytes data which is number of rows or A scans we have which is 768 
        num_scans = 768
        print(type(num_scans))
        print(num_scans)

        
   

            
    print(f"Bound PC UDP socket to {PC_BIND_IP}:{PC_BIND_PORT}")
    print(f"Sending to FPGA at {FPGA_IP}:{FPGA_PORT}")


    for batch_id in sorted(replies.keys()):
            pkt = replies[batch_id]
            first_two = pkt["samples"][:2]
            print(f"Reply batch {batch_id}: row={pkt['row_id']}, first samples={first_two}")


    if len(replies) != PACKETS_PER_ROW:
            print("\nDid not receive full 4-packet reply.")


if __name__ == "__main__":
        main()



        # 5 sample
        #base tells you where to start lo

        #4 coeff 1 base
        #512 by 32 bit 5 of those tables 



    # 2 x 512 dispersionn