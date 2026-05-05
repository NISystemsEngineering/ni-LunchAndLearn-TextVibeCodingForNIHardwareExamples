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
%   working directory. To change the path, modify LOG_FILE inside buildGUI()
%   (search for "LOG_FILE =").

    buildGUI();
end


% ======================================================================= %
%  GUI CONSTRUCTION                                                         %
% ======================================================================= %
function buildGUI()

    % ---- Log file path (change this string to redirect error logging) -- %
    LOG_FILE = 'daq_error_log.txt';   % <-- CHANGE THIS PATH IF NEEDED

    % NI-DAQmx requires at least this many samples in the preload buffer
    % for RepeatOutput (background generation). Do not set below 5000.
    MIN_PRELOAD_SAMPLES = 5000;       % <-- adjust if driver demands differ

    % ------------------------------------------------------------------ %
    %  Figure  -  fixed pixel size ensures all controls fit without overlap%
    % ------------------------------------------------------------------ %
    FIG_W  = 1280;   % total figure width  (px)
    FIG_H  = 820;    % total figure height (px)
    LEFT_W = 310;    % width of left control panel (px)

    hFig = figure( ...
        'Name',            'DAQ Sine Wave Generator & Acquisition', ...
        'NumberTitle',     'off', ...
        'Resize',          'off', ...
        'Units',           'pixels', ...
        'Position',        [60 40 FIG_W FIG_H], ...
        'CloseRequestFcn', @onClose, ...
        'Color',           [0.15 0.15 0.18]);

    % ------------------------------------------------------------------ %
    %  Application state                                                   %
    % ------------------------------------------------------------------ %
    s.hFig        = hFig;
    s.logFile     = LOG_FILE;
    s.minPreload  = MIN_PRELOAD_SAMPLES;
    s.daqSess     = [];
    s.running     = false;
    s.stopReq     = false;
    s.timeData    = [];
    s.voltData    = [];

    % ------------------------------------------------------------------ %
    %  Colours & fonts                                                     %
    % ------------------------------------------------------------------ %
    clrPanel  = [0.18 0.18 0.22];
    clrCard   = [0.22 0.22 0.28];
    clrAccent = [0.20 0.60 1.00];
    clrStart  = [0.18 0.72 0.44];
    clrStop   = [0.90 0.32 0.32];
    clrText   = [0.92 0.92 0.95];
    clrLabel  = [0.60 0.65 0.75];
    fontMain  = 'Segoe UI';
    fontMono  = 'Consolas';

    % ================================================================== %
    %  LEFT PANEL  (pixel-positioned so nothing can overlap)              %
    % ================================================================== %
    hLeft = uipanel('Parent', hFig, ...
        'Units', 'pixels', 'Position', [0 0 LEFT_W FIG_H], ...
        'BackgroundColor', clrPanel, 'BorderType', 'none');

    % Pixel layout: Y cursor starts near the top and moves DOWN.
    % All controls placed with absolute pixel coords inside hLeft.
    PAD = 14;          % horizontal margin (px)
    CW  = LEFT_W - 2*PAD;   % usable control width (px)
    LH  = 14;          % label height
    EH  = 24;          % edit-box height
    BH  = 46;          % button height
    GAP = 7;           % vertical gap between param groups

    % Running Y cursor (top of next control, in panel pixels from bottom).
    % We start 12px below the top of the panel.
    yc = FIG_H - 12;

    % ---- Helper: text label ------------------------------------------
    function uiLbl(txt, yy, h, fsz, bold, clr)
        fw = 'normal'; if bold, fw = 'bold'; end
        uicontrol('Parent', hLeft, 'Style', 'text', ...
            'Units', 'pixels', 'Position', [PAD yy-h CW h], ...
            'String', txt, 'FontName', fontMain, 'FontSize', fsz, ...
            'FontWeight', fw, 'ForegroundColor', clr, ...
            'BackgroundColor', clrPanel, 'HorizontalAlignment', 'left');
    end

    % ---- Helper: edit box --------------------------------------------
    function hE = uiEdt(yy, defVal, fnt)
        hE = uicontrol('Parent', hLeft, 'Style', 'edit', ...
            'Units', 'pixels', 'Position', [PAD yy-EH CW EH], ...
            'String', defVal, 'FontName', fnt, 'FontSize', 10, ...
            'ForegroundColor', clrText, 'BackgroundColor', clrCard, ...
            'HorizontalAlignment', 'left');
    end

    % ---- Helper: horizontal separator --------------------------------
    function uiSep(yy)
        uicontrol('Parent', hLeft, 'Style', 'text', ...
            'Units', 'pixels', 'Position', [PAD yy-2 CW 2], ...
            'BackgroundColor', clrAccent);
    end

    % ---- Section: DAQ Configuration ----------------------------------
    uiLbl('DAQ Configuration', yc, 26, 14, true, clrAccent);
    yc = yc - 26 - 4;

    % ---- Parameter fields --------------------------------------------
    paramDefs = { ...
        'Device Name',     'MIODAQ1', 'deviceName'; ...
        'Output Channel',  'ao0',     'outChan';    ...
        'Input Channel',   'ai0',     'inChan';     ...
        'Frequency (Hz)',  '1000',    'freq';       ...
        'Amplitude (Vpp)', '1',       'amp';        ...
        'Sample Rate (Hz)','10000',   'sampleRate'; ...
        'Duration (s)',    '0.1',     'duration';   ...
    };

    s.fields = struct();
    for k = 1:size(paramDefs,1)
        uiLbl(paramDefs{k,1}, yc, LH, 8, false, clrLabel);
        yc = yc - LH - 2;
        s.fields.(paramDefs{k,3}) = uiEdt(yc, paramDefs{k,2}, fontMono);
        yc = yc - EH - GAP;
    end

    % ---- Separator ---------------------------------------------------
    yc = yc - 4;
    uiSep(yc); yc = yc - 10;

    % ---- Section: Plot Display ---------------------------------------
    uiLbl('Plot Display', yc, 20, 11, true, clrAccent);
    yc = yc - 20 - 4;

    s.chkLive = uicontrol('Parent', hLeft, 'Style', 'checkbox', ...
        'Units', 'pixels', 'Position', [PAD yc-20 CW 20], ...
        'String', 'Live / Acquired Signal', 'Value', 1, ...
        'FontName', fontMain, 'FontSize', 9, ...
        'ForegroundColor', clrText, 'BackgroundColor', clrPanel, ...
        'Callback', @onCheckboxChange);
    yc = yc - 20 - 4;

    s.chkExpected = uicontrol('Parent', hLeft, 'Style', 'checkbox', ...
        'Units', 'pixels', 'Position', [PAD yc-20 CW 20], ...
        'String', 'Expected Sine Wave', 'Value', 1, ...
        'FontName', fontMain, 'FontSize', 9, ...
        'ForegroundColor', clrText, 'BackgroundColor', clrPanel, ...
        'Callback', @onCheckboxChange);
    yc = yc - 20 - 8;

    % ---- Separator ---------------------------------------------------
    uiSep(yc); yc = yc - 10;

    % ---- Section: Zoom Tool ------------------------------------------
    uiLbl('Zoom Tool  (X-axis only)', yc, 20, 11, true, clrAccent);
    yc = yc - 20 - 4;

    HLF = floor((CW - 8) / 2);   % half-width for side-by-side fields

    % Sub-labels for the two zoom fields
    uicontrol('Parent', hLeft, 'Style', 'text', ...
        'Units', 'pixels', 'Position', [PAD yc-LH HLF LH], ...
        'String', 'T start (s)', 'FontName', fontMain, 'FontSize', 8, ...
        'ForegroundColor', clrLabel, 'BackgroundColor', clrPanel, ...
        'HorizontalAlignment', 'left');
    uicontrol('Parent', hLeft, 'Style', 'text', ...
        'Units', 'pixels', 'Position', [PAD+HLF+8 yc-LH HLF LH], ...
        'String', 'T end (s)', 'FontName', fontMain, 'FontSize', 8, ...
        'ForegroundColor', clrLabel, 'BackgroundColor', clrPanel, ...
        'HorizontalAlignment', 'left');
    yc = yc - LH - 2;

    s.zoomStart = uicontrol('Parent', hLeft, 'Style', 'edit', ...
        'Units', 'pixels', 'Position', [PAD yc-EH HLF EH], ...
        'String', '', 'FontName', fontMono, 'FontSize', 9, ...
        'ForegroundColor', clrText, 'BackgroundColor', clrCard, ...
        'HorizontalAlignment', 'left', 'TooltipString', 'Leave blank for auto');
    s.zoomEnd = uicontrol('Parent', hLeft, 'Style', 'edit', ...
        'Units', 'pixels', 'Position', [PAD+HLF+8 yc-EH HLF EH], ...
        'String', '', 'FontName', fontMono, 'FontSize', 9, ...
        'ForegroundColor', clrText, 'BackgroundColor', clrCard, ...
        'HorizontalAlignment', 'left', 'TooltipString', 'Leave blank for auto');
    yc = yc - EH - 6;

    uicontrol('Parent', hLeft, 'Style', 'pushbutton', ...
        'Units', 'pixels', 'Position', [PAD yc-26 CW 26], ...
        'String', 'Apply Zoom', ...
        'FontName', fontMain, 'FontSize', 9, 'FontWeight', 'bold', ...
        'ForegroundColor', clrText, 'BackgroundColor', [0.30 0.30 0.38], ...
        'Callback', @onApplyZoom);
    yc = yc - 26 - 6;

    uicontrol('Parent', hLeft, 'Style', 'pushbutton', ...
        'Units', 'pixels', 'Position', [PAD yc-26 CW 26], ...
        'String', 'Reset Zoom', ...
        'FontName', fontMain, 'FontSize', 9, ...
        'ForegroundColor', clrLabel, 'BackgroundColor', [0.22 0.22 0.28], ...
        'Callback', @onResetZoom);

    % ---- START / STOP pinned to the bottom of the panel --------------
    % These use absolute positions from the BOTTOM (y=0 upward).
    s.btnStop = uicontrol('Parent', hLeft, 'Style', 'pushbutton', ...
        'Units', 'pixels', 'Position', [PAD 10 CW BH], ...
        'String', char(9632) + "  STOP", ...
        'FontName', fontMain, 'FontSize', 13, 'FontWeight', 'bold', ...
        'ForegroundColor', [1 1 1], 'BackgroundColor', clrStop, ...
        'Enable', 'off', 'Callback', @onStop);

    s.btnStart = uicontrol('Parent', hLeft, 'Style', 'pushbutton', ...
        'Units', 'pixels', 'Position', [PAD 10+BH+8 CW BH], ...
        'String', char(9658) + "  START", ...
        'FontName', fontMain, 'FontSize', 13, 'FontWeight', 'bold', ...
        'ForegroundColor', [1 1 1], 'BackgroundColor', clrStart, ...
        'Callback', @onStart);

    % ================================================================== %
    %  RIGHT PANEL  -  axes + status bar                                   %
    % ================================================================== %
    RP_X = LEFT_W;
    RP_W = FIG_W - LEFT_W;

    hRight = uipanel('Parent', hFig, ...
        'Units', 'pixels', 'Position', [RP_X 0 RP_W FIG_H], ...
        'BackgroundColor', clrPanel, 'BorderType', 'none');

    SB_H = 30;
    s.hStatus = uicontrol('Parent', hRight, 'Style', 'text', ...
        'Units', 'pixels', 'Position', [8 4 RP_W-16 SB_H], ...
        'String', 'Ready. Configure parameters and press START.', ...
        'FontName', fontMain, 'FontSize', 9, ...
        'ForegroundColor', clrText, 'BackgroundColor', clrCard, ...
        'HorizontalAlignment', 'left');

    % Axes dimensions
    ML = 68; MB = SB_H+48; MR = 20; MT = 46;
    s.hAxes = axes('Parent', hRight, ...
        'Units', 'pixels', ...
        'Position', [ML MB RP_W-ML-MR FIG_H-MB-MT], ...
        'Color', [0.10 0.10 0.13], ...
        'XColor', clrLabel, 'YColor', clrLabel, ...
        'GridColor', [0.30 0.30 0.38], 'GridAlpha', 0.5, ...
        'XGrid', 'on', 'YGrid', 'on', ...
        'FontName', fontMain, 'FontSize', 9);

    xlabel(s.hAxes, 'Time (s)',    'Color', clrText, 'FontSize', 10);
    ylabel(s.hAxes, 'Voltage (V)', 'Color', clrText, 'FontSize', 10);
    title(s.hAxes,  'Waiting for acquisition...', ...
          'Color', clrAccent, 'FontSize', 11, 'FontWeight', 'bold');

    hold(s.hAxes, 'on');
    s.hLineLive     = plot(s.hAxes, NaN, NaN, '-', ...
        'Color', [0.20 0.75 1.00], 'LineWidth', 1.2, 'DisplayName', 'Acquired');
    s.hLineExpected = plot(s.hAxes, NaN, NaN, '--', ...
        'Color', [1.00 0.65 0.15], 'LineWidth', 1.2, 'DisplayName', 'Expected');
    legend(s.hAxes, 'Location', 'northeast', ...
           'TextColor', clrText, 'Color', clrCard);

    guidata(hFig, s);


    % ================================================================== %
    %  CALLBACKS                                                            %
    % ================================================================== %

    function onStart(~, ~)
        s = guidata(hFig);
        if s.running, return; end
        try
            p = readParams(s);
        catch ME
            setStatus(s, ['Parameter error: ' ME.message], 'warn');
            return;
        end
        s.timeData = [];
        s.voltData = [];
        s.stopReq  = false;
        s.running  = true;
        set(s.btnStart, 'Enable', 'off');
        set(s.btnStop,  'Enable', 'on');
        title(s.hAxes, ...
            sprintf('Acquiring - %.0f Hz, %.2f Vpp @ %.0f S/s', ...
                    p.freq, p.amp, p.sampleRate), ...
            'Color', [0.20 1.00 0.55], 'FontSize', 11, 'FontWeight', 'bold');
        guidata(hFig, s);
        setStatus(s, 'Configuring DAQ session...');
        runAcquisition(p);
    end

    function onStop(~, ~)
        s = guidata(hFig);
        s.stopReq = true;
        guidata(hFig, s);
        setStatus(s, 'Stop requested - finishing current block...');
    end

    function onCheckboxChange(~, ~)
        s = guidata(hFig);
        set(s.hLineLive,     'Visible', boolVis(get(s.chkLive,     'Value')));
        set(s.hLineExpected, 'Visible', boolVis(get(s.chkExpected, 'Value')));
    end

    function onApplyZoom(~, ~)
        s  = guidata(hFig);
        t0 = str2double(get(s.zoomStart, 'String'));
        t1 = str2double(get(s.zoomEnd,   'String'));
        ax = s.hAxes;
        ok0 = ~isnan(t0);
        ok1 = ~isnan(t1);
        if ok0 && ok1
            if t1 > t0
                xlim(ax, [t0 t1]);
            else
                setStatus(s, 'Zoom: T end must be greater than T start.', 'warn');
            end
        elseif ok0
            cur = xlim(ax); xlim(ax, [t0 cur(2)]);
        elseif ok1
            cur = xlim(ax); xlim(ax, [cur(1) t1]);
        else
            setStatus(s, 'Zoom: enter at least one valid time value.', 'warn');
        end
        % Y-axis intentionally not changed by zoom (per spec)
    end

    function onResetZoom(~, ~)
        s = guidata(hFig);
        set(s.zoomStart, 'String', '');
        set(s.zoomEnd,   'String', '');
        axis(s.hAxes, 'auto x');
    end

    function onClose(~, ~)
        s = guidata(hFig);
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

        s = guidata(hFig);
        d = [];   % DAQ session handle - always in scope for delete(d)

        % ---- 1. Create session --------------------------------------- %
        try
            d = daq('ni');
            d.Rate = p.sampleRate;
        catch ME
            logError(s.logFile, 'Session creation', ME);
            setStatus(s, ['DAQ session error: ' ME.message], 'error');
            cleanupSession(d); resetButtons(s); return;
        end

        % ---- 2. Configure channels ----------------------------------- %
        try
            addoutput(d, p.deviceName, p.outChan, 'Voltage');
            ch_in = addinput(d, p.deviceName, p.inChan, 'Voltage');
            ch_in.TerminalConfig = 'SingleEnded';
        catch ME
            logError(s.logFile, 'Channel configuration', ME);
            setStatus(s, ['Channel config error: ' ME.message], 'error');
            cleanupSession(d); resetButtons(s); return;
        end

        % ---- 3. Build output waveform -------------------------------- %
        %
        % FIX: NI-DAQmx demands at least MIN_PRELOAD_SAMPLES in the
        % output buffer to run RepeatOutput (background generation).
        % When the user-specified duration is short (e.g. 0.1 s at
        % 10 kS/s = 1000 samples), we tile enough complete sine cycles
        % to reach the minimum. The tile is phase-seamless so the output
        % is a clean continuous sine with no glitches at the repeat point.
        %
        nNatural = round(p.sampleRate * p.duration);  % samples from duration field

        % Samples per complete cycle (exact, for seamless tiling)
        samplesPerCycle = p.sampleRate / p.freq;

        % Minimum whole cycles to satisfy both the user duration and the
        % driver minimum.
        minCycles = max( ceil(nNatural        / samplesPerCycle), ...
                         ceil(s.minPreload    / samplesPerCycle) );

        nBuf  = round(minCycles * samplesPerCycle);
        t_out = (0 : nBuf-1)' / p.sampleRate;
        waveform = (p.amp / 2) .* sin(2 * pi * p.freq * t_out);

        if nBuf > nNatural
            setStatus(s, sprintf( ...
                'Buffer extended to %d samples (%.1f ms) to meet driver minimum of %d.', ...
                nBuf, nBuf/p.sampleRate*1e3, s.minPreload));
        end

        % The read block size matches the user-requested duration.
        scansToRead = nNatural;
        blockDur    = p.duration;

        % ---- 4. Preload --------------------------------------------- %
        try
            preload(d, waveform);
        catch ME
            logError(s.logFile, 'Output preload', ME);
            setStatus(s, ['Preload error: ' ME.message], 'error');
            cleanupSession(d); resetButtons(s); return;
        end

        s.daqSess = d;
        guidata(hFig, s);

        % ---- 5. Start ----------------------------------------------- %
        try
            start(d, 'RepeatOutput');
        catch ME
            logError(s.logFile, 'Acquisition start', ME);
            setStatus(s, ['Start error: ' ME.message], 'error');
            cleanupSession(d); resetButtons(s); return;
        end

        setStatus(s, sprintf( ...
            'Acquiring: %.0f Hz, %.2f Vpp, %.0f S/s, %d-sample blocks', ...
            p.freq, p.amp, p.sampleRate, scansToRead));

        % ---- 6. Live polling loop ------------------------------------ %
        tOffset = 0;

        while true
            s = guidata(hFig);
            if s.stopReq || ~isvalid(hFig), break; end

            try
                [data, ~] = read(d, scansToRead, 'OutputFormat', 'Matrix');
            catch ME
                logError(s.logFile, 'Data read', ME);
                setStatus(s, ['Read error: ' ME.message], 'error');
                break;
            end

            t_block = tOffset + (0 : scansToRead-1)' / p.sampleRate;
            tOffset = tOffset + blockDur;

            s.timeData = [s.timeData; t_block];  %#ok<AGROW>
            s.voltData = [s.voltData; data];      %#ok<AGROW>
            guidata(hFig, s);

            try
                set(s.hLineLive, 'XData', s.timeData, 'YData', s.voltData);
                xLo = max(0, tOffset - 5*blockDur);
                xlim(s.hAxes, [xLo, max(xLo + blockDur, tOffset)]);
                drawnow limitrate;
            catch
                break;  % figure closed during drawnow
            end
        end

        % ---- 7. Stop & release hardware ----------------------------- %
        try
            stop(d);
        catch ME
            logError(s.logFile, 'Acquisition stop', ME);
        end
        cleanupSession(d);

        % ---- 8. Final overlay --------------------------------------- %
        s = guidata(hFig);
        if isvalid(hFig) && ~isempty(s.timeData)
            t_full   = s.timeData;
            expected = (p.amp / 2) .* sin(2 * pi * p.freq * t_full);

            set(s.hLineLive,     'XData', t_full, 'YData', s.voltData);
            set(s.hLineExpected, 'XData', t_full, 'YData', expected);
            set(s.hLineLive,     'Visible', boolVis(get(s.chkLive,     'Value')));
            set(s.hLineExpected, 'Visible', boolVis(get(s.chkExpected, 'Value')));

            axis(s.hAxes, 'auto x');
            title(s.hAxes, ...
                sprintf('Acquired %.3f s  |  %.0f Hz, %.2f Vpp', ...
                        t_full(end), p.freq, p.amp), ...
                'Color', clrAccent, 'FontSize', 11, 'FontWeight', 'bold');
            drawnow;

            % ---- 9. Save ------------------------------------------- %
            saveData(s, t_full, s.voltData, p);
        end

        resetButtons(s);
        s = guidata(hFig);
        s.running = false;
        s.daqSess = [];
        guidata(hFig, s);
    end


    % ================================================================== %
    %  DATA SAVE                                                            %
    % ================================================================== %

    function saveData(s, tvec, vvec, p)
    % Primary: CSV with Time_s, Voltage_V columns (one row per sample).
    % Fallback: .mat file if CSV write fails (e.g., no write permission).

        ts      = datestr(now, 'yyyymmdd_HHMMSS');  %#ok<TNOW1,DATST>
        csvName = sprintf('daq_data_%s.csv', ts);
        matName = sprintf('daq_data_%s.mat', ts);

        try
            fid = fopen(csvName, 'w');
            if fid == -1
                error('Cannot open file for writing: %s', csvName);
            end
            fprintf(fid, 'Time_s,Voltage_V\n');
            fprintf(fid, '%.9f,%.9f\n', [tvec(:), vvec(:)]');
            fclose(fid);
            setStatus(s, sprintf('Saved -> %s  (%d samples)', ...
                      csvName, numel(tvec)));
        catch ME
            logError(s.logFile, 'CSV save', ME);
            try
                sampleRate = p.sampleRate; %#ok<NASGU>
                frequency  = p.freq;       %#ok<NASGU>
                amplitude  = p.amp;        %#ok<NASGU>
                save(matName, 'tvec', 'vvec', 'sampleRate', 'frequency', 'amplitude');
                setStatus(s, sprintf('CSV failed; saved as MAT -> %s', matName), 'warn');
            catch ME2
                logError(s.logFile, 'MAT save', ME2);
                setStatus(s, 'Save failed - see daq_error_log.txt', 'error');
            end
        end
    end


    % ================================================================== %
    %  HELPERS                                                              %
    % ================================================================== %

    function p = readParams(s)
        p.deviceName = strtrim(get(s.fields.deviceName, 'String'));
        p.outChan    = strtrim(get(s.fields.outChan,    'String'));
        p.inChan     = strtrim(get(s.fields.inChan,     'String'));
        p.freq       = mustPosNum(s.fields.freq,       'Frequency');
        p.amp        = mustPosNum(s.fields.amp,        'Amplitude');
        p.sampleRate = mustPosNum(s.fields.sampleRate, 'Sample Rate');
        p.duration   = mustPosNum(s.fields.duration,   'Duration');
        if isempty(p.deviceName)
            error('Device name cannot be empty.');
        end
        if p.sampleRate < 2 * p.freq
            error('Sample rate must be > 2x frequency (Nyquist criterion).');
        end
    end

    function v = mustPosNum(hEdit, name)
        v = str2double(get(hEdit, 'String'));
        if isnan(v) || v <= 0
            error('%s must be a positive number.', name);
        end
    end

    function cleanupSession(d)
    % Safely stop and delete the DAQ session to release hardware.
    % Called in ALL error paths to prevent hardware lockup.
        if isempty(d), return; end
        try, if isvalid(d), stop(d); end; catch; end
        try, delete(d); catch; end
    end

    function resetButtons(s)
        if isvalid(hFig)
            set(s.btnStart, 'Enable', 'on');
            set(s.btnStop,  'Enable', 'off');
        end
    end

    function setStatus(s, msg, level)
        if nargin < 3, level = 'info'; end
        switch level
            case 'warn',  clr = [1.00 0.75 0.20];
            case 'error', clr = [1.00 0.40 0.40];
            otherwise,    clr = [0.92 0.92 0.95];
        end
        ts = datestr(now, 'HH:MM:SS');  %#ok<TNOW1,DATST>
        if isvalid(hFig)
            set(s.hStatus, 'String', sprintf('[%s]  %s', ts, msg), ...
                'ForegroundColor', clr);
            drawnow;
        end
        fprintf('[%s] %s\n', ts, msg);
    end

    function logError(logFile, operation, ME)
    % logError  Write a timestamped structured entry to the log file.
    % Each entry includes: timestamp, operation name, error message,
    % and full stack trace. Also echoed to the MATLAB Command Window.
        ts  = datestr(now, 'yyyy-mm-dd HH:MM:SS');  %#ok<TNOW1,DATST>
        sep = repmat('=', 1, 70);
        stackStr = '';
        for si = 1:numel(ME.stack)
            stackStr = sprintf('%s\n    at %s (line %d)', ...
                stackStr, ME.stack(si).name, ME.stack(si).line);
        end
        entry = sprintf( ...
            '\n%s\nTIMESTAMP : %s\nOPERATION : %s\nMESSAGE   : %s\nSTACK     :%s\n%s\n', ...
            sep, ts, operation, ME.message, stackStr, sep);
        try
            fid = fopen(logFile, 'a');
            if fid ~= -1
                fprintf(fid, '%s', entry);
                fclose(fid);
            end
        catch
        end
        fprintf('%s', entry);  % always echo to Command Window
    end

    function str = boolVis(val)
    % boolVis  Map 1/0 to 'on'/'off' for the Visible property.
        if val, str = 'on'; else, str = 'off'; end
    end

end  % buildGUI
