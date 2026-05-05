// ==================================================================================================
// Title        : PXIe-5842 VST — RF Spectrum
// Description  : Generates a CW tone via NI-RFSG (persistent session) and acquires the
//                power spectrum via RFmx SpecAn.  Left sidebar exposes all key parameters.
// Device       : PXIe-5842 (combined VST) in loopback (RFout → RFin)
// ==================================================================================================

using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.Windows.Forms;
using NationalInstruments;
using NationalInstruments.ModularInstruments.NIRfsg;
using NationalInstruments.RFmx.InstrMX;
using NationalInstruments.RFmx.SpecAnMX;

namespace NationalInstruments.Examples.VST5842Loopback
{
    public class MainForm : Form
    {
        private const double Timeout = 10.0;

        // ── Persistent RFSG session ──────────────────────────────────────────────
        private NIRfsg _rfsgSession;
        private bool   _rfOutputEnabled;

        // ── Signal Generator controls ────────────────────────────────────────────
        private TextBox  _genResourceBox;
        private ComboBox _freqUnitCombo;
        private TextBox  _freqBox;
        private Label    _freqUnitSuffix;
        private TextBox  _powerBox;
        private Button   _startBtn;
        private Button   _stopBtn;
        private Panel    _rfIndicator;

        // ── Spectrum Analyzer controls ───────────────────────────────────────────
        private TextBox  _saResourceBox;
        private TextBox  _centerFreqBox;
        private ComboBox _centerFreqUnitCombo;
        private TextBox  _spanBox;
        private ComboBox _spanUnitCombo;
        private Button   _acquireBtn;

        // ── Right-panel controls ─────────────────────────────────────────────────
        private Panel _specPanel;
        private Label _statusLabel;

        // ── Acquired data ────────────────────────────────────────────────────────
        private double[] _freqAxis;   // GHz
        private double[] _psd;        // dBm

        // ── Theme colors ─────────────────────────────────────────────────────────
        private static readonly Color ColBg       = Color.FromArgb(14, 14, 22);
        private static readonly Color ColSidebar  = Color.FromArgb(18, 18, 28);
        private static readonly Color ColInput    = Color.FromArgb(10, 36, 62);
        private static readonly Color ColTeal     = Color.FromArgb(0, 108, 110);
        private static readonly Color ColTealDim  = Color.FromArgb(45, 65, 68);
        private static readonly Color ColRfRow    = Color.FromArgb(12, 46, 46);
        private static readonly Color ColFg       = Color.White;
        private static readonly Color ColFgMuted  = Color.FromArgb(155, 175, 185);

        public MainForm()
        {
            BuildUI();
            SetSessionState(false);
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            CloseRfsg();
            base.OnFormClosing(e);
        }

        // ── Parsed property accessors ────────────────────────────────────────────
        private double CarrierHz  => ReadFreq(_freqBox,       _freqUnitCombo);
        private double OutPowerDbm
        {
            get { double.TryParse(_powerBox.Text, NumberStyles.Float,
                                  CultureInfo.InvariantCulture, out double v); return v; }
        }
        private double CenterHz   => ReadFreq(_centerFreqBox, _centerFreqUnitCombo);
        private double SpanHz     => ReadFreq(_spanBox,       _spanUnitCombo);

        private static double ReadFreq(TextBox tb, ComboBox unit)
        {
            double.TryParse(tb.Text, NumberStyles.Float,
                            CultureInfo.InvariantCulture, out double v);
            return (unit.SelectedItem?.ToString()) switch
            {
                "GHz" => v * 1e9,
                "MHz" => v * 1e6,
                "kHz" => v * 1e3,
                _     => v
            };
        }

        // ═══════════════════════════════════════════════════════════════════════
        //  UI construction
        // ═══════════════════════════════════════════════════════════════════════
        private void BuildUI()
        {
            Text          = "PXIe-5842 VST — RF Spectrum";
            Size          = new Size(1200, 780);
            MinimumSize   = new Size(960, 600);
            BackColor     = ColBg;
            ForeColor     = ColFg;
            Font          = new Font("Segoe UI", 9f);
            StartPosition = FormStartPosition.CenterScreen;

            // ── Left sidebar ──────────────────────────────────────────────────
            var sidebar = new Panel
            {
                Dock      = DockStyle.Left,
                Width     = 322,
                BackColor = ColSidebar
            };

            // ─ Signal Generator group ─────────────────────────────────────────
            int y = 10;
            var genBox = GBox("Signal Generator  (NI-RFSG)", 8, y, 305);

            int gy = 26;
            AddRow(genBox, "Device Name", gy);
            genBox.Controls.Add(_genResourceBox = IBox("VST1", 10, gy + 20, 283));
            gy += 54;

            AddRow(genBox, "Frequency Unit", gy);
            genBox.Controls.Add(_freqUnitCombo = CBox(new[] { "GHz", "MHz", "kHz", "Hz" }, 10, gy + 20, 283));
            _freqUnitCombo.SelectedIndex = 0;
            _freqUnitCombo.SelectedIndexChanged += (s, e) =>
            {
                if (_freqUnitSuffix != null)
                    _freqUnitSuffix.Text = _freqUnitCombo.SelectedItem?.ToString() ?? "GHz";
            };
            gy += 54;

            AddRow(genBox, "Frequency", gy);
            genBox.Controls.Add(_freqBox = IBox("1", 10, gy + 20, 236));
            _freqUnitSuffix = new Label { Text = "GHz", AutoSize = true,
                                          Location = new Point(252, gy + 24), ForeColor = ColFgMuted };
            genBox.Controls.Add(_freqUnitSuffix);
            gy += 54;

            AddRow(genBox, "Output Power (dBm)", gy);
            genBox.Controls.Add(_powerBox = IBox("-10", 10, gy + 20, 283));
            gy += 54;

            _startBtn = Btn("▶  Start Session", 10, gy, 283, ColTeal);
            _startBtn.Click += StartSession_Click;
            genBox.Controls.Add(_startBtn);
            gy += 44;

            _stopBtn = Btn("■  Stop Session", 10, gy, 283, ColTealDim);
            _stopBtn.Click += StopSession_Click;
            genBox.Controls.Add(_stopBtn);
            gy += 44;

            var rfRow = new Panel
            {
                Location  = new Point(10, gy),
                Size      = new Size(283, 36),
                BackColor = ColRfRow
            };
            rfRow.Controls.Add(new Label
            {
                Text = "RF OUTPUT", AutoSize = true, Location = new Point(8, 10),
                ForeColor = Color.FromArgb(70, 195, 195),
                Font = new Font("Segoe UI", 8f, FontStyle.Bold)
            });
            rfRow.Controls.Add(new Label
            {
                Text = "Enable", AutoSize = true, Location = new Point(108, 10),
                ForeColor = ColFgMuted
            });
            _rfIndicator = new Panel
            {
                Location  = new Point(252, 8),
                Size      = new Size(22, 20),
                BackColor = Color.Transparent,
                Cursor    = Cursors.Hand
            };
            _rfIndicator.Paint  += RfIndicator_Paint;
            _rfIndicator.Click  += RfIndicator_Click;
            rfRow.Controls.Add(_rfIndicator);
            genBox.Controls.Add(rfRow);
            gy += 44;

            genBox.Height = gy + 10;
            y = genBox.Bottom + 10;

            // ─ Spectrum Analyzer group ────────────────────────────────────────
            var saBox = GBox("Spectrum Analyzer  (NI-RFSA)", 8, y, 305);

            int sy = 26;
            AddRow(saBox, "Device Name", sy);
            saBox.Controls.Add(_saResourceBox = IBox("VST1", 10, sy + 20, 283));
            sy += 54;

            AddRow(saBox, "Center Frequency", sy);
            var cfRow = new Panel { Location = new Point(10, sy + 20), Size = new Size(283, 27),
                                    BackColor = Color.Transparent };
            cfRow.Controls.Add(_centerFreqBox = IBox("1", 0, 0, 197));
            cfRow.Controls.Add(_centerFreqUnitCombo = CBox(new[] { "GHz", "MHz", "kHz" }, 201, 0, 82));
            _centerFreqUnitCombo.SelectedIndex = 0;
            saBox.Controls.Add(cfRow);
            sy += 54;

            AddRow(saBox, "Span", sy);
            var spanRow = new Panel { Location = new Point(10, sy + 20), Size = new Size(283, 27),
                                      BackColor = Color.Transparent };
            spanRow.Controls.Add(_spanBox = IBox("100", 0, 0, 197));
            spanRow.Controls.Add(_spanUnitCombo = CBox(new[] { "MHz", "GHz", "kHz" }, 201, 0, 82));
            _spanUnitCombo.SelectedIndex = 0;
            saBox.Controls.Add(spanRow);
            sy += 54;

            _acquireBtn = Btn("⚙  Acquire Spectrum", 10, sy, 283, ColTeal);
            _acquireBtn.Click += Acquire_Click;
            saBox.Controls.Add(_acquireBtn);
            sy += 44;

            saBox.Height = sy + 10;

            sidebar.Controls.AddRange(new Control[] { genBox, saBox });

            // ── Right plot panel ──────────────────────────────────────────────
            var rightPanel = new Panel { Dock = DockStyle.Fill, BackColor = ColBg };

            var titleLabel = new Label
            {
                Text      = "RF Spectrum",
                Dock      = DockStyle.Top,
                Height    = 42,
                Font      = new Font("Segoe UI", 14f, FontStyle.Bold),
                ForeColor = ColFg,
                TextAlign = ContentAlignment.MiddleCenter,
                BackColor = ColBg
            };

            _statusLabel = new Label
            {
                Text      = "Ready.",
                Dock      = DockStyle.Bottom,
                Height    = 26,
                Font      = new Font("Segoe UI", 8.5f),
                ForeColor = Color.FromArgb(90, 200, 130),
                TextAlign = ContentAlignment.MiddleLeft,
                Padding   = new Padding(8, 0, 0, 0),
                BackColor = Color.FromArgb(10, 10, 16)
            };

            _specPanel = new Panel { Dock = DockStyle.Fill, BackColor = Color.Black };
            _specPanel.Paint += SpecPanel_Paint;

            rightPanel.Controls.Add(_specPanel);
            rightPanel.Controls.Add(_statusLabel);
            rightPanel.Controls.Add(titleLabel);

            Controls.Add(rightPanel);
            Controls.Add(sidebar);
        }

        // ── UI factory helpers ─────────────────────────────────────────────────
        private static GroupBox GBox(string title, int x, int y, int w)
            => new GroupBox
            {
                Text = title, Location = new Point(x, y), Width = w,
                ForeColor = ColFgMuted, BackColor = ColSidebar,
                Font = new Font("Segoe UI", 8.5f, FontStyle.Bold)
            };

        private static void AddRow(Control parent, string text, int y)
            => parent.Controls.Add(new Label
            {
                Text = text, Location = new Point(10, y), AutoSize = true,
                ForeColor = Color.FromArgb(185, 198, 208)
            });

        private static TextBox IBox(string text, int x, int y, int w)
            => new TextBox
            {
                Text = text, Location = new Point(x, y), Size = new Size(w, 26),
                BackColor = ColInput, ForeColor = ColFg,
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Segoe UI", 9.5f)
            };

        private static ComboBox CBox(string[] items, int x, int y, int w)
        {
            var cb = new ComboBox
            {
                Location      = new Point(x, y),
                Size          = new Size(w, 26),
                DropDownStyle = ComboBoxStyle.DropDownList,
                BackColor     = Color.White,
                ForeColor     = Color.Black,
                Font          = new Font("Segoe UI", 9f)
            };
            cb.Items.AddRange(items);
            return cb;
        }

        private static Button Btn(string text, int x, int y, int w, Color bg)
        {
            var b = new Button
            {
                Text = text, Location = new Point(x, y), Size = new Size(w, 36),
                FlatStyle = FlatStyle.Flat, BackColor = bg, ForeColor = ColFg,
                Font = new Font("Segoe UI", 9.5f, FontStyle.Bold), Cursor = Cursors.Hand
            };
            b.FlatAppearance.BorderSize = 0;
            return b;
        }

        // ═══════════════════════════════════════════════════════════════════════
        //  Session state
        // ═══════════════════════════════════════════════════════════════════════
        private void SetSessionState(bool active)
        {
            _startBtn.Enabled  = !active;
            _stopBtn.Enabled   = active;
            _stopBtn.BackColor = active ? ColTeal : ColTealDim;
            _rfIndicator.Cursor = active ? Cursors.Hand : Cursors.Default;
            if (!active) { _rfOutputEnabled = false; _rfIndicator.Invalidate(); }
        }

        // ═══════════════════════════════════════════════════════════════════════
        //  Event handlers
        // ═══════════════════════════════════════════════════════════════════════
        private void StartSession_Click(object sender, EventArgs e)
        {
            try
            {
                SetStatus("Opening RFSG session…");
                _rfsgSession = new NIRfsg(_genResourceBox.Text.Trim(), true, false);
                _rfsgSession.RF.Configure(CarrierHz, OutPowerDbm);
                _rfsgSession.Initiate();
                SetSessionState(true);
                SetStatus($"Session started — {CarrierHz / 1e9:F4} GHz, {OutPowerDbm:F1} dBm. " +
                          "RF output is OFF.");
            }
            catch (Exception ex)
            {
                SetStatus("ERROR: " + ex.Message);
                CloseRfsg();
                MessageBox.Show(ex.Message, "Session Error",
                                MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void StopSession_Click(object sender, EventArgs e)
        {
            CloseRfsg();
            SetSessionState(false);
            SetStatus("Session stopped.");
        }

        private void RfIndicator_Click(object sender, EventArgs e)
        {
            if (_rfsgSession == null) return;
            _rfOutputEnabled = !_rfOutputEnabled;
            try
            {
                _rfsgSession.RF.OutputEnabled = _rfOutputEnabled;
                _rfIndicator.Invalidate();
                SetStatus(_rfOutputEnabled
                    ? $"RF Output ON — {CarrierHz / 1e9:F4} GHz at {OutPowerDbm:F1} dBm."
                    : "RF Output OFF.");
            }
            catch (Exception ex)
            {
                _rfOutputEnabled = false;
                _rfIndicator.Invalidate();
                MessageBox.Show(ex.Message, "RF Output Error",
                                MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void Acquire_Click(object sender, EventArgs e)
        {
            _acquireBtn.Enabled = false;
            SetStatus("Acquiring spectrum…");

            RFmxInstrMX  instr  = null;
            RFmxSpecAnMX specAn = null;
            try
            {
                instr  = new RFmxInstrMX(_saResourceBox.Text.Trim(), "");
                specAn = instr.GetSpecAnSignalConfiguration();

                instr.ConfigureFrequencyReference("", RFmxInstrMXConstants.OnboardClock, 10.0e6);
                specAn.ConfigureRF("", CenterHz, 0.0, 0.0);
                specAn.ConfigureIQPowerEdgeTrigger(
                    "", "0", -20.0,
                    RFmxSpecAnMXIQPowerEdgeTriggerSlope.Rising, 0.0,
                    RFmxSpecAnMXTriggerMinimumQuietTimeMode.Manual, 0.0, false);

                specAn.SelectMeasurements("", RFmxSpecAnMXMeasurementTypes.Spectrum, false);
                specAn.Spectrum.Configuration.ConfigureSpan("", SpanHz);
                specAn.Spectrum.Configuration.ConfigureRbwFilter(
                    "", RFmxSpecAnMXSpectrumRbwAutoBandwidth.True,
                    100.0e3, RFmxSpecAnMXSpectrumRbwFilterType.Gaussian);

                specAn.Initiate("", "");

                Spectrum<float> result = null;
                specAn.Spectrum.Results.FetchSpectrum("", Timeout, ref result);

                float[] samples   = result.GetData();
                double  f0        = result.StartFrequency;
                double  df        = result.FrequencyIncrement;

                _freqAxis = new double[samples.Length];
                _psd      = new double[samples.Length];
                for (int k = 0; k < samples.Length; k++)
                {
                    _freqAxis[k] = (f0 + k * df) / 1e9;
                    _psd[k]      = samples[k];
                }

                int    pi  = PeakIndex(_psd);
                _specPanel.Invalidate();
                SetStatus($"Acquired {samples.Length} bins  |  " +
                          $"Peak: {_psd[pi]:F2} dBm @ {_freqAxis[pi]:F6} GHz  |  " +
                          $"{df / 1e3:F1} kHz/bin");
            }
            catch (Exception ex)
            {
                SetStatus("ERROR: " + ex.Message);
                MessageBox.Show(ex.Message, "Acquisition Error",
                                MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                try { specAn?.Dispose();  } catch { }
                try { instr?.Close();     } catch { }
                _acquireBtn.Enabled = true;
            }
        }

        private void CloseRfsg()
        {
            if (_rfsgSession == null) return;
            try { _rfsgSession.RF.OutputEnabled = false; } catch { }
            try { _rfsgSession.Close(); } catch { }
            _rfsgSession = null;
        }

        // ═══════════════════════════════════════════════════════════════════════
        //  RF output indicator
        // ═══════════════════════════════════════════════════════════════════════
        private void RfIndicator_Paint(object sender, PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            var rc  = _rfIndicator.ClientRectangle;
            var col = _rfOutputEnabled ? Color.FromArgb(0, 210, 100) : Color.FromArgb(175, 175, 175);
            using (var b = new SolidBrush(col))
                e.Graphics.FillEllipse(b, 1, 1, rc.Width - 2, rc.Height - 2);
        }

        // ═══════════════════════════════════════════════════════════════════════
        //  Spectrum plot
        // ═══════════════════════════════════════════════════════════════════════
        private void SpecPanel_Paint(object sender, PaintEventArgs e)
        {
            var g  = e.Graphics;
            var rc = _specPanel.ClientRectangle;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            const int mL = 58, mR = 20, mT = 20, mB = 48;
            float pw = rc.Width  - mL - mR;
            float ph = rc.Height - mT - mB;
            if (pw < 10 || ph < 10) return;

            // Axis ranges
            double xMin, xMax, yMin, yMax;
            if (_psd != null && _psd.Length > 1)
            {
                xMin = _freqAxis[0];
                xMax = _freqAxis[_freqAxis.Length - 1];
                double dMax = ArrMax(_psd), dMin = ArrMin(_psd);
                yMax = Math.Ceiling((dMax + 5)  / 10.0) * 10;
                yMin = Math.Floor( (dMin - 10)  / 10.0) * 10;
                if (yMax - yMin < 20) yMax = yMin + 20;
            }
            else { xMin = 0; xMax = 100; yMin = 0; yMax = 100; }

            double xRange = xMax - xMin; if (xRange == 0) xRange = 1;
            double yRange = yMax - yMin; if (yRange == 0) yRange = 1;

            // Plot background
            using (var bg = new SolidBrush(Color.Black))
                g.FillRectangle(bg, mL, mT, pw, ph);

            // Grid
            using (var gp = new Pen(Color.FromArgb(42, 42, 55), 1))
            {
                gp.DashStyle = DashStyle.Dash;
                int xDiv = 10, yDiv = 5;
                for (int i = 0; i <= xDiv; i++)
                {
                    float x = mL + i * pw / xDiv;
                    g.DrawLine(gp, x, mT, x, mT + ph);
                }
                for (int i = 0; i <= yDiv; i++)
                {
                    float y = mT + i * ph / yDiv;
                    g.DrawLine(gp, mL, y, mL + pw, y);
                }
            }

            // Axis border
            using (var ap = new Pen(Color.FromArgb(75, 80, 90), 1))
                g.DrawRectangle(ap, mL, mT, pw, ph);

            // Tick labels + axis titles
            string xFmt = xRange < 0.001 ? "F5" : xRange < 0.01 ? "F4" :
                          xRange < 0.1   ? "F3" : xRange < 1    ? "F2" :
                          xRange < 10    ? "F1" : "F0";

            using (var tf  = new Font("Segoe UI", 8f))
            using (var tb  = new SolidBrush(Color.FromArgb(155, 162, 172)))
            using (var axF = new Font("Segoe UI", 9f))
            using (var axB = new SolidBrush(Color.FromArgb(175, 182, 192)))
            {
                int xDiv = 10, yDiv = 5;

                for (int i = 0; i <= xDiv; i++)
                {
                    double v  = xMin + i * xRange / xDiv;
                    float  px = mL + i * pw / xDiv;
                    string s  = v.ToString(xFmt, CultureInfo.InvariantCulture);
                    var    sz = g.MeasureString(s, tf);
                    g.DrawString(s, tf, tb, px - sz.Width / 2, mT + ph + 5);
                }
                for (int i = 0; i <= yDiv; i++)
                {
                    double v  = yMax - i * yRange / yDiv;
                    float  py = mT + i * ph / yDiv;
                    string s  = v.ToString("F0", CultureInfo.InvariantCulture);
                    var    sz = g.MeasureString(s, tf);
                    g.DrawString(s, tf, tb, mL - sz.Width - 4, py - sz.Height / 2);
                }

                // X axis title
                string xTitle = "Frequency (GHz)";
                var    xTSz   = g.MeasureString(xTitle, axF);
                g.DrawString(xTitle, axF, axB, mL + pw / 2 - xTSz.Width / 2, mT + ph + 28);

                // Y axis title (rotated)
                var sf = new StringFormat { Alignment = StringAlignment.Center };
                g.TranslateTransform(14, mT + ph / 2);
                g.RotateTransform(-90);
                g.DrawString("Power (dBm)", axF, axB, 0, 0, sf);
                g.ResetTransform();
            }

            if (_psd == null || _psd.Length < 2) return;

            // Trace
            var pts = new PointF[_psd.Length];
            for (int k = 0; k < _psd.Length; k++)
            {
                float px = mL + (float)((_freqAxis[k] - xMin) / xRange * pw);
                float py = mT + (float)((yMax - _psd[k])      / yRange * ph);
                py = Math.Max(mT, Math.Min(mT + ph, py));
                pts[k] = new PointF(px, py);
            }

            using (var pen = new Pen(Color.FromArgb(55, 215, 115), 1.5f))
                g.DrawLines(pen, pts);

            // Peak marker
            int   pi   = PeakIndex(_psd);
            float pkX  = pts[pi].X;
            float pkY  = pts[pi].Y;
            using (var yb  = new SolidBrush(Color.Yellow))
            using (var pkF = new Font("Segoe UI", 8f))
            {
                g.FillEllipse(yb, pkX - 4, pkY - 4, 8, 8);
                g.DrawString($"{_psd[pi]:F1} dBm\n{_freqAxis[pi]:F4} GHz",
                             pkF, yb, pkX + 6, pkY - 16);
            }
        }

        // ── Utilities ─────────────────────────────────────────────────────────
        private static int PeakIndex(double[] a)
        {
            int idx = 0;
            for (int i = 1; i < a.Length; i++) if (a[i] > a[idx]) idx = i;
            return idx;
        }
        private static double ArrMax(double[] a) { double m = a[0]; foreach (double v in a) if (v > m) m = v; return m; }
        private static double ArrMin(double[] a) { double m = a[0]; foreach (double v in a) if (v < m) m = v; return m; }

        private void SetStatus(string msg)
        {
            if (InvokeRequired) { Invoke(new Action(() => SetStatus(msg))); return; }
            _statusLabel.Text = msg;
            Application.DoEvents();
        }
    }
}
