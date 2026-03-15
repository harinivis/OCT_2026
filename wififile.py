
import socket
import struct
import time
import numpy as np

FPGA_IP = "192.168.10.50"
FPGA_PORT = 5000

PC_BIND_IP = "0.0.0.0"      
PC_BIND_PORT = 5000         
SOCKET_TIMEOUT_SEC = 2.0
INTER_PACKET_DELAY_SEC = 0.001  # not entirely sure if packet backlog will 
                                # be an issue. integrate delay for now

ROW_ID = 7

BATCH_SAMPLES = 128
PACKETS_PER_ROW = 4
ROW_SAMPLES = BATCH_SAMPLES * PACKETS_PER_ROW

HEADER_MAGIC= 0xFF
HEADER_DATA = 0xFF
HEADER_CALI = 0xFE

def build_header(row_id: int, batch_id: int) -> bytes:
    
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

    header_word = (HEADER_MAGIC << 24) | (HEADER_DATA << 16) | ((batch_id & 0x3) << 14) | (row_id & 0x3FF)
    return struct.pack("<I", header_word)


def build_payload(samples):
    """
    samples: list of (re, im), length must be 128
    each re/im is int32, serialized little-endian
    """
    if len(samples) != BATCH_SAMPLES:
        raise ValueError(f"payload must contain exactly {BATCH_SAMPLES} complex samples")

    payload = bytearray()
    for re, im in samples:
        payload += struct.pack("<ii", int(re), int(im))
    return bytes(payload)


def build_packet(row_id: int, batch_id: int, samples):
    # stack header with payload data
    return build_header(row_id, batch_id) + build_payload(samples)


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
        re, im = struct.unpack("<ii", payload[i:i+8])
        samples.append((re, im))

    return {
        "row_id": row_id,
        "batch_id": batch_id,
        "samples": samples,
    }


def make_test_row():
    """
    Simple deterministic test pattern.
    Sample k = (re=k, im=-k)
    """
    return [(k, -k) for k in range(ROW_SAMPLES)]


def send_row_and_receive_reply(sock, row_id: int, row_samples):
    if len(row_samples) != ROW_SAMPLES:
        raise ValueError(f"row must contain exactly {ROW_SAMPLES} samples")

    # Send 4 packets: batch 0,1,2,3
    for batch_id in range(PACKETS_PER_ROW):
        start = batch_id * BATCH_SAMPLES
        end = start + BATCH_SAMPLES
        batch_samples = row_samples[start:end]
        pkt = build_packet(row_id, batch_id, batch_samples)

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
    row_samples = make_test_row() # size (512, 2), re and im

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    #sock.bind((PC_BIND_IP, PC_BIND_PORT))

    print(f"Bound PC UDP socket to {PC_BIND_IP}:{PC_BIND_PORT}")
    print(f"Sending to FPGA at {FPGA_IP}:{FPGA_PORT}")

    replies = send_row_and_receive_reply(sock, ROW_ID, row_samples)

    print()
    print(f"Received {len(replies)}/{PACKETS_PER_ROW} reply packets")

    for batch_id in sorted(replies.keys()):
        pkt = replies[batch_id]
        first_two = pkt["samples"][:2]
        print(f"Reply batch {batch_id}: row={pkt['row_id']}, first samples={first_two}")

    if len(replies) != PACKETS_PER_ROW:
        print("\nDid not receive full 4-packet reply.")


if __name__ == "__main__":
    main()