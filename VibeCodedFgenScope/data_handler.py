"""
data_handler.py
===============
Handles all TDMS file I/O using the nptdms library.

TDMS file structure produced by this module
-------------------------------------------
Root
└── Group: <instrument_id>         (one group per physical device)
    ├── Channel: <channel_name>/voltage   (float64 array, V)
    ├── Channel: <channel_name>/time      (float64 array, s)
    └── Properties on each channel:
            sample_rate, timestamp, device_name, channel, waveform_type, …

If nptdms is not installed the handler logs a warning and is a no-op.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

log = logging.getLogger("ni_controller.data")

try:
    from nptdms import TdmsWriter, ChannelObject
    NPTDMS_AVAILABLE = True
except ImportError:
    NPTDMS_AVAILABLE = False


class TdmsDataHandler:
    """
    Writes waveform data packets to a TDMS file.

    Parameters
    ----------
    filepath : str
        Absolute or relative path to the ``.tdms`` output file.
        The file is created (or appended to) on each :meth:`write` call.
    """

    def __init__(self, filepath: str):
        self._filepath = filepath
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

    def write(self, waveform_items: list[dict[str, Any]]):
        """
        Append *waveform_items* to the TDMS file.

        Each item in the list is a dict with the keys documented in
        :class:`ScopeController`.  Items that are not of type ``"waveform"``
        are silently ignored.

        Parameters
        ----------
        waveform_items : list[dict]
            Waveform data packets produced by :class:`ScopeController`.
        """
        if not NPTDMS_AVAILABLE:
            log.warning("nptdms not available – TDMS write skipped.")
            return

        items = [i for i in waveform_items if i.get("type") == "waveform"]
        if not items:
            return

        # Determine write mode: append if file exists, else create fresh
        mode = "a" if os.path.exists(self._filepath) else "w"

        try:
            with TdmsWriter(self._filepath, mode=mode) as writer:
                for item in items:
                    group_name   = item["instrument_id"]
                    channel_name = item["channel"]

                    voltage = np.asarray(item["voltage"], dtype=np.float64)
                    time_ax = np.asarray(item["time_axis"], dtype=np.float64)

                    # Build metadata properties
                    properties = {
                        "sample_rate":   item.get("sample_rate", 0.0),
                        "timestamp":     item.get("timestamp", ""),
                        "resource_name": item.get("resource_name", ""),
                        "instrument_id": item.get("instrument_id", ""),
                        "channel":       channel_name,
                        "NI_ChannelName": channel_name,
                    }

                    # Include any config-level keys that are simple scalars
                    for k, v in item.get("config", {}).items():
                        if isinstance(v, (str, int, float, bool)):
                            properties[f"config_{k}"] = v

                    voltage_ch = ChannelObject(
                        group_name,
                        f"{channel_name}/voltage",
                        voltage,
                        properties=properties,
                    )
                    time_ch = ChannelObject(
                        group_name,
                        f"{channel_name}/time",
                        time_ax,
                        properties={"unit_string": "s"},
                    )

                    writer.write_segment([voltage_ch, time_ch])

            log.info("TDMS written: %s (%d channels)", self._filepath, len(items))

        except Exception as exc:
            log.error("TDMS write error: %s", exc, exc_info=True)
            raise
