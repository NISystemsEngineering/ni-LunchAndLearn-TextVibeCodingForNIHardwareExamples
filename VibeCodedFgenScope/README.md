# NI Multi-Instrument Controller

Production-quality Python application for simultaneous control of multiple
NI oscilloscopes and waveform generators with a live GUI, embedded waveform
plot, and TDMS file output.

---

## Architecture

```
ni_instrument_controller/
├── main.py               # NIControllerApp (root Tk window, orchestration)
├── instrument_control.py # ScopeController, FgenController (driver wrappers)
├── data_handler.py       # TdmsDataHandler (nptdms file I/O)
├── ui_components.py      # ScopeConfigFrame, FgenConfigFrame,
│                         # InstrumentListPanel, StatusBar
└── requirements.txt
```

### Class responsibilities

| Class | File | Responsibility |
|---|---|---|
| `NIControllerApp` | `main.py` | Root Tk window; owns all threads, data queue, plot, and log |
| `ScopeController` | `instrument_control.py` | One niscope session: connect → configure → acquire → close |
| `FgenController` | `instrument_control.py` | One nifgen session: connect → configure → generate → close |
| `TdmsDataHandler` | `data_handler.py` | Writes waveform dicts to a TDMS file via nptdms |
| `ScopeConfigFrame` | `ui_components.py` | LabelFrame with all scope parameters; returns `get_config()` |
| `FgenConfigFrame` | `ui_components.py` | LabelFrame with all fgen parameters; returns `get_config()` |
| `InstrumentListPanel` | `ui_components.py` | Scrollable canvas that hosts N config frames |
| `StatusBar` | `ui_components.py` | Bottom-of-window one-line status label |

---

## Threading model

```
Main thread (Tk event loop)
  │
  ├── Thread: fgen_1   →  FgenController.connect/configure/start_generation
  ├── Thread: fgen_2   →  FgenController.connect/configure/start_generation
  ├── Thread: scope_1  →  ScopeController.connect/configure/acquire
  └── Thread: scope_2  →  ScopeController.connect/configure/acquire
          │
          └──► queue.Queue  ──► main thread polls via after(200, poll)
                                 │
                                 ├── _update_plot()   (matplotlib redraw)
                                 └── _write_tdms()    (nptdms append)
```

- All NI driver calls are confined to worker threads so the GUI never blocks.
- A shared `threading.Event` (`_stop_event`) signals all threads to abort.
- The data queue carries typed dicts: `{"type": "waveform"|"error"|"done", …}`

---

## Simulation mode

Every instrument panel has a **Simulate** checkbox (default: **on**).

When checked (or when the driver package is not installed), the controllers
generate synthetic waveforms entirely in Python so you can exercise the full
application workflow without physical hardware:

- Scope channel 0 → 1 kHz sine wave + noise
- Scope channel 1 → 500 Hz square wave + noise
- Fgen → logs "pretending to configure/generate"

---

## TDMS file layout

```
Root
└─ Group: scope_1                 (one group per instrument_id)
   ├─ Channel: 0/voltage          float64[], V
   ├─ Channel: 0/time             float64[], s
   ├─ Channel: 1/voltage
   └─ Channel: 1/time
      Properties (per channel):
        sample_rate, timestamp, resource_name, instrument_id, channel,
        config_duration, config_voltage_range, …
```

---

## Requirements

| Dependency | Purpose |
|---|---|
| `niscope >= 0.9` | NI-SCOPE Python bindings |
| `nifgen >= 0.9` | NI-FGEN Python bindings |
| `nptdms >= 1.5` | TDMS file I/O |
| `numpy >= 1.24` | Array maths |
| `matplotlib >= 3.7` | Embedded waveform plot |
| `tkinter` | GUI (stdlib, no pip needed) |

Install: `pip install -r requirements.txt`

> **NI drivers** (NI-SCOPE, NI-FGEN) must be installed separately from
> [ni.com](https://www.ni.com/en/support/downloads/drivers.html) before the
> Python bindings will work.  The application runs in **simulation mode**
> without them.

---

## Quick start

```bash
python main.py
```

1. Click **+ Add Scope** or **+ Add Fgen** to add instruments.
2. Fill in resource names (e.g. `Dev1`, `Dev2`) and parameters.
3. Leave **Simulate** checked if no hardware is connected.
4. Click **▶ Run Acquisition**.
5. Waveforms appear in the embedded plot and are saved to the TDMS file.

---

## Key assumptions

- NI-SCOPE model assumed to support `configure_vertical`, `configure_horizontal_timing`,
  and `fetch` (all standard for PXIe-5160/5162/5170 family).
- Input impedance defaulted to 1 MΩ; change in `ScopeController.configure()`.
- NI-FGEN `func_duty_cycle_high` attribute used for square wave duty cycle;
  verify attribute name against your specific hardware model.
- Fgens start generating immediately and run until Stop is pressed or
  the acquisition window closes.
- Scopes arm after fgens to ensure signals are present at trigger time.
