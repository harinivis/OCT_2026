%%FINAL Forward OCT MATLAB Process
clear variables
clc

%OCT Pipeline
% Step 1: Load the OCT data

%files = dir('forward_pipeline_outputs_optimized*.mat'); %get the mat files in the 1 folder it is located in
files = dir('raw_signals_optimal*.bin');

for i = 1:length(files)
    filename = files(i).name;
    [~,~,ext] = fileparts(filename);  % check if mat or bin file

    if strcmp(ext, '.mat') %if its a matfile
        octData = load(filename);
        bscan_data_real = real(octData.raw_signals);
        

        % get dimensions
        [num_ascans, num_depth] = size(bscan_data_real);  % e.g., 768 x 1024
        signal_length = num_depth;

        %calib data
        tvec = octData.tvec;
        kclk = octData.kclk;
        mybg = octData.mybg;
        maxmin = octData.maxmin;
        a_coeffs = octData.a_coeffs;
    
    elseif strcmp(ext, '.bin') %if bin file
        fid = fopen(filename,'rb');

     

        % specify the dimensions of your data (must match how the bin was saved)
        num_ascans = 768;   % e.g., number of A-lines
        num_depth  = 1024;  % e.g., points per A-line
        signal_length = num_depth;

        % read raw data   
        raw = fread(fid, 'int32'); 
        fclose(fid);

        % reshape into [num_ascans x num_depth]
         bscan_data_real = reshape(raw, num_ascans, num_depth);  
        num_depth = size(bscan_data_real, 2);
           


       
        calibData = load('calibration_data.mat', 'tvec', 'kclk', 'mybg', 'maxmin', 'a_coeffs');

       
        tvec    = calibData.tvec;
        kclk    = calibData.kclk;
        mybg    = calibData.mybg;
        maxmin  = calibData.maxmin;
        a_coeffs = calibData.a_coeffs;


    else
        error('boi get the right file types');
    end




%% OCT PARAMETERS


half_depth = floor(signal_length / 2); %remove half the depth
b_recon = (zeros(num_ascans, half_depth));
% mybg = zeros(signal_length,1);
% mybg = 100000 * sin(tvec * 0.003);
    
    % FORWARD PIPELINE (reconstruct) %IF USING PARFOR, U CANNOT USE i as
    % INDEX ITS LITERALLY A RULE
    tic
    parfor j = 1:num_ascans %(i = 1:768)
        raw = bscan_data_real(j, :); %(i, :) is going through every A scan and getting all its data points being 512
        %raw = hilbert(bscan_data_real(i,:)); %used to reconstruct a complex signal from real interferrograms (used to get a complex analytical signal)
        s1 = bg_sub_f(raw);               % Remove background
        s2 = k_lin_f(s1, tvec, kclk);           % Linearize k-space
        %s2 = k_lin_f(s1, kclk);
        s3 = disp_c_f(s2, maxmin, a_coeffs);   % Correct dispersion
        s4 = fft_f(s3);                         % FFT to spatial domain
        s4 = s4(1:floor(end/2)); 
        
      
        s5 = log_sc_f(s4);                      % Log scale magnitude
        s6 = gs_map_f (s5);
        b_recon(j, :) = s6;
        
    
    end
    
toc
 
     % Display 
    figure;
    %imagesc(20*log10(abs(b_recon +  1e-12)))
    % threshold = 1e-80;                  % values below this are considered background
    % b_recon(abs(b_recon) < threshold) = 0;
    %b_recon_smooth = imgaussfilt(abs(b_recon), 0.2); % sigma = 1
    imagesc(abs(b_recon).')

    axis image
    colormap(gray)
    title('Final B scan')

     
end
toc

    %Functions used
    
    % Background subtraction
    function output = bg_sub_f(input)
        output = input - mean(input);
    end
    
    % function output = bg_sub_f(input, bg)
    %     output = input - bg;
    % end
    
    % Dispersion compensation
    function output = disp_c_f(input, maxmin, a_coeffs)
        % Forward: Remove dispersion (multiply by opposite phase)
        N = length(input);
        lambda = linspace(maxmin(1), maxmin(2), N);
        k = 2*pi ./ lambda;
        k0 = mean(k);
        phi = a_coeffs(2)*(k-k0).^2 + a_coeffs(3)*(k-k0).^3;
        output = input .* exp(-1i * phi);
    
    
    end
    
    %send cosine of phi and sin and phi
    
    
    
    % k linearization
    function output = k_lin_f(nonlinear_y, linear_x, nonlinear_x)
        % Forward: Map from nonlinear k-clock to linear k-space
         % assert(length(nonlinear_y) == length(nonlinear_x), ...
         %     'k_lin_f: signal and source grid must match');
        output = interp1(nonlinear_x, nonlinear_y, linear_x, 'pchip');

    end
    % function output = k_lin_f(signal, kclk)
    % k_linear = linspace(min(kclk), max(kclk), length(kclk));
    % output = interp1(kclk, signal, k_linear, 'linear', 0);
    % end
    % 
    % FFT
    
function output = fft_f(input)
    output = fft(input);
end

    % 
    % function output = fft_f(input)
    %     % Forward: FFT to spatial domain
    % 
    % 
    % % FFT
    % 
    % output = fft(input);
    % %output = abs(output);
    % 
    % %output  = fft(temp);
    % 
    % end
    % 
    
    % lOG Scaling
    function output = log_sc_f(input)
        % Forward: Convert magnitude to dB scale
        % Input: complex data from FFT
        % Output: real dB magnitude (magnitude domain)
        %epsv = 1e-12;   
        output = 20*log10(abs(input ));
    end
    
    
    % Grey scale mapping
    function output = gs_map_f(input)
     min_val = min(input);
        max_val = max(input);
    
        output = ((input - min_val) / (max_val - min_val)) *255;
        
      
    %Quantized_Log_Ref = ((A_Scan_DB - globalMin)/ (globalMax-globalMin)).*255; %a bit of 8 bits corresponds to 256 possible values. Modelling an OCT signal acquired by an 8 bit analog to digital converter makes the signal values
       
    end
    

    
 