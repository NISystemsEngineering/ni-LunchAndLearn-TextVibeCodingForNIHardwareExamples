"""
NI Multi-Instrument Controller
================================
Production-quality Python application for simultaneous control of multiple
NI oscilloscopes (niscope) and waveform generators (nifgen), with a tkinter
GUI, live matplotlib plots, and TDMS file output.

Assumptions:
    - NI-SCOPE and NI-FGEN drivers are installed (NI-DAQmx / IVI drivers).
    - niscope >= 0.9, nifgen >= 0.9 Python bindings are installed.
    - Hardware is accessible via NI-VISA resource strings (e.g., "Dev1").
    - If no hardware is present, the app runs in SIMULATION mode using
      niscope/nifgen simulation sessions (options="Simulate=1,DriverSetup=...").
    - TDMS files are written to the working directory unless changed by user.
    - All scope channels are assumed to have 50Ω or 1MΩ input impedance
      selectable; we default to 1MΩ.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import queue
import datetime
import os
import sys
import traceback
import logging

# ---------------------------------------------------------------------------
# Configure root logger early so all modules share it
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ni_controller")

# ---------------------------------------------------------------------------
# Deferred heavy imports so the GUI can still open if drivers are missing
# ---------------------------------------------------------------------------
try:
    import niscope
    NISCOPE_AVAILABLE = True
except ImportError:
    NISCOPE_AVAILABLE = False
    log.warning("niscope not installed – scope control disabled.")

try:
    import nifgen
    NIFGEN_AVAILABLE = True
except ImportError:
    NIFGEN_AVAILABLE = False
    log.warning("nifgen not installed – fgen control disabled.")

try:
    import nptdms
    from nptdms import TdmsWriter, ChannelObject, RootObject, GroupObject
    NPTDMS_AVAILABLE = True
except ImportError:
    NPTDMS_AVAILABLE = False
    log.warning("nptdms not installed – TDMS output disabled.")

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from instrument_control import ScopeController, FgenController
from data_handler import TdmsDataHandler
from ui_components import (
    ScopeConfigFrame, FgenConfigFrame, InstrumentListPanel, StatusBar
)


# ===========================================================================
# Application entry-point
# ===========================================================================

class NIControllerApp(tk.Tk):
    """
    Root application window.

    Orchestrates the GUI, instrument threads, live plot, and TDMS output.
    """

    def __init__(self):
        super().__init__()
        self.title("NI Multi-Instrument Controller")
        self.geometry("1400x900")
        self.resizable(True, True)

        # Thread-safe queue for waveform data from instrument threads
        self._data_queue: queue.Queue = queue.Queue()

        # Active controller objects {instrument_id: controller}
        self._scope_controllers: dict[str, ScopeController] = {}
        self._fgen_controllers: dict[str, FgenController] = {}

        # Worker threads
        self._threads: list[threading.Thread] = []

        # Stop event shared across all acquisition threads
        self._stop_event = threading.Event()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        log.info("Application started.")

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        """Construct all UI panels."""
        # ── Top menu bar ──────────────────────────────────────────────
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Set TDMS Output Path…", command=self._choose_tdms_path)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        self.config(menu=menubar)

        # ── Main paned layout ─────────────────────────────────────────
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Left panel – instrument configuration
        left_frame = ttk.Frame(paned, width=480)
        paned.add(left_frame, weight=1)

        # Right panel – plot + log
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        # ── Instrument list panel (left) ──────────────────────────────
        self.instrument_panel = InstrumentListPanel(left_frame, app=self)
        self.instrument_panel.pack(fill=tk.BOTH, expand=True)

        # ── Control buttons ───────────────────────────────────────────
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=(4, 0))

        self.btn_run = ttk.Button(btn_frame, text="▶  Run Acquisition",
                                  command=self._start_acquisition)
        self.btn_run.pack(side=tk.LEFT, padx=4, pady=4, expand=True, fill=tk.X)

        self.btn_stop = ttk.Button(btn_frame, text="■  Stop",
                                   command=self._stop_acquisition, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=4, pady=4, expand=True, fill=tk.X)

        # TDMS path display
        tdms_frame = ttk.LabelFrame(left_frame, text="TDMS Output")
        tdms_frame.pack(fill=tk.X, padx=4, pady=4)
        self._tdms_path_var = tk.StringVar(value=os.path.join(os.getcwd(), "acquisition.tdms"))
        ttk.Entry(tdms_frame, textvariable=self._tdms_path_var, state="readonly").pack(
            fill=tk.X, padx=4, pady=2)
        ttk.Button(tdms_frame, text="Browse…", command=self._choose_tdms_path).pack(
            anchor=tk.E, padx=4, pady=2)

        # ── Plot area (right, top) ────────────────────────────────────
        plot_frame = ttk.LabelFrame(right_frame, text="Waveform Plot")
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._build_plot(plot_frame)

        # ── Log / status (right, bottom) ──────────────────────────────
        log_frame = ttk.LabelFrame(right_frame, text="Acquisition Log")
        log_frame.pack(fill=tk.X, padx=4, pady=(0, 4))
        self.log_text = tk.Text(log_frame, height=8, state=tk.DISABLED,
                                bg="#1e1e1e", fg="#d4d4d4", font=("Courier", 9))
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Status bar ────────────────────────────────────────────────
        self.status_bar = StatusBar(self)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _build_plot(self, parent):
        """Embed a matplotlib figure inside *parent*."""
        self._fig = Figure(figsize=(8, 4), dpi=100, facecolor="#2b2b2b")
        self._ax = self._fig.add_subplot(111)
        self._ax.set_facecolor("#1e1e1e")
        self._ax.set_xlabel("Time (s)", color="white")
        self._ax.set_ylabel("Voltage (V)", color="white")
        self._ax.set_title("Acquired Waveforms", color="white")
        self._ax.tick_params(colors="white")
        for spine in self._ax.spines.values():
            spine.set_edgecolor("#555555")
        self._fig.tight_layout()

        self._canvas = FigureCanvasTkAgg(self._fig, master=parent)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar = NavigationToolbar2Tk(self._canvas, parent)
        toolbar.update()

    # ------------------------------------------------------------------
    # TDMS path selection
    # ------------------------------------------------------------------

    def _choose_tdms_path(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".tdms",
            filetypes=[("TDMS files", "*.tdms"), ("All files", "*.*")],
            initialfile="acquisition.tdms",
        )
        if path:
            self._tdms_path_var.set(path)

    # ------------------------------------------------------------------
    # Acquisition lifecycle
    # ------------------------------------------------------------------

    def _start_acquisition(self):
        """Validate configuration, then launch instrument threads."""
        configs = self.instrument_panel.get_all_configs()
        if not configs:
            messagebox.showwarning("No Instruments", "Add at least one instrument before running.")
            return

        self._stop_event.clear()
        self._threads.clear()

        # Clear previous plot
        self._ax.cla()
        self._ax.set_xlabel("Time (s)", color="white")
        self._ax.set_ylabel("Voltage (V)", color="white")
        self._ax.set_title("Acquired Waveforms", color="white")
        self._canvas.draw()

        self.btn_run.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.status_bar.set("Running acquisition…")
        self._log("═" * 60)
        self._log(f"Acquisition started at {datetime.datetime.now().isoformat(timespec='seconds')}")

        scope_configs = [c for c in configs if c["type"] == "scope"]
        fgen_configs  = [c for c in configs if c["type"] == "fgen"]

        # Launch fgens first so signals are present when scopes arm
        for cfg in fgen_configs:
            ctrl = FgenController(cfg, self._data_queue, self._stop_event)
            self._fgen_controllers[cfg["instrument_id"]] = ctrl
            t = threading.Thread(target=self._run_fgen, args=(ctrl,), daemon=True,
                                 name=f"fgen-{cfg['instrument_id']}")
            self._threads.append(t)
            t.start()

        for cfg in scope_configs:
            ctrl = ScopeController(cfg, self._data_queue, self._stop_event)
            self._scope_controllers[cfg["instrument_id"]] = ctrl
            t = threading.Thread(target=self._run_scope, args=(ctrl,), daemon=True,
                                 name=f"scope-{cfg['instrument_id']}")
            self._threads.append(t)
            t.start()

        # Poll the data queue on the main thread
        self.after(200, self._poll_data_queue)

    def _run_scope(self, ctrl: "ScopeController"):
        """Thread worker for one scope controller."""
        try:
            ctrl.connect()
            ctrl.configure()
            ctrl.acquire()
        except Exception as exc:
            self._data_queue.put({
                "type": "error",
                "instrument_id": ctrl.instrument_id,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            })
        finally:
            ctrl.close()
            self._data_queue.put({"type": "done", "instrument_id": ctrl.instrument_id})

    def _run_fgen(self, ctrl: "FgenController"):
        """Thread worker for one fgen controller."""
        try:
            ctrl.connect()
            ctrl.configure()
            ctrl.start_generation()
            # Wait until stop is requested
            self._stop_event.wait()
        except Exception as exc:
            self._data_queue.put({
                "type": "error",
                "instrument_id": ctrl.instrument_id,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            })
        finally:
            ctrl.close()
            self._data_queue.put({"type": "done", "instrument_id": ctrl.instrument_id})

    def _stop_acquisition(self):
        """Signal all threads to stop."""
        self._stop_event.set()
        self.status_bar.set("Stopping…")
        self._log("Stop requested by user.")

    def _poll_data_queue(self):
        """
        Periodically drain the data queue on the main thread to update the
        plot and trigger TDMS writes.
        """
        collected: list[dict] = []
        try:
            while True:
                item = self._data_queue.get_nowait()
                collected.append(item)
        except queue.Empty:
            pass

        waveforms = [i for i in collected if i.get("type") == "waveform"]
        errors    = [i for i in collected if i.get("type") == "error"]
        dones     = [i for i in collected if i.get("type") == "done"]

        if waveforms:
            self._update_plot(waveforms)
            self._write_tdms(waveforms)

        for err in errors:
            self._log(f"[ERROR] {err['instrument_id']}: {err['message']}")
            messagebox.showerror(
                "Instrument Error",
                f"{err['instrument_id']}:\n{err['message']}\n\nSee log for details.",
            )

        for done in dones:
            self._log(f"[DONE] {done['instrument_id']} finished.")

        # Check if all threads are complete
        alive = any(t.is_alive() for t in self._threads)
        if alive or not self._threads:
            self.after(200, self._poll_data_queue)
        else:
            self._acquisition_complete()

    def _acquisition_complete(self):
        """Called when all instrument threads have exited."""
        self.btn_run.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_bar.set("Acquisition complete.")
        self._log("All instruments finished.")
        self._scope_controllers.clear()
        self._fgen_controllers.clear()

    # ------------------------------------------------------------------
    # Plot update
    # ------------------------------------------------------------------

    def _update_plot(self, waveform_items: list[dict]):
        """Redraw axes with newly received waveform data."""
        self._ax.cla()
        self._ax.set_facecolor("#1e1e1e")
        self._ax.set_xlabel("Time (s)", color="white")
        self._ax.set_ylabel("Voltage (V)", color="white")
        self._ax.set_title("Acquired Waveforms", color="white")
        self._ax.tick_params(colors="white")

        colours = plt.cm.tab10.colors  # up to 10 distinct colours

        for idx, item in enumerate(waveform_items):
            label = f"{item['instrument_id']} / {item['channel']}"
            t = item["time_axis"]
            v = item["voltage"]
            self._ax.plot(t, v, color=colours[idx % len(colours)],
                          linewidth=0.8, label=label)

        legend = self._ax.legend(facecolor="#2b2b2b", edgecolor="#555555",
                                  labelcolor="white", fontsize=8)
        self._fig.tight_layout()
        self._canvas.draw()

    # ------------------------------------------------------------------
    # TDMS output
    # ------------------------------------------------------------------

    def _write_tdms(self, waveform_items: list[dict]):
        """Append waveform data to the configured TDMS file."""
        if not NPTDMS_AVAILABLE:
            self._log("[WARN] nptdms not available – skipping TDMS write.")
            return

        path = self._tdms_path_var.get()
        try:
            handler = TdmsDataHandler(path)
            handler.write(waveform_items)
            self._log(f"TDMS written → {path}")
        except Exception as exc:
            self._log(f"[ERROR] TDMS write failed: {exc}")

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log(self, message: str):
        """Append *message* to the on-screen log widget (thread-safe via after)."""
        def _append():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.after(0, _append)

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def _on_close(self):
        """Cleanly shut down threads then destroy the window."""
        if any(t.is_alive() for t in self._threads):
            if not messagebox.askyesno("Confirm Exit",
                                       "Acquisition is running. Stop and exit?"):
                return
            self._stop_event.set()
            for t in self._threads:
                t.join(timeout=5)
        self.destroy()


# ===========================================================================

if __name__ == "__main__":
    app = NIControllerApp()
    app.mainloop()
