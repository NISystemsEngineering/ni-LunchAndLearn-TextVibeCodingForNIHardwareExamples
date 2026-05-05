"""
ui_components.py
================
Reusable tkinter widgets for instrument configuration.

Classes
-------
ScopeConfigFrame   – configuration panel for one NI-SCOPE instrument.
FgenConfigFrame    – configuration panel for one NI-FGEN instrument.
InstrumentListPanel – scrollable container that manages multiple config frames.
StatusBar          – thin status bar at the bottom of the main window.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from main import NIControllerApp

# Colour palette (matches dark plot background)
BG_DARK  = "#2b2b2b"
BG_MED   = "#3c3f41"
FG_LIGHT = "#ffffff"

# Counter used to generate unique IDs
_scope_counter = 0
_fgen_counter  = 0


def _next_scope_id() -> str:
    global _scope_counter
    _scope_counter += 1
    return f"scope_{_scope_counter}"


def _next_fgen_id() -> str:
    global _fgen_counter
    _fgen_counter += 1
    return f"fgen_{_fgen_counter}"


# ===========================================================================
# Scope configuration frame
# ===========================================================================

class ScopeConfigFrame(ttk.LabelFrame):
    """
    A collapsible configuration panel for a single NI-SCOPE instrument.

    Exposes :meth:`get_config` which returns a validated dict ready for
    :class:`ScopeController`.
    """

    TRIGGER_TYPES  = ["Immediate", "Edge", "Software"]
    TRIGGER_SLOPES = ["Positive", "Negative"]

    def __init__(self, parent, instrument_id: str,
                 remove_callback: Callable[[], None], **kwargs):
        super().__init__(parent, text=f"📡  Scope – {instrument_id}", **kwargs)
        self._id = instrument_id
        self._remove_cb = remove_callback
        self._build()

    def _build(self):
        """Create all input widgets."""
        pad = {"padx": 6, "pady": 2}

        # ── Row 0: resource name + simulate ──────────────────────────
        r = 0
        ttk.Label(self, text="Resource Name:").grid(row=r, column=0, sticky=tk.W, **pad)
        self._resource_var = tk.StringVar(value="Scope1")
        ttk.Entry(self, textvariable=self._resource_var, width=14).grid(
            row=r, column=1, sticky=tk.EW, **pad)
        self._simulate_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Simulate", variable=self._simulate_var).grid(
            row=r, column=2, sticky=tk.W, **pad)

        # ── Row 1: channels ───────────────────────────────────────────
        r = 1
        ttk.Label(self, text="Channels (CSV):").grid(row=r, column=0, sticky=tk.W, **pad)
        self._channels_var = tk.StringVar(value="0,1")
        ttk.Entry(self, textvariable=self._channels_var, width=14).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 2: sample rate ────────────────────────────────────────
        r = 2
        ttk.Label(self, text="Sample Rate (S/s):").grid(row=r, column=0, sticky=tk.W, **pad)
        self._sample_rate_var = tk.StringVar(value="1000000")
        ttk.Entry(self, textvariable=self._sample_rate_var, width=14).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 3: voltage range ──────────────────────────────────────
        r = 3
        ttk.Label(self, text="Voltage Range (V):").grid(row=r, column=0, sticky=tk.W, **pad)
        self._vrange_var = tk.StringVar(value="5.0")
        ttk.Entry(self, textvariable=self._vrange_var, width=14).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 4: duration ───────────────────────────────────────────
        r = 4
        ttk.Label(self, text="Duration (s):").grid(row=r, column=0, sticky=tk.W, **pad)
        self._duration_var = tk.StringVar(value="0.05")
        ttk.Entry(self, textvariable=self._duration_var, width=14).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 5: trigger type ───────────────────────────────────────
        r = 5
        ttk.Label(self, text="Trigger Type:").grid(row=r, column=0, sticky=tk.W, **pad)
        self._ttype_var = tk.StringVar(value="Edge")
        ttk.Combobox(self, textvariable=self._ttype_var,
                     values=self.TRIGGER_TYPES, state="readonly", width=12).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 6: trigger source ─────────────────────────────────────
        r = 6
        ttk.Label(self, text="Trigger Source:").grid(row=r, column=0, sticky=tk.W, **pad)
        self._tsource_var = tk.StringVar(value="0")
        ttk.Entry(self, textvariable=self._tsource_var, width=14).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 7: trigger level + slope ──────────────────────────────
        r = 7
        ttk.Label(self, text="Trigger Level (V):").grid(row=r, column=0, sticky=tk.W, **pad)
        self._tlevel_var = tk.StringVar(value="0.5")
        ttk.Entry(self, textvariable=self._tlevel_var, width=7).grid(
            row=r, column=1, sticky=tk.EW, **pad)
        self._tslope_var = tk.StringVar(value="Positive")
        ttk.Combobox(self, textvariable=self._tslope_var,
                     values=self.TRIGGER_SLOPES, state="readonly", width=10).grid(
            row=r, column=2, sticky=tk.EW, **pad)

        # ── Row 8: remove button ──────────────────────────────────────
        r = 8
        ttk.Button(self, text="✕ Remove", command=self._remove_cb).grid(
            row=r, column=2, sticky=tk.E, **pad)

        self.columnconfigure(1, weight=1)

    def get_config(self) -> dict:
        """
        Return a validated configuration dict.

        Raises
        ------
        ValueError
            If any numeric field cannot be parsed.
        """
        try:
            return {
                "type":           "scope",
                "instrument_id":  self._id,
                "resource_name":  self._resource_var.get().strip(),
                "channels":       self._channels_var.get().strip(),
                "sample_rate":    float(self._sample_rate_var.get()),
                "voltage_range":  float(self._vrange_var.get()),
                "duration":       float(self._duration_var.get()),
                "trigger_type":   self._ttype_var.get(),
                "trigger_source": self._tsource_var.get().strip(),
                "trigger_level":  float(self._tlevel_var.get()),
                "trigger_slope":  self._tslope_var.get(),
                "simulate":       self._simulate_var.get(),
            }
        except ValueError as exc:
            raise ValueError(f"[{self._id}] Invalid parameter: {exc}") from exc


# ===========================================================================
# Fgen configuration frame
# ===========================================================================

class FgenConfigFrame(ttk.LabelFrame):
    """
    Configuration panel for a single NI-FGEN instrument.

    Exposes :meth:`get_config` which returns a dict ready for
    :class:`FgenController`.
    """

    WAVEFORM_TYPES = ["Sine", "Square", "Triangle", "Ramp Up", "Ramp Down", "DC"]

    def __init__(self, parent, instrument_id: str,
                 remove_callback: Callable[[], None], **kwargs):
        super().__init__(parent, text=f"〜  Fgen – {instrument_id}", **kwargs)
        self._id = instrument_id
        self._remove_cb = remove_callback
        self._build()

    def _build(self):
        pad = {"padx": 6, "pady": 2}

        # ── Row 0: resource + simulate ────────────────────────────────
        r = 0
        ttk.Label(self, text="Resource Name:").grid(row=r, column=0, sticky=tk.W, **pad)
        self._resource_var = tk.StringVar(value="AWG1")
        ttk.Entry(self, textvariable=self._resource_var, width=14).grid(
            row=r, column=1, sticky=tk.EW, **pad)
        self._simulate_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Simulate", variable=self._simulate_var).grid(
            row=r, column=2, sticky=tk.W, **pad)

        # ── Row 1: channel ────────────────────────────────────────────
        r = 1
        ttk.Label(self, text="Channel:").grid(row=r, column=0, sticky=tk.W, **pad)
        self._channel_var = tk.StringVar(value="0,1")
        ttk.Entry(self, textvariable=self._channel_var, width=14).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 2: waveform type ──────────────────────────────────────
        r = 2
        ttk.Label(self, text="Waveform Type:").grid(row=r, column=0, sticky=tk.W, **pad)
        self._wtype_var = tk.StringVar(value="Sine")
        ttk.Combobox(self, textvariable=self._wtype_var,
                     values=self.WAVEFORM_TYPES, state="readonly", width=12).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 3: frequency ──────────────────────────────────────────
        r = 3
        ttk.Label(self, text="Frequency (Hz):").grid(row=r, column=0, sticky=tk.W, **pad)
        self._freq_var = tk.StringVar(value="1000.0")
        ttk.Entry(self, textvariable=self._freq_var, width=14).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 4: amplitude ──────────────────────────────────────────
        r = 4
        ttk.Label(self, text="Amplitude Vpp (V):").grid(row=r, column=0, sticky=tk.W, **pad)
        self._amp_var = tk.StringVar(value="1.0")
        ttk.Entry(self, textvariable=self._amp_var, width=14).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 5: DC offset ──────────────────────────────────────────
        r = 5
        ttk.Label(self, text="DC Offset (V):").grid(row=r, column=0, sticky=tk.W, **pad)
        self._offset_var = tk.StringVar(value="0.0")
        ttk.Entry(self, textvariable=self._offset_var, width=14).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 6: duty cycle ─────────────────────────────────────────
        r = 6
        ttk.Label(self, text="Duty Cycle (%):").grid(row=r, column=0, sticky=tk.W, **pad)
        self._duty_var = tk.StringVar(value="50.0")
        ttk.Entry(self, textvariable=self._duty_var, width=14).grid(
            row=r, column=1, columnspan=2, sticky=tk.EW, **pad)

        # ── Row 7: remove button ──────────────────────────────────────
        r = 7
        ttk.Button(self, text="✕ Remove", command=self._remove_cb).grid(
            row=r, column=2, sticky=tk.E, **pad)

        self.columnconfigure(1, weight=1)

    def get_config(self) -> dict:
        """
        Return a validated configuration dict.

        Raises
        ------
        ValueError
            If any numeric field cannot be parsed.
        """
        try:
            return {
                "type":          "fgen",
                "instrument_id": self._id,
                "resource_name": self._resource_var.get().strip(),
                "channel":       self._channel_var.get().strip(),
                "waveform_type": self._wtype_var.get(),
                "frequency":     float(self._freq_var.get()),
                "amplitude":     float(self._amp_var.get()),
                "dc_offset":     float(self._offset_var.get()),
                "duty_cycle":    float(self._duty_var.get()),
                "simulate":      self._simulate_var.get(),
            }
        except ValueError as exc:
            raise ValueError(f"[{self._id}] Invalid parameter: {exc}") from exc


# ===========================================================================
# Instrument list panel
# ===========================================================================

class InstrumentListPanel(ttk.Frame):
    """
    Scrollable panel containing zero or more :class:`ScopeConfigFrame` and
    :class:`FgenConfigFrame` widgets.

    Instruments can be added or removed dynamically.  The panel is intended
    to sit in the left pane of the main window.
    """

    def __init__(self, parent, app: "NIControllerApp", **kwargs):
        super().__init__(parent, **kwargs)
        self._app = app
        # {instrument_id: config_frame}
        self._frames: dict[str, ScopeConfigFrame | FgenConfigFrame] = {}
        self._build()

    def _build(self):
        # ── Toolbar: add buttons ──────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(toolbar, text="＋ Add Scope",
                   command=self._add_scope).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="＋ Add Fgen",
                   command=self._add_fgen).pack(side=tk.LEFT, padx=2)

        # ── Scrollable canvas ─────────────────────────────────────────
        outer = ttk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner = ttk.Frame(self._canvas)
        self._window_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor=tk.NW)

        self._inner.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse-wheel scrolling
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Pre-populate one FGEN then one Scope
        self._add_fgen()
        self._add_scope()

    def _on_frame_configure(self, _event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._window_id, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------------

    def _add_scope(self):
        iid = _next_scope_id()
        frame = ScopeConfigFrame(
            self._inner,
            instrument_id=iid,
            remove_callback=lambda i=iid: self._remove(i),
        )
        frame.pack(fill=tk.X, padx=4, pady=4)
        self._frames[iid] = frame

    def _add_fgen(self):
        iid = _next_fgen_id()
        frame = FgenConfigFrame(
            self._inner,
            instrument_id=iid,
            remove_callback=lambda i=iid: self._remove(i),
        )
        frame.pack(fill=tk.X, padx=4, pady=4)
        self._frames[iid] = frame

    def _remove(self, instrument_id: str):
        frame = self._frames.pop(instrument_id, None)
        if frame is not None:
            frame.destroy()

    # ------------------------------------------------------------------

    def get_all_configs(self) -> list[dict]:
        """
        Collect and return configuration dicts from all visible panels.

        Shows an error dialog for any panel with invalid values and returns
        an empty list in that case.
        """
        configs = []
        for iid, frame in self._frames.items():
            try:
                configs.append(frame.get_config())
            except ValueError as exc:
                from tkinter import messagebox
                messagebox.showerror("Configuration Error", str(exc))
                return []
        return configs


# ===========================================================================
# Status bar
# ===========================================================================

class StatusBar(ttk.Frame):
    """
    Thin label at the bottom of the main window that shows short status text.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, relief=tk.SUNKEN, **kwargs)
        self._var = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self._var, anchor=tk.W).pack(fill=tk.X, padx=4)

    def set(self, message: str):
        """Update the status text (call from any thread via :meth:`after`)."""
        self._var.set(message)
