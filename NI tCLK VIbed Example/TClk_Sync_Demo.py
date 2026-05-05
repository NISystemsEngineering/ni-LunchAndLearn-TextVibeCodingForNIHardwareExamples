#!/usr/bin/env python3
"""
TClk_Sync_Demo
NI PXIe oscilloscope measurement application with TClk synchronization.
Generates a CW RF signal on a PXIe-5841 VST, then acquires synchronized
waveforms across two scopes using NI-TClk.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import math
import time
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib
matplotlib.use("TkAgg")

# ── Driver availability ────────────────────────────────────────────────────────
try:
    import niscope
    import nitclk
    NISCOPE_AVAILABLE = True
    _VERT_COUPLING = {
        "DC":  niscope.VerticalCoupling.DC,
        "AC":  niscope.VerticalCoupling.AC,
        "GND": niscope.VerticalCoupling.GND,
    }
    _TRIG_SLOPE = {
        "Rising":  niscope.TriggerSlope.POSITIVE,
        "Falling": niscope.TriggerSlope.NEGATIVE,
    }
    _TRIG_COUPLING = {
        "DC":       niscope.TriggerCoupling.DC,
        "AC":       niscope.TriggerCoupling.AC,
        "HF Reject": niscope.TriggerCoupling.HF_REJECT,
        "LF Reject": niscope.TriggerCoupling.LF_REJECT,
    }
except ImportError:
    NISCOPE_AVAILABLE = False
    _VERT_COUPLING = {"DC": "DC", "AC": "AC", "GND": "GND"}
    _TRIG_SLOPE    = {"Rising": "POSITIVE", "Falling": "NEGATIVE"}
    _TRIG_COUPLING = {"DC": "DC", "AC": "AC", "HF Reject": "HF", "LF Reject": "LF"}

try:
    import nirfsg
    NIRFSG_AVAILABLE = True
except ImportError:
    NIRFSG_AVAILABLE = False

# ── Theme ──────────────────────────────────────────────────────────────────────
BG      = "#1c1c2b"
SURFACE = "#252538"
BORDER  = "#3a3a55"
ACCENT  = "#4c9be8"
TEXT    = "#d4d4e8"
DIM     = "#6b6b8f"
SUCCESS = "#56c17f"
ERROR   = "#e85c5c"
WARN    = "#e8a84c"

SCOPE_COLORS     = ["#4c9be8", "#56c17f"]
NUM_SCOPES       = 2
NUM_MEASUREMENTS = 10
DEFAULT_RESOURCES = ["Scope1", "Scope2"]


# ── Main application ───────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TClk_2Scopes  —  NI PXIe Synchronized Measurement")
        self.geometry("1300x840")
        self.minsize(1024, 720)
        self.configure(bg=BG)

        self.sessions: list = []
        self.rf_session = None
        self.running = False
        self._q: queue.Queue = queue.Queue()

        self._apply_style()
        self._build_menu()
        self._build_notebook()
        self._build_statusbar()
        self._poll_queue()

        missing = []
        if not NISCOPE_AVAILABLE:
            missing.append("niscope/nitclk")
        if not NIRFSG_AVAILABLE:
            missing.append("nirfsg")
        if missing:
            self._status(
                f"{', '.join(missing)} not found — running in simulation mode", WARN)

        self.after(100, self._on_connect)

    # ── Style ──────────────────────────────────────────────────────────────────
    def _apply_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure(".", background=BG, foreground=TEXT,
                     fieldbackground=SURFACE, font=("Segoe UI", 10))

        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=SURFACE, foreground=DIM,
                     padding=[18, 8], font=("Segoe UI", 10, "bold"))
        s.map("TNotebook.Tab",
              background=[("selected", BG)],
              foreground=[("selected", ACCENT)])

        s.configure("TFrame",      background=BG)
        s.configure("TLabel",      background=BG, foreground=TEXT)
        s.configure("TEntry",      fieldbackground=SURFACE, foreground=TEXT,
                     insertcolor=TEXT, relief="flat")
        s.configure("TCombobox",   fieldbackground=SURFACE, foreground=TEXT,
                     selectbackground=ACCENT, relief="flat")
        s.map("TCombobox", fieldbackground=[("readonly", SURFACE)])

        s.configure("TLabelframe",       background=BG, relief="solid",
                     bordercolor=BORDER, borderwidth=1)
        s.configure("TLabelframe.Label", background=BG, foreground=DIM,
                     font=("Segoe UI", 9, "bold"))

        s.configure("TButton", background=ACCENT, foreground="#ffffff",
                     relief="flat", padding=[14, 7],
                     font=("Segoe UI", 10, "bold"))
        s.map("TButton",
              background=[("active", "#3a8ad4"), ("disabled", BORDER)],
              foreground=[("disabled", DIM)])

        s.configure("Danger.TButton",  background=ERROR)
        s.map("Danger.TButton",  background=[("active", "#c94444"),
                                              ("disabled", BORDER)])
        s.configure("Success.TButton", background=SUCCESS)
        s.map("Success.TButton", background=[("active", "#45a86a"),
                                              ("disabled", BORDER)])

        s.configure("Treeview", background=SURFACE, foreground=TEXT,
                     fieldbackground=SURFACE, rowheight=26,
                     font=("Segoe UI", 10))
        s.configure("Treeview.Heading", background=BORDER, foreground=TEXT,
                     font=("Segoe UI", 10, "bold"), relief="flat")
        s.map("Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])

        s.configure("TScrollbar", background=SURFACE, troughcolor=BG,
                     relief="flat", borderwidth=0)

    # ── Menu ───────────────────────────────────────────────────────────────────
    def _build_menu(self):
        kw = dict(bg=SURFACE, fg=TEXT, tearoff=False,
                  activebackground=ACCENT, activeforeground="#fff")
        root_menu = tk.Menu(self, **kw)

        file_menu = tk.Menu(root_menu, **kw)
        file_menu.add_command(label="Exit", command=self.on_close)
        root_menu.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(root_menu, **kw)
        help_menu.add_command(label="About", command=self._show_about)
        root_menu.add_cascade(label="Help", menu=help_menu)

        self.config(menu=root_menu)

    # ── Notebook ───────────────────────────────────────────────────────────────
    def _build_notebook(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 0))

        self.cfg_tab = ttk.Frame(self.nb, padding=0)
        self.res_tab = ttk.Frame(self.nb, padding=0)
        self.nb.add(self.cfg_tab, text="  Configuration  ")
        self.nb.add(self.res_tab, text="  Results  ")

        self._build_config_tab()
        self._build_results_tab()

    # ══════════════════════════════════════════════════════════════════════════
    # Configuration Tab
    # ══════════════════════════════════════════════════════════════════════════
    def _build_config_tab(self):
        outer = ttk.Frame(self.cfg_tab)
        outer.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        outer.columnconfigure((0, 1, 2, 3), weight=1)

        # Row 0 — RF signal generator
        self._rf_vars = self._build_section(outer, "  RF Signal Generator  ",
                                             0, 0, self._populate_rf,
                                             columnspan=4)

        # Row 1 — scope resource names
        self._build_resources_frame(outer)

        # Row 2 — four settings columns
        self._vert_vars  = self._build_section(outer, "  Vertical  ",
                                                2, 0, self._populate_vertical)
        self._horiz_vars = self._build_section(outer, "  Horizontal  ",
                                                2, 1, self._populate_horizontal)
        self._trig_vars  = self._build_section(outer, "  Trigger  ",
                                                2, 2, self._populate_trigger)
        self._tclk_vars  = self._build_section(outer, "  TClk  ",
                                                2, 3, self._populate_tclk)

        # Row 3 — action buttons
        self._build_buttons(outer)

    # ── Scope resources ────────────────────────────────────────────────────────
    def _build_resources_frame(self, parent):
        lf = ttk.LabelFrame(parent, text="  Scope Resources  ", padding=12)
        lf.grid(row=1, column=0, columnspan=4, sticky="ew",
                padx=(0, 0), pady=(0, 12))

        self.resource_vars = []
        self.channel_vars  = []

        for i in range(NUM_SCOPES):
            col = i * 4
            color_dot = tk.Label(lf, text="●", fg=SCOPE_COLORS[i], bg=BG,
                                  font=("Segoe UI", 14))
            color_dot.grid(row=0, column=col, rowspan=2, padx=(4, 6), pady=4)

            ttk.Label(lf, text=f"Scope {i+1} Resource:").grid(
                row=0, column=col+1, sticky="w", padx=(0, 4))
            r_var = tk.StringVar(value=DEFAULT_RESOURCES[i])
            self.resource_vars.append(r_var)
            ttk.Entry(lf, textvariable=r_var, width=16).grid(
                row=0, column=col+2, sticky="ew", padx=(0, 20), pady=3)

            ttk.Label(lf, text="Channel:").grid(
                row=1, column=col+1, sticky="w", padx=(0, 4))
            ch_var = tk.StringVar(value="0")
            self.channel_vars.append(ch_var)
            ttk.Combobox(lf, textvariable=ch_var, width=5,
                         values=["0", "1", "2", "3"],
                         state="readonly").grid(
                row=1, column=col+2, sticky="w", padx=(0, 20), pady=3)

    # ── Generic labeled section ────────────────────────────────────────────────
    def _build_section(self, parent, title, row, col, populate_fn, columnspan=1):
        lf = ttk.LabelFrame(parent, text=title, padding=14)
        lf.grid(row=row, column=col, columnspan=columnspan, sticky="nsew",
                padx=(0, 8) if (col + columnspan - 1) < 3 else (0, 0),
                pady=(0, 12))
        lf.columnconfigure(1, weight=1)
        vars_ = {}
        populate_fn(lf, vars_)
        return vars_

    # ── Vertical settings ──────────────────────────────────────────────────────
    def _populate_vertical(self, parent, v):
        rows = [
            ("Range (V):",        "range",    "1.0"),
            ("Offset (V):",       "offset",   "0.0"),
            ("Probe Atten.:",     "probe",    "1.0"),
        ]
        for i, (lbl, key, default) in enumerate(rows):
            ttk.Label(parent, text=lbl).grid(
                row=i, column=0, sticky="w", pady=5, padx=(0, 8))
            var = tk.StringVar(value=default)
            v[key] = var
            ttk.Entry(parent, textvariable=var, width=10).grid(
                row=i, column=1, sticky="ew", pady=5)

        ttk.Label(parent, text="Coupling:").grid(
            row=3, column=0, sticky="w", pady=5)
        var = tk.StringVar(value="DC")
        v["coupling"] = var
        ttk.Combobox(parent, textvariable=var, width=9,
                     values=["DC", "AC", "GND"],
                     state="readonly").grid(row=3, column=1, sticky="ew", pady=5)

    @staticmethod
    def _to_eng_str(value: float) -> str:
        """Format a float in engineering notation (exponent a multiple of 3)."""
        if value == 0:
            return "0"
        exp  = int(math.floor(math.log10(abs(value))))
        exp3 = exp - (exp % 3)
        mantissa = value / (10 ** exp3)
        return f"{mantissa:g}e{exp3}" if exp3 != 0 else f"{mantissa:g}"

    # ── Horizontal settings ────────────────────────────────────────────────────
    def _populate_horizontal(self, parent, v):
        rows = [
            ("Sample Rate (S/s):", "sample_rate",    "250e6"),
            ("Record Length:",     "record_length",  "10"),
            ("Ref Position (%):",  "ref_pos",        "50.0"),
            ("Num Records:",       "num_records",    "1"),
        ]
        for i, (lbl, key, default) in enumerate(rows):
            ttk.Label(parent, text=lbl).grid(
                row=i, column=0, sticky="w", pady=5, padx=(0, 8))
            var = tk.StringVar(value=default)
            v[key] = var
            entry = ttk.Entry(parent, textvariable=var, width=10)
            entry.grid(row=i, column=1, sticky="ew", pady=5)
            if key == "sample_rate":
                entry.bind("<FocusOut>", lambda e, sv=var: sv.set(
                    self._to_eng_str(float(sv.get()))
                    if sv.get() else sv.get()))

    # ── Trigger settings ───────────────────────────────────────────────────────
    def _populate_trigger(self, parent, v):
        ttk.Label(parent, text="Source (ch):").grid(
            row=0, column=0, sticky="w", pady=5, padx=(0, 8))
        var = tk.StringVar(value="0")
        v["source"] = var
        ttk.Entry(parent, textvariable=var, width=10).grid(
            row=0, column=1, sticky="ew", pady=5)

        ttk.Label(parent, text="Level (V):").grid(
            row=1, column=0, sticky="w", pady=5)
        var = tk.StringVar(value="0.01")
        v["level"] = var
        ttk.Entry(parent, textvariable=var, width=10).grid(
            row=1, column=1, sticky="ew", pady=5)

        ttk.Label(parent, text="Slope:").grid(row=2, column=0, sticky="w", pady=5)
        var = tk.StringVar(value="Rising")
        v["slope"] = var
        ttk.Combobox(parent, textvariable=var, width=9,
                     values=["Rising", "Falling"],
                     state="readonly").grid(row=2, column=1, sticky="ew", pady=5)

        ttk.Label(parent, text="Coupling:").grid(row=3, column=0, sticky="w", pady=5)
        var = tk.StringVar(value="DC")
        v["coupling"] = var
        ttk.Combobox(parent, textvariable=var, width=9,
                     values=["DC", "AC", "HF Reject", "LF Reject"],
                     state="readonly").grid(row=3, column=1, sticky="ew", pady=5)

    # ── TClk settings ──────────────────────────────────────────────────────────
    def _populate_tclk(self, parent, v):
        fields = [
            ("Sample Clk Src:",  "sample_clk_src",  "SampleClockTimebase"),
            ("Sync Pulse Src:",  "sync_pulse_src",   ""),
            ("Min TClk Period:", "min_tclk_period",  "0.0"),
            ("Timeout (s):",     "timeout",          "10.0"),
        ]
        for i, (lbl, key, default) in enumerate(fields):
            ttk.Label(parent, text=lbl).grid(
                row=i, column=0, sticky="w", pady=5, padx=(0, 8))
            var = tk.StringVar(value=default)
            v[key] = var
            ttk.Entry(parent, textvariable=var, width=14).grid(
                row=i, column=1, sticky="ew", pady=5)

        parent.columnconfigure(1, weight=1)

    # ── RF Signal Generator settings ──────────────────────────────────────────
    def _populate_rf(self, parent, v):
        fields = [
            ("Resource:",       "resource",  "5841_8"),
            ("Frequency (Hz):", "frequency", "20e6"),
            ("Level (dBm):",    "level",     "0.0"),
        ]
        for i, (lbl, key, default) in enumerate(fields):
            ttk.Label(parent, text=lbl).grid(
                row=i, column=0, sticky="w", pady=5, padx=(0, 8))
            var = tk.StringVar(value=default)
            v[key] = var
            entry = ttk.Entry(parent, textvariable=var, width=14)
            entry.grid(row=i, column=1, sticky="w", pady=5)
            if key == "frequency":
                entry.bind("<FocusOut>", lambda e, sv=var: sv.set(
                    self._to_eng_str(float(sv.get()))
                    if sv.get() else sv.get()))

        parent.columnconfigure(1, weight=0)

    # ── Action buttons ─────────────────────────────────────────────────────────
    def _build_buttons(self, parent):
        frame = ttk.Frame(parent)
        frame.grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 0))

        self.connect_btn = ttk.Button(
            frame, text="Connect", command=self._on_connect)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.disconnect_btn = ttk.Button(
            frame, text="Disconnect", command=self._on_disconnect,
            style="Danger.TButton", state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Separator(frame, orient="vertical").pack(
            side=tk.LEFT, fill=tk.Y, padx=8)

        self.run_notclk_btn = ttk.Button(
            frame, text="Run without TClk",
            command=lambda: self._on_run(use_tclk=False),
            style="Success.TButton", state=tk.DISABLED)
        self.run_notclk_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.run_tclk_btn = ttk.Button(
            frame, text="Run with TClk",
            command=lambda: self._on_run(use_tclk=True),
            style="Success.TButton", state=tk.DISABLED)
        self.run_tclk_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = ttk.Button(
            frame, text="Stop", command=self._on_stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)

    # ══════════════════════════════════════════════════════════════════════════
    # Results Tab
    # ══════════════════════════════════════════════════════════════════════════
    def _build_results_tab(self):
        self.res_tab.rowconfigure(0, weight=5)
        self.res_tab.rowconfigure(1, weight=1)
        self.res_tab.columnconfigure(0, weight=1)

        # ── Waveform plots ─────────────────────────────────────────────────────
        plot_outer = ttk.Frame(self.res_tab)
        plot_outer.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        plot_outer.rowconfigure(0, weight=1)
        plot_outer.columnconfigure(0, weight=1)

        self.fig = Figure(facecolor=BG)
        self.fig.subplots_adjust(left=0.09, right=0.97, top=0.91, bottom=0.11)

        ax = self.fig.add_subplot(1, 1, 1)
        ax.set_facecolor(SURFACE)
        ax.tick_params(colors=DIM, labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
        ax.set_title("Synchronized Waveforms",
                     color=TEXT, fontsize=10, loc="left", pad=6)
        ax.set_ylabel("Amplitude (V)", color=DIM, fontsize=9)
        ax.set_xlabel("Time (s)", color=DIM, fontsize=9)
        ax.grid(True, color=BORDER, linewidth=0.5, linestyle="--", alpha=0.7)
        self.ax = ax

        self.lines = [
            ax.plot([], [], color=SCOPE_COLORS[i], linewidth=0.9,
                    label=DEFAULT_RESOURCES[i])[0]
            for i in range(NUM_SCOPES)
        ]
        self.legend = ax.legend(
            facecolor=SURFACE, edgecolor=BORDER,
            labelcolor=TEXT, fontsize=9)

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_outer)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        tb_frame = tk.Frame(plot_outer, bg=SURFACE)
        tb_frame.grid(row=1, column=0, sticky="ew")
        toolbar = NavigationToolbar2Tk(self.canvas, tb_frame)
        toolbar.config(bg=SURFACE)
        toolbar.update()

        # ── ΔT Statistics panel ────────────────────────────────────────────────
        stats_lf = ttk.LabelFrame(
            self.res_tab, text="  Trigger Timing Statistics  ", padding=14)
        stats_lf.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        stats_lf.columnconfigure(0, weight=2)
        for col in range(1, 5):
            stats_lf.columnconfigure(col, weight=3)

        # Header: threshold and scope names (updated on connect)
        self._stats_title = tk.Label(
            stats_lf, text="ΔT at 0.1 V rising",
            fg=DIM, bg=BG, font=("Segoe UI", 10))
        self._stats_title.grid(row=0, column=0, columnspan=5, pady=(0, 8))

        # Column headings
        for col, heading in enumerate(
                ["", "MIN  ΔT", "MAX  ΔT", "STD DEV  ΔT", "N"], 0):
            tk.Label(stats_lf, text=heading, fg=DIM, bg=BG,
                     font=("Segoe UI", 9, "bold")).grid(
                row=1, column=col, pady=(0, 6), padx=8)

        # One row per sync mode
        for row, (mode_lbl, suffix) in enumerate(
                [("Without TClk", "notclk"), ("With TClk", "tclk")], start=2):
            tk.Label(stats_lf, text=mode_lbl, fg=TEXT, bg=BG,
                     font=("Segoe UI", 11, "bold"), anchor="w").grid(
                row=row, column=0, sticky="w", padx=(4, 16), pady=6)
            for col, attr in enumerate(
                    [f"_lbl_min_{suffix}", f"_lbl_max_{suffix}",
                     f"_lbl_std_{suffix}", f"_lbl_n_{suffix}"], start=1):
                lbl = tk.Label(stats_lf, text="—", fg=DIM, bg=BG,
                               font=("Segoe UI", 20, "bold"))
                lbl.grid(row=row, column=col, pady=4, padx=8)
                setattr(self, attr, lbl)

    # ── Status bar ─────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        bar = tk.Frame(self, bg=SURFACE, height=28)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        self._dot = tk.Label(bar, text="●", fg=DIM, bg=SURFACE,
                              font=("Segoe UI", 12))
        self._dot.pack(side=tk.LEFT, padx=(10, 4))

        self._status_lbl = tk.Label(
            bar, text="Ready", fg=DIM, bg=SURFACE,
            font=("Segoe UI", 9), anchor="w")
        self._status_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._conn_lbl = tk.Label(
            bar, text="Not connected", fg=DIM, bg=SURFACE,
            font=("Segoe UI", 9))
        self._conn_lbl.pack(side=tk.RIGHT, padx=12)

    def _status(self, msg: str, color: str = DIM):
        self._status_lbl.config(text=msg)
        self._dot.config(fg=color)

    # ── Queue for thread-safe UI updates ───────────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                self._q.get_nowait()()
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    def _post(self, fn):
        self._q.put(fn)

    # ══════════════════════════════════════════════════════════════════════════
    # Connection logic
    # ══════════════════════════════════════════════════════════════════════════
    def _on_connect(self):
        resources = [v.get().strip() for v in self.resource_vars]
        if not all(resources):
            messagebox.showwarning(
                "Missing Resources",
                "Please enter a resource name for all three scopes.")
            return

        self._status("Connecting…", WARN)
        self.connect_btn.config(state=tk.DISABLED)

        def _worker():
            try:
                sessions = []
                for res in resources:
                    s = (niscope.Session(res) if NISCOPE_AVAILABLE
                         else _SimSession(res))
                    sessions.append(s)
                rf_res = self._rf_vars["resource"].get().strip()
                rf = (nirfsg.Session(rf_res) if NIRFSG_AVAILABLE
                      else _SimRFSGSession(rf_res))
                self._post(lambda s=sessions, r=rf: self._on_connected(s, r, resources))
            except Exception as exc:
                self._post(lambda e=exc: self._on_connect_error(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_connected(self, sessions, rf_session, resources):
        self.sessions = sessions
        self.rf_session = rf_session
        rf_res = self._rf_vars["resource"].get().strip()
        self._status(f"Connected: {', '.join(resources)}, {rf_res}", SUCCESS)
        self._conn_lbl.config(
            text=f"Connected ({NUM_SCOPES} scopes + RF)", fg=SUCCESS)
        self.connect_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.NORMAL)
        self._set_run_btns(tk.NORMAL)
        self._scope_resources = resources
        for i, line in enumerate(self.lines):
            line.set_label(resources[i])
        self.legend = self.ax.legend(
            facecolor=SURFACE, edgecolor=BORDER,
            labelcolor=TEXT, fontsize=9)
        self.canvas.draw()

    def _on_connect_error(self, exc):
        self._status(f"Connection failed: {exc}", ERROR)
        self.connect_btn.config(state=tk.NORMAL)
        messagebox.showerror("Connection Error", str(exc))

    def _on_disconnect(self):
        for s in self.sessions:
            try:
                s.close()
            except Exception:
                pass
        self.sessions.clear()
        if self.rf_session is not None:
            try:
                self.rf_session.abort()
                self.rf_session.close()
            except Exception:
                pass
            self.rf_session = None
        self.running = False
        self._status("Disconnected", DIM)
        self._conn_lbl.config(text="Not connected", fg=DIM)
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self._set_run_btns(tk.DISABLED)
        self.stop_btn.config(state=tk.DISABLED)

    # ══════════════════════════════════════════════════════════════════════════
    # Measurement logic
    # ══════════════════════════════════════════════════════════════════════════
    def _set_run_btns(self, state):
        self.run_notclk_btn.config(state=state)
        self.run_tclk_btn.config(state=state)

    def _on_run(self, use_tclk: bool):
        if not self.sessions:
            return
        self.running = True
        self._set_run_btns(tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        mode = "TClk" if use_tclk else "backplane trigger"
        self._status(f"Starting measurement ({mode})…", WARN)
        threading.Thread(target=self._measure_thread, args=(use_tclk,),
                         daemon=True).start()

    def _on_stop(self):
        self.running = False
        self.stop_btn.config(state=tk.DISABLED)
        self._set_run_btns(tk.NORMAL if self.sessions else tk.DISABLED)
        self._status("Stopped", DIM)

    def _measure_thread(self, use_tclk: bool):
        try:
            self._post(lambda: self._status("Starting RF signal…", WARN))
            self._start_rf()
            if not self.running:
                return

            self._post(lambda: self._status("Configuring scopes…", WARN))
            cfg = self._collect_config()
            self._configure_sessions(cfg)

            delta_ts     = []
            last_results = None
            threshold    = 0.1

            self._post(self._clear_chart)

            for i in range(NUM_MEASUREMENTS):
                if not self.running:
                    break
                n = i + 1
                self._post(lambda n=n: self._status(
                    f"Measurement {n} of {NUM_MEASUREMENTS}…", WARN))

                if use_tclk:
                    self._tclk_initiate(cfg)
                else:
                    self._backplane_initiate(cfg)
                results      = self._fetch_all(cfg)
                last_results = results

                crossings = [
                    self._rising_crossing_time(r["t"], r["y"], threshold)
                    for r in results
                ]
                if all(c is not None for c in crossings):
                    delta_ts.append(crossings[1] - crossings[0])

                self._post(lambda r=results: self._add_waveforms(r))
                if not use_tclk:
                    time.sleep(1.0)

            mode_str = "TClk" if use_tclk else "backplane trigger"
            if last_results is not None:
                self._post(lambda r=last_results, dts=list(delta_ts), tc=use_tclk:
                           self._update_measurements(r, dts, threshold, tc))
            self._post(lambda m=mode_str: self._status(
                f"Complete — {NUM_MEASUREMENTS} measurements ({m})", SUCCESS))

        except Exception as exc:
            self._post(lambda e=exc: self._status(f"Error: {e}", ERROR))
            self._post(lambda e=exc: messagebox.showerror(
                "Measurement Error", str(e)))
        finally:
            self._post(lambda: self.stop_btn.config(state=tk.DISABLED))
            if not use_tclk:
                self._post(self._on_disconnect)
            else:
                self._post(lambda: self._set_run_btns(
                    tk.NORMAL if self.sessions else tk.DISABLED))
            self.running = False

    def _collect_config(self):
        return {
            "channels":      [v.get() for v in self.channel_vars],
            "resources":     [v.get() for v in self.resource_vars],
            "range":         float(self._vert_vars["range"].get()),
            "offset":        float(self._vert_vars["offset"].get()),
            "probe":         float(self._vert_vars["probe"].get()),
            "vert_coupling": self._vert_vars["coupling"].get(),
            "sample_rate":   float(self._horiz_vars["sample_rate"].get()),
            "record_length": int(self._horiz_vars["record_length"].get()),
            "ref_pos":       float(self._horiz_vars["ref_pos"].get()),
            "num_records":   int(self._horiz_vars["num_records"].get()),
            "trig_source":   self._trig_vars["source"].get(),
            "trig_level":    float(self._trig_vars["level"].get()),
            "trig_slope":    self._trig_vars["slope"].get(),
            "trig_coupling": self._trig_vars["coupling"].get(),
            "tclk_timeout":       float(self._tclk_vars["timeout"].get()),
            "min_tclk_period":    float(self._tclk_vars["min_tclk_period"].get()),
        }

    def _configure_sessions(self, cfg):
        vert_coup  = _VERT_COUPLING[cfg["vert_coupling"]]
        trig_slope = _TRIG_SLOPE[cfg["trig_slope"]]
        trig_coup  = _TRIG_COUPLING[cfg["trig_coupling"]]

        for i, session in enumerate(self.sessions):
            ch = cfg["channels"][i]
            session.channels[ch].configure_vertical(cfg["range"], vert_coup)
            session.channels[ch].probe_attenuation = cfg["probe"]
            session.configure_horizontal_timing(
                cfg["sample_rate"], cfg["record_length"],
                cfg["ref_pos"], cfg["num_records"], True)
            session.configure_trigger_edge(
                cfg["trig_source"], cfg["trig_level"],
                trig_coup, trig_slope)

    def _tclk_initiate(self, cfg):
        if NISCOPE_AVAILABLE:
            nitclk.configure_for_homogeneous_triggers(self.sessions)
            nitclk.synchronize(self.sessions, cfg["min_tclk_period"])
            nitclk.initiate(self.sessions)
        else:
            for s in self.sessions:
                s.initiate()

    def _backplane_initiate(self, cfg):
        """Synchronize using PXI backplane reference trigger.

        The master detects the analog edge and exports it to PXI_Trig0.
        The slave arms simultaneously and stamps its trigger when PXI_Trig0
        fires, so both scopes share the exact same trigger event. Jitter is
        limited only to backplane propagation delay rather than each scope
        independently detecting the analog threshold.
        """
        if NISCOPE_AVAILABLE:
            trig_slope = _TRIG_SLOPE[cfg["trig_slope"]]
            trig_coup  = _TRIG_COUPLING[cfg["trig_coupling"]]
            master, slave = self.sessions[0], self.sessions[1]

            # Master: detect the analog edge; export it as a reference trigger
            master.configure_trigger_edge(
                cfg["trig_source"], cfg["trig_level"], trig_coup, trig_slope)
            master.exported_ref_trigger_output_terminal = "PXI_Trig0"

            # Slave: use the exported reference trigger from the backplane
            slave.configure_trigger_digital("PXI_Trig0", trig_slope)

            # Arm both scopes before the trigger fires so they record together
            slave.initiate()
            master.initiate()
        else:
            for s in self.sessions:
                s.initiate()

    def _start_rf(self):
        s = self.rf_session
        if s is None:
            return
        freq  = float(self._rf_vars["frequency"].get())
        level = float(self._rf_vars["level"].get())
        if NIRFSG_AVAILABLE:
            s.generation_mode    = nirfsg.GenerationMode.CW
            s.frequency          = freq
            s.power_level        = level
            s.output_enabled     = True
        else:
            s.frequency  = freq
            s.power_level = level
        s.initiate()

    def _fetch_all(self, cfg):
        results = []
        for i, session in enumerate(self.sessions):
            ch = cfg["channels"][i]
            wfms = session.channels[ch].fetch(
                num_samples=cfg["record_length"],
                timeout=cfg["tclk_timeout"])
            wfm = wfms[0]
            n   = len(wfm.samples)
            t   = wfm.relative_initial_x + np.arange(n) * wfm.x_increment
            results.append({
                "scope":    i + 1,
                "resource": cfg["resources"][i],
                "channel":  ch,
                "t":        t,
                "y":        np.asarray(wfm.samples, dtype=float),
            })
        return results

    # ── Display update (main thread) ───────────────────────────────────────────
    def _clear_chart(self):
        """Clear the axes and restore styling before a new run."""
        self.ax.cla()
        self.ax.set_facecolor(SURFACE)
        self.ax.tick_params(colors=DIM, labelsize=8)
        for spine in self.ax.spines.values():
            spine.set_edgecolor(BORDER)
        self.ax.set_title("Synchronized Waveforms",
                           color=TEXT, fontsize=10, loc="left", pad=6)
        self.ax.set_ylabel("Amplitude (V)", color=DIM, fontsize=9)
        self.ax.set_xlabel("Time (s)", color=DIM, fontsize=9)
        self.ax.grid(True, color=BORDER, linewidth=0.5, linestyle="--", alpha=0.7)
        # Invisible seed lines so the legend always shows both scope names
        resources = getattr(self, "_scope_resources", DEFAULT_RESOURCES)
        self.lines = [
            self.ax.plot([], [], color=SCOPE_COLORS[i], linewidth=0.9,
                         label=resources[i])[0]
            for i in range(NUM_SCOPES)
        ]
        self.legend = self.ax.legend(
            facecolor=SURFACE, edgecolor=BORDER, labelcolor=TEXT, fontsize=9)
        self.canvas.draw()

    def _add_waveforms(self, results):
        """Add one acquisition's waveforms to the chart without clearing it."""
        for i, r in enumerate(results):
            self.ax.plot(r["t"], r["y"],
                         color=SCOPE_COLORS[i], linewidth=0.8, alpha=0.6)
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw()
        self.nb.select(self.res_tab)

    def _update_measurements(self, results, delta_ts, threshold, use_tclk=True):
        """Update the appropriate stats row after all runs complete."""
        res0, res1 = results[0]["resource"], results[1]["resource"]
        self._stats_title.config(
            text=f"ΔT at {threshold} V rising   ({res0} → {res1})")

        suffix = "tclk" if use_tclk else "notclk"
        lbl_min = getattr(self, f"_lbl_min_{suffix}")
        lbl_max = getattr(self, f"_lbl_max_{suffix}")
        lbl_std = getattr(self, f"_lbl_std_{suffix}")
        lbl_n   = getattr(self, f"_lbl_n_{suffix}")

        if delta_ts:
            dts_ns = [dt * 1e9 for dt in delta_ts]
            lbl_min.config(text=f"{min(dts_ns):.3f} ns",             fg=ACCENT)
            lbl_max.config(text=f"{max(dts_ns):.3f} ns",             fg=ACCENT)
            lbl_std.config(text=f"{float(np.std(dts_ns)):.3f} ns",   fg=ACCENT)
            lbl_n.config(  text=str(len(dts_ns)),                     fg=ACCENT)
        else:
            for lbl in (lbl_min, lbl_max, lbl_std, lbl_n):
                lbl.config(text="no crossing", fg=WARN)

    @staticmethod
    def _rising_crossing_time(t: np.ndarray, y: np.ndarray,
                               threshold: float) -> float | None:
        """Return time of first rising crossing at threshold (linear interpolation)."""
        below = y < threshold
        for i in range(len(y) - 1):
            if below[i] and not below[i + 1]:
                frac = (threshold - y[i]) / (y[i + 1] - y[i])
                return float(t[i] + frac * (t[i + 1] - t[i]))
        return None

    # ── Misc ───────────────────────────────────────────────────────────────────
    def _show_about(self):
        messagebox.showinfo(
            "About TClk_2Scopes",
            "TClk_2Scopes\n\n"
            "NI PXIe oscilloscope measurement application.\n"
            "Acquires synchronized waveforms across two scopes\n"
            "using NI-TClk for hardware-level synchronization.\n\n"
            "Requires: niscope, nitclk, numpy, matplotlib")

    def on_close(self):
        self.running = False
        for s in self.sessions:
            try:
                s.close()
            except Exception:
                pass
        if self.rf_session is not None:
            try:
                self.rf_session.abort()
                self.rf_session.close()
            except Exception:
                pass
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
# Simulation stubs (used when niscope is not installed)
# ══════════════════════════════════════════════════════════════════════════════
class _SimWaveform:
    """Mimics a niscope WaveformInfo for offline testing."""
    def __init__(self, num_samples: int, sample_rate: float, index: int):
        rng  = np.random.default_rng(seed=index * 42)
        freq = rng.uniform(1e6, 8e6)
        amp  = rng.uniform(1.5, 4.5)
        noise = rng.uniform(0.02, 0.08)
        t = np.linspace(0.0, num_samples / sample_rate, num_samples)
        self.samples           = amp * np.sin(2 * np.pi * freq * t) \
                                 + noise * rng.standard_normal(num_samples)
        self.relative_initial_x = 0.0
        self.x_increment        = 1.0 / sample_rate


class _SimChannels:
    def __init__(self, session):
        self._session = session
        self._ch      = "0"

    def __getitem__(self, key):
        self._ch = str(key)
        return self

    def configure_vertical(self, *a, **kw):
        pass

    @property
    def probe_attenuation(self):
        return 1.0

    @probe_attenuation.setter
    def probe_attenuation(self, v):
        pass

    def fetch(self, num_samples=10000, timeout=10.0):
        return [_SimWaveform(num_samples,
                             self._session._sample_rate,
                             self._session._index)]


class _SimSession:
    """Offline stub that generates synthetic waveforms."""
    _counter = 0

    def __init__(self, resource: str):
        self.resource     = resource
        self._sample_rate = 1e8
        self._index       = _SimSession._counter
        _SimSession._counter += 1
        self.channels     = _SimChannels(self)

    def configure_horizontal_timing(self, sample_rate, record_length,
                                     ref_pos, num_records, enforce_realtime):
        self._sample_rate = sample_rate

    def configure_trigger_edge(self, *a, **kw):
        pass

    def initiate(self):
        pass

    def close(self):
        pass


# ── Entry point ────────────────────────────────────────────────────────────────
class _SimRFSGSession:
    """Offline stub for nirfsg."""
    def __init__(self, resource: str):
        self.resource     = resource
        self.frequency    = 20e6
        self.power_level  = 0.0

    def initiate(self): pass
    def abort(self):    pass
    def close(self):    pass


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
