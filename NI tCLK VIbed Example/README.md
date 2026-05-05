# NI PXIe Scope TClk Comparison

This repository contains two Python programs that demonstrate the trigger
timing improvement achieved by using NI-TClk to synchronize multiple PXIe
oscilloscopes, compared to synchronization using a PXI backplane trigger.

---

## Hardware Requirements

### PXI Chassis
- Any NI PXIe chassis (e.g., NI PXIe-1085)

### Oscilloscopes — 2× NI PXIe Digitizers
Two NI PXIe oscilloscopes are required.
The units in this system are named **Scope1** and **Scope2** in NI MAX.

### RF Signal Generator — NI PXIe-5841
Used to generate the CW RF test signal acquired by the scopes.
Named **5841_8** in NI MAX.
- Frequency: 20 MHz (default)
- Level: 0 dBm (default)

---

## Software Requirements

### NI Driver Software
The following NI drivers must be installed on the host PC:
- **NI-SCOPE** — digitizer driver
- **NI-RFSG** — RF signal generator driver
- **NI-TClk** — included with NI-SCOPE

### Python
Python 3.9 or later is required. Install dependencies with:

```
python -m pip install -r requirements.txt
```

### Python Packages (`requirements.txt`)
| Package | Purpose |
|---|---|
| `niscope` | Python wrapper for NI-SCOPE driver |
| `nitclk` | Python wrapper for NI-TClk |
| `nirfsg` | Python wrapper for NI-RFSG driver |
| `numpy` | Waveform processing and statistics |
| `matplotlib` | Waveform plotting |

---

## Programs

### `TClk_2Scopes.py`
A general-purpose two-scope measurement tool with TClk synchronization.
Configurable vertical, horizontal, and trigger settings. Measures and
displays the trigger timing difference (ΔT) between the two scopes.

**Run:**
```
python TClk_2Scopes.py
```

---

### `TClk_Sync_Demo.py`
A self-contained demonstration program that shows the trigger timing
improvement achieved by NI-TClk versus a PXI backplane trigger.

**Workflow:**
1. Launch the program — it connects to the hardware automatically.
2. Click **Run without TClk** — acquires 10 waveforms using a PXI
   backplane reference trigger. Results are displayed and the hardware
   disconnects automatically.
3. Click **Connect**, then **Run with TClk** — acquires 10 waveforms
   using NI-TClk hardware synchronization.
4. Compare the **Min**, **Max**, and **Std Dev** of ΔT between the two
   methods on the Results tab.

**Run:**
```
python TClk_Sync_Demo.py
```

A pre-built Windows executable (`TClk_Sync_Demo.exe`) can also be run
directly without a Python installation, provided the NI driver software
is installed.

---

## NI MAX Resource Names

| Instrument | Model | NI MAX Name |
|---|---|---|
| Scope 1 | NI PXIe digitizer | Scope1 |
| Scope 2 | NI PXIe digitizer | Scope2 |
| RF Signal Generator | NI PXIe-5841 | 5841_8 |
