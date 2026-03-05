import scipy.io  # libray to inport .mat files in python
import socket
import numpy as np # so we can convert to ints
import struct


# load the data
#r treats backslashes literally
mat_data = scipy.io.loadmat(r"C:\Users\Harin\OneDrive\Capstone\forward_pipeline_outputs.mat")  # does #octData = load("C:\Users\Harin\OneDrive\Capstone\768_synthetic_interferograms_bij.mat", 'interferograms');
bscan_data = mat_data['raw_signals']      # does interferograms = octData.interferograms;
num_scans, num_samples = bscan_data.shape #768 a lines, 512 samples in each a line
# Take real part only (matlab does this automatically apparently)
real_data = bscan_data.real

print(real_data)


# Find max absolute value
max_val = np.max(np.abs(real_data))

# Check for NaN
print("Number of NaNs:", np.isnan(real_data).sum())
# Check for Inf
print("Number of Infs:", np.isinf(real_data).sum())


import sys
print(sys.byteorder)
# Convert to int32 
#data_bytes = bscan_data.real.astype(np.int32)
data_bytes = real_data.astype(np.int32) #does data_bytes = typecast(interferograms, 'int32');
print(data_bytes)


#Open UDP port
FPGA_IP = "192.168.10.10"  # replace with FPGA IP
FPGA_PORT = 5000           # UDP port FPGA is listening to


# https://realpython.com/python-sockets/
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
# The arguments passed to socket() are constants used to specify the address family and socket type.
# AF_INET is the Internet address family for IPv4. SOCK_STREAM is the socket type for TCP (it is SOCK_DGRAM FOR UDP!!!), the protocol that will be used to transport messages in the network.
#sending the scans
for i in range(num_scans):
    scan = data_bytes[i, :]  # go through each A scan up to 768 and go though all data points (512) in each a scan 

    # Build packet
    header = 4095 
    message_type = 0  # 0 = data %To say this is data packet or a calibration packet (0 for data, 1 for calib) int8 = holds 1 byte which is 0 - 255
    scan_number = i + 1  # MATLAB 1-based index 
    number_of_samples = len(scan) # does NumberofSamples = int16(length(scan)); 
    Data = scan
    close_marker = 32767

    # Packet structure
    # 'h' = int16, 'b' = int8, 'i' = int32 boi what da hell is this ugliness
    basic_packet = struct.pack(
        '>hbhh',  # Big endian is > but change to < for little endian
        header,
        message_type,
        scan_number,
        number_of_samples
    )

    # Pack scan data as int32 https://realpython.com/python-sockets/
    #import struct
#   network_byteorder_int = struct.pack(">H", 256) --> this packs the number 256
    data_packet = struct.pack('>' + 'i' * number_of_samples, *scan) # big endian, do one a scan at a time multiplied by 512, and, *scan does scan[0], scan[1], scan[2], so it packs all 512 scans 

    # Pack close marker
    close_packet = struct.pack('>h', close_marker)

    # Final packet = header + data + close
    full_packet = basic_packet + data_packet + close_packet 

    # Send packet
    sock.sendto(full_packet, (FPGA_IP, FPGA_PORT))
    print(f"Sent scan {i + 1}/{num_scans}")
 

#  calibration packet
header = 4095
message_type = 1  # calibration packet
disp_coeff = [0, -4 * 10^-11, 0]
message_length = len(disp_coeff)
close_marker = 32767

# Pack calibration packet
calibration_packet = struct.pack( '>hh', header, message_type) + struct.pack('>h', message_length) + struct.pack('>fff', *disp_coeff) + struct.pack('>h', close_marker)

sock.sendto(calibration_packet, (FPGA_IP, FPGA_PORT))
print("Calibration packet sent")



# background calibration packet
