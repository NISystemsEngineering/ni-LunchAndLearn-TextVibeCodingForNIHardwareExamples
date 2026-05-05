function sine_daq_gui()
% SINE_DAQ_GUI  Sine wave generation + acquisition GUI for NI USB-6453
%
% Requirements:
%   - MATLAB R2026a
%   - Data Acquisition Toolbox 26.1 with NI-DAQmx 26.3.0
%   - Device: NI USB-6453 (default device name: MIODAQ1)
%
% Usage:
%   Run this function from the MATLAB Command Window:
%       sine_daq_gui()
%
% Log file location:
%   By default, errors are logged to 'daq_error_log.txt' in the current
%   working directory. To change the path, modify the LOG_FILE constant
%   near the top of buildGUI() (search for "LOG_FILE =").

    % ------------------------------------------------------------------ %
    %  Build GUI and hand off control to callbacks                         %
    % ------------------------------------------------------------------ %
    buildGUI();
end


% ======================================================================= %
%  GUI CONSTRUCTION                                                         %
% ======================================================================= %
function buildGUI()

    % ---- Log file path (change this string to redirect error logging) -- %
    LOG_FILE = 'daq_error_log.txt';   % <-- CHANGE THIS PATH IF NEEDED

    % ------------------------------------------------------------------ %
    %  Main figure                                                         %
    % ------------------------------------------------------------------ %
    hFig = figure( ...
        'Name',           'DAQ Sine Wave Generator & Acquisition', ...
        'NumberTitle',    'off', ...
        'Resize',         'on', ...
        'Units',          'pixels', ...
        'Position',       [80 60 1200 780], ...
        'CloseRequestFcn', @onClose, ...
        'Color',          [0.15 0.15 0.18]);

    % ------------------------------------------------------------------ %
    %  Shared application state stored in guidata                          %
    % ------------------------------------------------------------------ %
    s.hFig      = hFig;
    s.logFile   = LOG_FILE;
    s.daqSess   = [];       % daq session handle (daqSession object)
    s.running   = false;    % acquisition running flag
    s.stopReq   = false;    % stop requested by user
    s.timeData  = [];       % accumulated time vector
    s.voltData  = [];       % accumulated voltage vector

    % ================================================================== %
    %  LAYOUT – left panel (controls) + right panel (plot)                %
    % ================================================================== %

    % --- Colours & fonts ---
    clrPanel  = [0.18 0.18 0.22];
    clrCard   = [0.22 0.22 0.28];
    clrAccent = [0.20 0.60 1.00];
    clrStart  = [0.18 0.72 0.44];
    clrStop   = [0.90 0.32 0.32];
    clrText   = [0.92 0.92 0.95];
    clrLabel  = [0.60 0.65 0.75];
    fontMain  = 'Segoe UI';
    fontMono  = 'Consolas';

    % --- Left panel (controls) ---
    hLeft = uipanel( ...
        'Parent',          hFig, ...
        'Units',           'normalized', ...
        'Position',        [0 0 0.28 1], ...
        'BackgroundColor', clrPanel, ...
        'BorderType',      'none');

    % --- Right panel (plot) ---
    hRight = uipanel( ...
        'Parent',          hFig, ...
        'Units',           'normalized', ...
        'Position',        [0.28 0 0.72 1], ...
        'BackgroundColor', clrPanel, ...
        'BorderType',      'none');

    % ================================================================== %
    %  LEFT PANEL – parameter fields                                       %
    % ================================================================== %

    % Title
    uicontrol('Parent', hLeft, 'Style', 'text', ...
        'Units', 'normalized', 'Position', [0.04 0.93 0.92 0.05], ...
        'String', 'DAQ Configuration', ...
        'FontName', fontMain, 'FontSize', 14, 'FontWeight', 'bold', ...
        'ForegroundColor', clrAccent, 'BackgroundColor', clrPanel, ...
        'HorizontalAlignment', 'left');

    % Helper to make a labelled edit field
    %   row positions run top-to-bottom (yN to y0 in normalised coords)
    paramDefs = { ...
        'Device Name',    'MIODAQ1',  'deviceName'; ...
        'Output Channel', 'ao0',      'outChan';    ...
        'Input Channel',  'ai0',      'inChan';     ...
        'Frequency (Hz)', '1000',     'freq';       ...
        'Amplitude (Vpp)','1',        'amp';        ...
        'Sample Rate (Hz)','10000',   'sampleRate'; ...
        'Duration (s)',   '0.1',      'duration';   ...
    };

    nP    = size(paramDefs,1);
    yTop  = 0.88;
    yStep = 0.10;

    s.fields = struct();
    for k = 1:nP
        label   = paramDefs{k,1};
        defVal  = paramDefs{k,2};
        tag     = paramDefs{k,3};
        yPos    = yTop - (k-1)*yStep;

        % Label
        uicontrol('Parent', hLeft, 'Style', 'text', ...
            'Units', 'normalized', ...
            'Position', [0.05 yPos+0.025 0.90 0.025], ...
            'String', label, ...
            'FontName', fontMain, 'FontSize', 9, ...
            'ForegroundColor', clrLabel, 'BackgroundColor', clrPanel, ...
            'HorizontalAlignment', 'left');

        % Edit box
        hEdit = uicontrol('Parent', hLeft, 'Style', 'edit', ...
            'Units', 'normalized', ...
            'Position', [0.05 yPos 0.90 0.030], ...
            'String', defVal, ...
            'FontName', fontMono, 'FontSize', 10, ...
            'ForegroundColor', clrText, ...
            'BackgroundColor', clrCard, ...
            'HorizontalAlignment', 'left');

        s.fields.(tag) = hEdit;
    end

    % ---- Separator line ----
    sepY = yTop - nP*yStep + 0.02;
    uicontrol('Parent', hLeft, 'Style', 'text', ...
        'Units', 'normalized', 'Position', [0.04 sepY 0.92 0.003], ...
        'BackgroundColor', clrAccent);

    % ---- Plot selector checkboxes ----
    uicontrol('Parent', hLeft, 'Style', 'text', ...
        'Units', 'normalized', 'Position', [0.05 sepY-0.04 0.90 0.030], ...
        'String', 'Plot Display', ...
        'FontName', fontMain, 'FontSize', 11, 'FontWeight', 'bold', ...
        'ForegroundColor', clrAccent, 'BackgroundColor', clrPanel, ...
        'HorizontalAlignment', 'left');

    s.chkLive = uicontrol('Parent', hLeft, 'Style', 'checkbox', ...
        'Units', 'normalized', 'Position', [0.05 sepY-0.08 0.90 0.030], ...
        'String', 'Live / Acquired Signal', 'Value', 1, ...
        'FontName', fontMain, 'FontSize', 9, ...
        'ForegroundColor', clrText, 'BackgroundColor', clrPanel, ...
        'Callback', @onCheckboxChange);

    s.chkExpected = uicontrol('Parent', hLeft, 'Style', 'checkbox', ...
        'Units', 'normalized', 'Position', [0.05 sepY-0.115 0.90 0.030], ...
        'String', 'Expected Sine Wave', 'Value', 1, ...
        'FontName', fontMain, 'FontSize', 9, ...
        'ForegroundColor', clrText, 'BackgroundColor', clrPanel, ...
        'Callback', @onCheckboxChange);

    % ---- Zoom tool label ----
    uicontrol('Parent', hLeft, 'Style', 'text', ...
        'Units', 'normalized', 'Position', [0.05 sepY-0.165 0.90 0.030], ...
        'String', 'Zoom Tool', ...
        'FontName', fontMain, 'FontSize', 11, 'FontWeight', 'bold', ...
        'ForegroundColor', clrAccent, 'BackgroundColor', clrPanel, ...
        'HorizontalAlignment', 'left');

    uicontrol('Parent', hLeft, 'Style', 'text', ...
        'Units', 'normalized', 'Position', [0.05 sepY-0.205 0.45 0.025], ...
        'String', 'T start (s)', ...
        'FontName', fontMain, 'FontSize', 9, ...
        'ForegroundColor', clrLabel, 'BackgroundColor', clrPanel, ...
        'HorizontalAlignment', 'left');

    uicontrol('Parent', hLeft, 'Style', 'text', ...
        'Units', 'normalized', 'Position', [0.53 sepY-0.205 0.42 0.025], ...
        'String', 'T end (s)', ...
        'FontName', fontMain, 'FontSize', 9, ...
        'ForegroundColor', clrLabel, 'BackgroundColor', clrPanel, ...
        'HorizontalAlignment', 'left');

    s.zoomStart = uicontrol('Parent', hLeft, 'Style', 'edit', ...
        'Units', 'normalized', 'Position', [0.05 sepY-0.235 0.42 0.030], ...
        'String', '', ...
        'FontName', fontMono, 'FontSize', 9, ...
        'ForegroundColor', clrText, 'BackgroundColor', clrCard, ...
        'HorizontalAlignment', 'left', ...
        'TooltipString', 'Leave blank for auto');

    s.zoomEnd = uicontrol('Parent', hLeft, 'Style', 'edit', ...
        'Units', 'normalized', 'Position', [0.53 sepY-0.235 0.42 0.030], ...
        'String', '', ...
        'FontName', fontMono, 'FontSize', 9, ...
        'ForegroundColor', clrText, 'BackgroundColor', clrCard, ...
        'HorizontalAlignment', 'left', ...
        'TooltipString', 'Leave blank for auto');

    uicontrol('Parent', hLeft, 'Style', 'pushbutton', ...
        'Units', 'normalized', 'Position', [0.05 sepY-0.275 0.90 0.033], ...
        'String', 'Apply Zoom', ...
        'FontName', fontMain, 'FontSize', 9, 'FontWeight', 'bold', ...
        'ForegroundColor', clrText, 'BackgroundColor', [0.30 0.30 0.38], ...
        'Callback', @onApplyZoom);

    uicontrol('Parent', hLeft, 'Style', 'pushbutton', ...
        'Units', 'normalized', 'Position', [0.05 sepY-0.315 0.90 0.033], ...
        'String', 'Reset Zoom', ...
        'FontName', fontMain, 'FontSize', 9, ...
        'ForegroundColor', clrLabel, 'BackgroundColor', [0.22 0.22 0.28], ...
        'Callback', @onResetZoom);

    % ---- Start / Stop buttons ----
    s.btnStart = uicontrol('Parent', hLeft, 'Style', 'pushbutton', ...
        'Units', 'normalized', 'Position', [0.05 0.095 0.90 0.055], ...
        'String', '▶  START', ...
        'FontName', fontMain, 'FontSize', 12, 'FontWeight', 'bold', ...
        'ForegroundColor', [1 1 1], 'BackgroundColor', clrStart, ...
        'Callback', @onStart);

    s.btnStop = uicontrol('Parent', hLeft, 'Style', 'pushbutton', ...
        'Units', 'normalized', 'Position', [0.05 0.030 0.90 0.055], ...
        'String', '■  STOP', ...
        'FontName', fontMain, 'FontSize', 12, 'FontWeight', 'bold', ...
        'ForegroundColor', [1 1 1], 'BackgroundColor', clrStop, ...
        'Enable', 'off', ...
        'Callback', @onStop);

    % ================================================================== %
    %  RIGHT PANEL – axes + status bar                                     %
    % ================================================================== %

    s.hAxes = axes( ...
        'Parent',          hRight, ...
        'Units',           'normalized', ...
        'Position',        [0.08 0.12 0.88 0.82], ...
        'Color',           [0.10 0.10 0.13], ...
        'XColor',          clrLabel, ...
        'YColor',          clrLabel, ...
        'GridColor',       [0.30 0.30 0.38], ...
        'GridAlpha',       0.5, ...
        'XGrid',           'on', ...
        'YGrid',           'on', ...
        'FontName',        fontMain, ...
        'FontSize',        9);

    xlabel(s.hAxes, 'Time (s)', 'Color', clrText, 'FontSize', 10);
    ylabel(s.hAxes, 'Voltage (V)', 'Color', clrText, 'FontSize', 10);
    title(s.hAxes,  'Waiting for acquisition…', ...
          'Color', clrAccent, 'FontSize', 11, 'FontWeight', 'bold');

    % Initialise empty line handles
    hold(s.hAxes, 'on');
    s.hLineLive     = plot(s.hAxes, NaN, NaN, '-', ...
        'Color', [0.20 0.75 1.00], 'LineWidth', 1.2, ...
        'DisplayName', 'Acquired');
    s.hLineExpected = plot(s.hAxes, NaN, NaN, '--', ...
        'Color', [1.00 0.65 0.15], 'LineWidth', 1.2, ...
        'DisplayName', 'Expected');
    legend(s.hAxes, 'Location', 'northeast', ...
           'TextColor', clrText, 'Color', clrCard);

    % Status bar
    s.hStatus = uicontrol('Parent', hRight, 'Style', 'text', ...
        'Units', 'normalized', 'Position', [0.02 0.01 0.96 0.06], ...
        'String', 'Ready. Configure parameters and press START.', ...
        'FontName', fontMain, 'FontSize', 9, ...
        'ForegroundColor', clrText, 'BackgroundColor', clrCard, ...
        'HorizontalAlignment', 'left');

    % Store state
    guidata(hFig, s);


    % ================================================================== %
    %  NESTED CALLBACK FUNCTIONS                                           %
    % ================================================================== %

    % ------------------------------------------------------------------
    function onStart(~, ~)
        s = guidata(hFig);
        if s.running
            return;
        end

        % Read parameters from GUI fields
        try
            p = readParams(s);
        catch ME
            setStatus(s, ['Parameter error: ' ME.message], 'warn');
            return;
        end

        % Reset accumulated data
        s.timeData = [];
        s.voltData = [];
        s.stopReq  = false;
        s.running  = true;

        % Disable Start, enable Stop
        set(s.btnStart, 'Enable', 'off');
        set(s.btnStop,  'Enable', 'on');

        title(s.hAxes, sprintf('Acquiring — %.0f Hz, %.2f Vpp @ %.0f S/s', ...
              p.freq, p.amp, p.sampleRate), ...
              'Color', [0.20 1.00 0.55], 'FontSize', 11, 'FontWeight', 'bold');

        guidata(hFig, s);
        setStatus(s, 'Configuring DAQ session…');

        % Delegate to acquisition loop
        runAcquisition(p);
    end


    % ------------------------------------------------------------------
    function onStop(~, ~)
        s = guidata(hFig);
        s.stopReq = true;
        guidata(hFig, s);
        setStatus(s, 'Stop requested — finishing current scan…');
    end


    % ------------------------------------------------------------------
    function onCheckboxChange(~, ~)
        s = guidata(hFig);
        set(s.hLineLive,     'Visible', onOff(get(s.chkLive,     'Value')));
        set(s.hLineExpected, 'Visible', onOff(get(s.chkExpected, 'Value')));
    end


    % ------------------------------------------------------------------
    function onApplyZoom(~, ~)
        s  = guidata(hFig);
        t0 = str2double(get(s.zoomStart, 'String'));
        t1 = str2double(get(s.zoomEnd,   'String'));
        ax = s.hAxes;
        if ~isnan(t0) && ~isnan(t1) && t1 > t0
            xlim(ax, [t0 t1]);
        elseif ~isnan(t0)
            curXL = xlim(ax);
            xlim(ax, [t0 curXL(2)]);
        elseif ~isnan(t1)
            curXL = xlim(ax);
            xlim(ax, [curXL(1) t1]);
        else
            setStatus(s, 'Zoom: enter at least one valid time value.', 'warn');
        end
        % Y axis is NOT altered by zoom (spec requirement)
    end


    % ------------------------------------------------------------------
    function onResetZoom(~, ~)
        s = guidata(hFig);
        set(s.zoomStart, 'String', '');
        set(s.zoomEnd,   'String', '');
        axis(s.hAxes, 'auto x');
    end


    % ------------------------------------------------------------------
    function onClose(~, ~)
        s = guidata(hFig);
        % Clean up DAQ session on close
        if ~isempty(s.daqSess)
            try
                if isvalid(s.daqSess)
                    stop(s.daqSess);
                    delete(s.daqSess);
                end
            catch
            end
        end
        delete(hFig);
    end


    % ================================================================== %
    %  ACQUISITION ENGINE                                                   %
    % ================================================================== %

    function runAcquisition(p)
    % runAcquisition  Create DAQ session, output sine, acquire, poll loop.

        s = guidata(hFig);
        d = [];   % session handle (named 'd' for delete(d) in error paths)

        % ---- 1. Create DAQ session ------------------------------------ %
        try
            d = daq('ni');
            d.Rate = p.sampleRate;
        catch ME
            logError(s.logFile, 'Session creation', ME);
            setStatus(s, ['DAQ session error: ' ME.message], 'error');
            cleanupSession(d);
            resetButtons(s);
            return;
        end

        % ---- 2. Add channels ------------------------------------------ %
        try
            addoutput(d, p.deviceName, p.outChan, 'Voltage');
            ch_in = addinput(d, p.deviceName, p.inChan, 'Voltage');
            ch_in.TerminalConfig = 'SingleEnded';
        catch ME
            logError(s.logFile, 'Channel configuration', ME);
            setStatus(s, ['Channel config error: ' ME.message], 'error');
            cleanupSession(d);
            resetButtons(s);
            return;
        end

        % ---- 3. Build output waveform ---------------------------------- %
        nSamples = round(p.sampleRate * p.duration);
        t_out    = (0 : nSamples-1)' / p.sampleRate;
        waveform = (p.amp / 2) .* sin(2 * pi * p.freq * t_out);

        % ---- 4. Preload output waveform into session ------------------- %
        try
            preload(d, waveform);
        catch ME
            logError(s.logFile, 'Output preload', ME);
            setStatus(s, ['Preload error: ' ME.message], 'error');
            cleanupSession(d);
            resetButtons(s);
            return;
        end

        % Store session handle in guidata before starting
        s.daqSess = d;
        guidata(hFig, s);

        % ---- 5. Start session ----------------------------------------- %
        try
            start(d, 'RepeatOutput');
        catch ME
            logError(s.logFile, 'Acquisition start', ME);
            setStatus(s, ['Start error: ' ME.message], 'error');
            cleanupSession(d);
            resetButtons(s);
            return;
        end

        setStatus(s, sprintf( ...
            'Acquiring: %.0f Hz, %.2f Vpp, %.0f S/s, %.3f s blocks', ...
            p.freq, p.amp, p.sampleRate, p.duration));

        % ---- 6. Polling loop ------------------------------------------ %
        blockDur    = p.duration;           % seconds per read block
        scansToRead = nSamples;
        tOffset     = 0;                    % running time offset

        while true
            % Check stop flag
            s = guidata(hFig);
            if s.stopReq || ~isvalid(hFig)
                break;
            end

            % Read one block of data
            try
                [data, ~] = read(d, scansToRead, 'OutputFormat', 'Matrix');
            catch ME
                logError(s.logFile, 'Data read', ME);
                setStatus(s, ['Read error: ' ME.message], 'error');
                break;
            end

            % Accumulate data
            t_block = tOffset + (0 : scansToRead-1)' / p.sampleRate;
            tOffset = tOffset + blockDur;

            s = guidata(hFig);
            s.timeData = [s.timeData; t_block];   %#ok<AGROW>
            s.voltData = [s.voltData; data];       %#ok<AGROW>
            guidata(hFig, s);

            % Live plot update
            try
                set(s.hLineLive, 'XData', s.timeData, 'YData', s.voltData);
                xlim(s.hAxes, [max(0, tOffset - 5*blockDur), tOffset]);
                drawnow limitrate;
            catch
                % Figure may have been closed
                break;
            end
        end

        % ---- 7. Stop and clean up ------------------------------------- %
        try
            stop(d);
        catch ME
            logError(s.logFile, 'Acquisition stop', ME);
        end
        cleanupSession(d);

        % ---- 8. Final overlay plot ------------------------------------ %
        s = guidata(hFig);
        if isvalid(hFig) && ~isempty(s.timeData)
            t_full    = s.timeData;
            expected  = (p.amp / 2) .* sin(2 * pi * p.freq * t_full);

            set(s.hLineLive,     'XData', t_full, 'YData', s.voltData);
            set(s.hLineExpected, 'XData', t_full, 'YData', expected);

            % Apply visibility from checkboxes
            set(s.hLineLive,     'Visible', onOff(get(s.chkLive,     'Value')));
            set(s.hLineExpected, 'Visible', onOff(get(s.chkExpected, 'Value')));

            axis(s.hAxes, 'auto x');
            title(s.hAxes, ...
                sprintf('Acquired %.3f s — %.0f Hz, %.2f Vpp', ...
                        t_full(end), p.freq, p.amp), ...
                'Color', clrAccent, 'FontSize', 11, 'FontWeight', 'bold');
            drawnow;

            % ---- 9. Save data ---------------------------------------- %
            saveData(s, t_full, s.voltData, p);
        end

        resetButtons(s);
        s = guidata(hFig);
        s.running  = false;
        s.daqSess  = [];
        guidata(hFig, s);
    end


    % ================================================================== %
    %  DATA SAVE                                                            %
    % ================================================================== %

    function saveData(s, tvec, vvec, p)
    % saveData  Save acquired data.  Primary: CSV time/value pairs.
    %           Fallback (no DSP System Toolbox): .mat file.

        timestamp = datestr(now, 'yyyymmdd_HHMMSS');  %#ok<TNOW1,DATST>
        csvName   = sprintf('daq_data_%s.csv', timestamp);
        matName   = sprintf('daq_data_%s.mat', timestamp);

        try
            % Attempt CSV save (no toolbox required)
            fid = fopen(csvName, 'w');
            if fid == -1
                error('Cannot open file for writing: %s', csvName);
            end
            fprintf(fid, 'Time_s,Voltage_V\n');
            fprintf(fid, '%.9f,%.9f\n', [tvec, vvec]');
            fclose(fid);
            setStatus(s, sprintf('Data saved → %s  (%.0f samples)', ...
                      csvName, numel(tvec)));
        catch ME
            % Fallback: save as .mat
            logError(s.logFile, 'CSV save', ME);
            try
                sampleRate = p.sampleRate; %#ok<NASGU>
                frequency  = p.freq;       %#ok<NASGU>
                amplitude  = p.amp;        %#ok<NASGU>
                save(matName, 'tvec', 'vvec', 'sampleRate', 'frequency', 'amplitude');
                setStatus(s, sprintf( ...
                    'CSV failed; saved as MAT → %s', matName), 'warn');
            catch ME2
                logError(s.logFile, 'MAT save', ME2);
                setStatus(s, 'Save failed — see daq_error_log.txt', 'error');
            end
        end
    end


    % ================================================================== %
    %  HELPERS                                                              %
    % ================================================================== %

    function p = readParams(s)
    % readParams  Read and validate GUI parameter fields.
        p.deviceName = strtrim(get(s.fields.deviceName, 'String'));
        p.outChan    = strtrim(get(s.fields.outChan,    'String'));
        p.inChan     = strtrim(get(s.fields.inChan,     'String'));
        p.freq       = mustPositiveNum(s.fields.freq,       'Frequency');
        p.amp        = mustPositiveNum(s.fields.amp,        'Amplitude');
        p.sampleRate = mustPositiveNum(s.fields.sampleRate, 'Sample Rate');
        p.duration   = mustPositiveNum(s.fields.duration,   'Duration');

        if isempty(p.deviceName)
            error('Device name cannot be empty.');
        end
        if p.sampleRate < 2 * p.freq
            error('Sample rate must be > 2× frequency (Nyquist).');
        end
    end

    function v = mustPositiveNum(hEdit, name)
        v = str2double(get(hEdit, 'String'));
        if isnan(v) || v <= 0
            error('%s must be a positive number.', name);
        end
    end

    function cleanupSession(d)
    % cleanupSession  Safely stop and delete the DAQ session.
        if ~isempty(d)
            try
                if isvalid(d)
                    stop(d);
                end
            catch
            end
            try
                delete(d);
            catch
            end
        end
    end

    function resetButtons(s)
    % resetButtons  Re-enable Start, disable Stop.
        if isvalid(hFig)
            set(s.btnStart, 'Enable', 'on');
            set(s.btnStop,  'Enable', 'off');
        end
    end

    function setStatus(s, msg, level)
    % setStatus  Update status bar and print to Command Window.
        if nargin < 3
            level = 'info';
        end
        switch level
            case 'warn',  clr = [1.00 0.75 0.20];
            case 'error', clr = [1.00 0.40 0.40];
            otherwise,    clr = [0.92 0.92 0.95];
        end
        if isvalid(hFig)
            ts = datestr(now, 'HH:MM:SS');  %#ok<TNOW1,DATST>
            set(s.hStatus, 'String', sprintf('[%s]  %s', ts, msg), ...
                'ForegroundColor', clr);
            drawnow;
        end
        fprintf('[%s] %s\n', datestr(now, 'HH:MM:SS'), msg);  %#ok<TNOW1,DATST>
    end

    function logError(logFile, operation, ME)
    % logError  Append timestamped error entry to log file and Command Window.
        ts  = datestr(now, 'yyyy-mm-dd HH:MM:SS');  %#ok<TNOW1,DATST>
        sep = repmat('=', 1, 70);

        % Build stack trace string
        stackStr = '';
        for si = 1:numel(ME.stack)
            stackStr = sprintf('%s\n    at %s (line %d)', ...
                stackStr, ME.stack(si).name, ME.stack(si).line);
        end

        entry = sprintf( ...
            '\n%s\nTIMESTAMP : %s\nOPERATION : %s\nMESSAGE   : %s\nSTACK     :%s\n%s\n', ...
            sep, ts, operation, ME.message, stackStr, sep);

        % Write to log file
        try
            fid = fopen(logFile, 'a');
            if fid ~= -1
                fprintf(fid, '%s', entry);
                fclose(fid);
            end
        catch
            % Cannot write log — print to Command Window only
        end

        % Always print to Command Window
        fprintf('%s', entry);
    end

    function str = onOff(val)
    % onOff  Convert checkbox value (0/1) to 'off'/'on'.
        if val
            str = 'on';
        else
            str = 'off';
        end
    end

end  % buildGUI
