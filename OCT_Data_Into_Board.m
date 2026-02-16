%% loop code: to send the actual interferogram data


%Load/convert and initalize
%octData = load("C:\Users\Harin\OneDrive\Capstone\synthetic_interferograms.mat", 'interferograms');
octData = load("C:\Users\Harin\OneDrive\Capstone\768_synthetic_interferograms_bij.mat", 'interferograms');
interferograms = octData.interferograms;
data_bytes = typecast(interferograms, 'int32');

% Send to FPGA IP address and port
fpga_ip = "###.###.#.##";  % FPGA IP 
fpga_port = 5000;           % UDP port the FPGA is listening on



for i = 1:768
    scan = data_bytes(i,:); %go through all samples in each row (each A scan)

    %make the DATA packet
    header = int16(4095); %start marker to say "this is the start of a packet"
    Message_Type = int8(0); %To say this is data packet or a calibration packet (0 for data, 1 for calib) int8 = holds 1 byte which is 0 - 255
    ScanNumber = int16(i); %1st A-scan? 2nd A-scan? etc
    NumberofSamples = int16(length(scan)); %should ve 512 samples per A scan (the number of samples for that A scan)
    Data = (scan); %the actual interferrogram data
    Close = int16(32767);
    
    %Packet structure
    Data_packet = [header, Message_Type, ScanNumber, NumberofSamples, Data, Close]; 

  %sending the DATA packet via ethernet
  write(u, Data_packet, fpga_ip, fpga_port);

  % Display a message indicating the completion of the current scan
   disp(['Scan ', num2str(i), ' yaaas']);

end


%% make the CALIBRATION packet for dispersion compensation (these stay constant for all the A scans so send it once and have the fpga store it)

    header = int16(4095); %start marker to say "this is the start of a packet"
    Message_Type = int8(1); %To say this is data packet or a calibration packet (0 for data, 1 for calib) int8 = holds 1 byte which is 0 - 255
    a1 = int16(0);
    a2 = int16(0.001);
    a3 = int16(0.003);
    Close = int16(32767);

    DispCoeff = [a1,a2,a3];
    MessageLength = int16(length(DispCoeff));
    %Packet structure
    Calibration_packet = [header, Message_Type, MessageLength, DispCoeff, Close]; 

  %sending the CALIBRATION packet via ethernet
  write(u, Calibration_packet, fpga_ip, fpga_port);

  % Display a message indicating the completion of the current scan
  disp("Packet sent to FPGA");


  %% make the CALIBRATION packet for background subtraction (this should change per each scan so we need to send it via a loop?)