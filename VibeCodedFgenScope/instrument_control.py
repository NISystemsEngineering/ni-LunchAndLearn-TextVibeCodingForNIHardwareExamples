"""
instrument_control.py
=====================
Low-level wrappers around niscope and nifgen sessions.

Each controller runs inside its own thread (managed by main.py) and puts
waveform data packets or error dicts onto the shared data queue.

Simulation mode
---------------
If the NI driver packages are not installed, or if ``simulate=True`` is set
in the instrument config, the controllers generate synthetic waveform data
so the rest of the application (GUI, plot, TDMS) can be exercised without
real hardware.
"""

from __future__ import annotations

import datetime
import logging
import queue
import threading
import time
from typing import Any

import numpy as np

log = logging.getLogger("ni_controller.instruments")

# ---------------------------------------------------------------------------
# Optional driver imports
# ---------------------------------------------------------------------------
try:
    import niscope
    NISCOPE_AVAILABLE = True
except ImportError:
    NISCOPE_AVAILABLE = False

try:
    import nifgen
    NIFGEN_AVAILABLE = True
except ImportError:
    NIFGEN_AVAILABLE = False


# ===========================================================================
# Scope controller
# ===========================================================================

class ScopeController:
    """
    Manages a single NI-SCOPE session.

    Parameters
    ----------
    config : dict
        Instrument configuration produced by :class:`ScopeConfigFrame`.
        Expected keys:

        - ``instrument_id``   – unique label (e.g. ``"scope_0"``)
        - ``resource_name``   – VISA resource string (e.g. ``"Dev1"``)
        - ``channels``        – comma-separated channel list (e.g. ``"0,1"``)
        - ``sample_rate``     – float, samples per second
        - ``voltage_range``   – float, peak voltage range (V)
        - ``duration``        – float, acquisition duration (s)
        - ``trigger_type``    – ``"Immediate"`` | ``"Edge"`` | ``"Software"``
        - ``trigger_source``  – VISA channel or ``""``
        - ``trigger_level``   – float (V)
        - ``trigger_slope``   – ``"Positive"`` | ``"Negative"``
        - ``simulate``        – bool, use NI simulation driver
    data_queue : queue.Queue
        Shared queue into which waveform packets are placed.
    stop_event : threading.Event
        Signals this controller to abort.
    """

    def __init__(self, config: dict, data_queue: queue.Queue,
                 stop_event: threading.Event):
        self._cfg = config
        self._q = data_queue
        self._stop = stop_event
        self._session = None

    # ── Public interface ─────────────────────────────────────────────

    @property
    def instrument_id(self) -> str:
        return self._cfg["instrument_id"]

    def connect(self):
        """Open the niscope session."""
        if not NISCOPE_AVAILABLE or self._cfg.get("simulate", False):
            log.info("[%s] niscope unavailable or simulate=True – using synthetic data.",
                     self.instrument_id)
            self._session = None
            return

        options = "Simulate=0"
        if self._cfg.get("simulate", False):
            options = (
                "Simulate=1,DriverSetup=Model:5162 (4CH);BoardType:PXI"
            )

        log.info("[%s] Opening niscope session on %s",
                 self.instrument_id, self._cfg["resource_name"])
        self._session = niscope.Session(
            self._cfg["resource_name"],
            options=options,
        )

    def configure(self):
        """Apply vertical, horizontal, and trigger settings."""
        if self._session is None:
            return  # simulation path – nothing to configure

        session = self._session
        channels = self._cfg["channels"].split(",")

        # ── Vertical ────────────────────────────────────────────────
        for ch in channels:
            ch = ch.strip()
            session.channels[ch].configure_vertical(
                range=float(self._cfg["voltage_range"]),
                coupling=niscope.VerticalCoupling.DC,
            )
            session.channels[ch].probe_attenuation = 1.0
            # Assumption: 1 MΩ input impedance
            session.channels[ch].input_impedance = 1_000_000.0

        # ── Horizontal (timing) ──────────────────────────────────────
        num_samples = int(
            float(self._cfg["sample_rate"]) * float(self._cfg["duration"])
        )
        session.configure_horizontal_timing(
            min_sample_rate=float(self._cfg["sample_rate"]),
            min_num_pts=num_samples,
            ref_position=50.0,          # trigger at 50% of record
            num_records=1,
            enforce_realtime=True,
        )

        # ── Trigger ─────────────────────────────────────────────────
        ttype = self._cfg.get("trigger_type", "Immediate")
        if ttype == "Immediate":
            session.configure_trigger_immediate()
        elif ttype == "Edge":
            slope_map = {
                "Positive": niscope.TriggerSlope.POSITIVE,
                "Negative": niscope.TriggerSlope.NEGATIVE,
            }
            session.configure_trigger_edge(
                trigger_source=self._cfg.get("trigger_source", "0"),
                level=float(self._cfg.get("trigger_level", 0.0)),
                trigger_coupling=niscope.TriggerCoupling.DC,
                slope=slope_map.get(
                    self._cfg.get("trigger_slope", "Positive"),
                    niscope.TriggerSlope.POSITIVE,
                ),
            )
        elif ttype == "Software":
            session.configure_trigger_software()

        log.info("[%s] Configured: %s channels, %.0f S/s, %.3f s, trigger=%s",
                 self.instrument_id, channels,
                 float(self._cfg["sample_rate"]),
                 float(self._cfg["duration"]), ttype)

    def acquire(self):
        """
        Initiate acquisition, retrieve waveforms, and push packets to the
        data queue.
        """
        if self._session is None:
            self._acquire_simulated()
            return

        session = self._session
        channels = [ch.strip() for ch in self._cfg["channels"].split(",")]
        num_samples = int(
            float(self._cfg["sample_rate"]) * float(self._cfg["duration"])
        )

        with session.initiate():
            timeout = datetime.timedelta(seconds=float(self._cfg["duration"]) + 5.0)
            waveform_info = session.channels[",".join(channels)].fetch(
                num_samples=num_samples,
                timeout=timeout,
            )

        # waveform_info is a list of WaveformInfo objects, one per channel
        for ch, wi in zip(channels, waveform_info):
            dt = 1.0 / float(self._cfg["sample_rate"])
            t = np.arange(len(wi.samples)) * dt
            self._q.put({
                "type": "waveform",
                "instrument_id": self.instrument_id,
                "resource_name": self._cfg["resource_name"],
                "channel": ch,
                "time_axis": t,
                "voltage": np.array(wi.samples),
                "sample_rate": float(self._cfg["sample_rate"]),
                "timestamp": datetime.datetime.now().isoformat(),
                "config": dict(self._cfg),
            })
            log.info("[%s] Channel %s: %d samples acquired.", self.instrument_id, ch, len(wi.samples))

    def close(self):
        """Release the session."""
        if self._session is not None:
            try:
                self._session.close()
                log.info("[%s] Session closed.", self.instrument_id)
            except Exception as exc:
                log.warning("[%s] Error closing session: %s", self.instrument_id, exc)
            finally:
                self._session = None

    # ── Private helpers ──────────────────────────────────────────────

    def _acquire_simulated(self):
        """
        Generate synthetic waveforms when real hardware is absent.

        Produces a noisy sine on channel 0 and a noisy square on channel 1
        (or whichever channels are configured).
        """
        log.info("[%s] Generating simulated waveforms.", self.instrument_id)
        sample_rate = float(self._cfg["sample_rate"])
        duration    = float(self._cfg["duration"])
        channels    = [ch.strip() for ch in self._cfg["channels"].split(",")]
        num_samples = int(sample_rate * duration)
        t = np.linspace(0, duration, num_samples, endpoint=False)

        waveforms = {
            "0": 0.9 * np.sin(2 * np.pi * 1000 * t) + 0.02 * np.random.randn(num_samples),
            "1": 0.9 * np.sign(np.sin(2 * np.pi * 500 * t)) + 0.02 * np.random.randn(num_samples),
        }

        # Brief delay to simulate acquisition time
        time.sleep(min(duration, 1.0))

        for ch in channels:
            v = waveforms.get(ch, np.zeros(num_samples))
            self._q.put({
                "type": "waveform",
                "instrument_id": self.instrument_id,
                "resource_name": self._cfg["resource_name"],
                "channel": ch,
                "time_axis": t,
                "voltage": v,
                "sample_rate": sample_rate,
                "timestamp": datetime.datetime.now().isoformat(),
                "config": dict(self._cfg),
            })
            log.info("[%s] Simulated channel %s: %d samples.", self.instrument_id, ch, num_samples)


# ===========================================================================
# Fgen controller
# ===========================================================================

class FgenController:
    """
    Manages a single NI-FGEN (waveform generator) session.

    Parameters
    ----------
    config : dict
        Instrument configuration produced by :class:`FgenConfigFrame`.
        Expected keys:

        - ``instrument_id``   – unique label
        - ``resource_name``   – VISA resource string
        - ``channel``         – output channel (e.g. ``"0"``)
        - ``waveform_type``   – ``"Sine"`` | ``"Square"`` | ``"Triangle"`` |
                                ``"Ramp Up"`` | ``"Ramp Down"`` | ``"DC"``
        - ``frequency``       – float (Hz)
        - ``amplitude``       – float peak-to-peak (V)
        - ``dc_offset``       – float (V)
        - ``duty_cycle``      – float 0–100 (% used for Square only)
        - ``simulate``        – bool
    data_queue : queue.Queue
        Shared queue (errors/done messages only for fgens).
    stop_event : threading.Event
        Signals this controller to abort generation.
    """

    def __init__(self, config: dict, data_queue: queue.Queue,
                 stop_event: threading.Event):
        self._cfg = config
        self._q = data_queue
        self._stop = stop_event
        self._session = None

    @property
    def instrument_id(self) -> str:
        return self._cfg["instrument_id"]

    def connect(self):
        """Open the nifgen session."""
        if not NIFGEN_AVAILABLE or self._cfg.get("simulate", False):
            log.info("[%s] nifgen unavailable or simulate=True – no hardware session.",
                     self.instrument_id)
            self._session = None
            return

        log.info("[%s] Opening nifgen session on %s",
                 self.instrument_id, self._cfg["resource_name"])
        self._session = nifgen.Session(self._cfg["resource_name"])

    def configure(self):
        """Apply waveform settings to the fgen."""
        if self._session is None:
            log.info("[%s] Simulated fgen – pretending to configure.", self.instrument_id)
            return

        session = self._session
        ch = self._cfg.get("channel", "0")

        wmap = {
            "Sine":      nifgen.Waveform.SINE,
            "Square":    nifgen.Waveform.SQUARE,
            "Triangle":  nifgen.Waveform.TRIANGLE,
            "Ramp Up":   nifgen.Waveform.RAMP_UP,
            "Ramp Down": nifgen.Waveform.RAMP_DOWN,
            "DC":        nifgen.Waveform.DC,
        }
        waveform = wmap.get(self._cfg.get("waveform_type", "Sine"), nifgen.Waveform.SINE)

        session.channels[ch].configure_standard_waveform(
            waveform=waveform,
            amplitude=float(self._cfg["amplitude"]),
            frequency=float(self._cfg["frequency"]),
            dc_offset=float(self._cfg["dc_offset"]),
            start_phase=0.0,
        )

        # Duty cycle only applies to Square waveform
        if waveform == nifgen.Waveform.SQUARE:
            # Assumption: NI-FGEN exposes duty_cycle as a channel attribute
            session.channels[ch].func_duty_cycle_high = float(
                self._cfg.get("duty_cycle", 50.0)
            )

        session.output_mode = nifgen.OutputMode.FUNC
        log.info("[%s] Configured: %s %.1f Hz %.3f Vpp offset=%.3f V",
                 self.instrument_id,
                 self._cfg.get("waveform_type"), float(self._cfg["frequency"]),
                 float(self._cfg["amplitude"]), float(self._cfg["dc_offset"]))

    def start_generation(self):
        """Initiate continuous generation (real session only)."""
        if self._session is not None:
            self._session.initiate()
            log.info("[%s] Generation started.", self.instrument_id)
        else:
            log.info("[%s] Simulated generation running.", self.instrument_id)

    def close(self):
        """Abort generation and release the session."""
        if self._session is not None:
            try:
                self._session.abort()
                self._session.close()
                log.info("[%s] Session closed.", self.instrument_id)
            except Exception as exc:
                log.warning("[%s] Error closing fgen session: %s", self.instrument_id, exc)
            finally:
                self._session = None
