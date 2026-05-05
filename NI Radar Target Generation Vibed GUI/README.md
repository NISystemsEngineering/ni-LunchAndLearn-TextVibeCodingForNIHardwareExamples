# NI RTG Simple Python UI

This repository contains Python programs for controlling an NI Radar Target Generation
(RTG) system via a gRPC client. Two UI programs are provided: one with static target
configuration controls and one that loads target configurations from CSV files.

---

## Hardware Requirements

### NI PXIe-5841 VST (Vector Signal Transceiver)
- The RTG system requires one NI PXIe-5841 VST.
- Named **5841_8** in NI MAX by default.
- Used as the RF signal source and receiver for radar target simulation.

### PXI Chassis
- Any NI PXIe chassis compatible with the PXIe-5841 (e.g., NI PXIe-1085).

---

## Software Requirements

### NI RTG Server
The NI RTG Server must be installed and running on the host PC before launching
the UI. Default install location:

```
C:\Program Files\National Instruments\RTG\app\RTG Server.exe
```

The server exposes a gRPC API on **localhost:50052** (default).

### Python
Python 3.9 or later is required. Install dependencies with:

```
python -m pip install -r requirements.txt
```

### Python Packages (`requirements.txt`)
| Package | Purpose |
|---|---|
| `grpcio` | gRPC runtime for communicating with the RTG Server |
| `grpcio-tools` | Tools for regenerating gRPC stubs from `.proto` files |
| `protobuf` | Protocol Buffers serialization |
| `PyQt6` | Desktop UI framework |

---

## Programs

### `RTG_UI_Static.py`
A desktop UI for controlling up to 4 radar targets with static (manually entered)
configuration parameters. Supports range/velocity, time-offset/frequency-offset, and
parameter sweep target modes.

**Run:**
```
python RTG_UI_Static.py
```

---

### `RTG_UI_List.py`
A desktop UI for loading target configurations from CSV files on the RTG controller
and sending them to the hardware.

**Run:**
```
python RTG_UI_List.py
```

---

## Connection Settings

| Setting | Default |
|---|---|
| RTG Server address | `localhost:50052` |
| Instrument (NI MAX name) | `5841_8` |
| Max targets | 4 |

---

## Regenerating gRPC Stubs

If the RTG API `.proto` file changes, regenerate the Python stubs with:

```
python generate_stubs.py
```

Pre-generated stubs are included in the `generated/` directory.
