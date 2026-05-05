# PXIe-5842 VST Loopback — 1 GHz / −10 dBm

## What the program does

1. **Generates** a 1 GHz CW tone at −10 dBm on the VST's **RFout** port using NI-RFSG.  
2. **Acquires** the looped-back signal on the **RFin** port using RFmx SpecAn IQ at 50 MS/s.  
3. **Displays** two plots side-by-side in a WinForms window:
   - **IQ Time-Domain** — I (blue) and Q (orange) versus sample index.
   - **Power Spectrum** — FFT of the IQ record, displayed in dBm vs. MHz offset from the carrier, with the peak annotated.
4. Shows the **measured mean power** in the status bar.

## Prerequisites

| Requirement | Notes |
|---|---|
| Windows 10/11 | 64-bit recommended |
| .NET Framework 4.5 | Included with Windows 8+ |
| NI-RFSG driver | Install from ni.com — provides `NIRfsg.Fx45` |
| RFmx SpecAn | Install from ni.com — provides `RFmx.InstrMX` + `RFmx.SpecAnMX` |
| Visual Studio 2013+ | Or MSBuild 12+ |
| PXIe-5842 | Configured in NI-MAX, RFout → RFin loopback cable fitted |

## Build

```
> Open VST5842Loopback.sln in Visual Studio
> Build → Build Solution  (Ctrl+Shift+B)
```

Or from the command line (Developer Command Prompt):

```
msbuild VST5842Loopback.csproj /p:Configuration=Release
```

## Configure the resource name

By default the code uses `"VST"` as both the RFSG and RFmx resource name.
This is the NI-MAX alias for the PXIe-5842 VST.
If your device appears under a different name (e.g. `"PXIe-5842"`, `"VST2"`) 
change the two constants near the top of `MainForm.cs`:

```csharp
private const string ResourceNameGen = "VST";   // NI-RFSG resource name
private const string ResourceNameAcq = "VST";   // RFmx resource name
```

## Key acquisition parameters (easy to change)

```csharp
private const double CarrierFrequency = 1.0e9;   // Hz   — carrier
private const double OutputPower      = -10.0;   // dBm  — generator power
private const double ReferenceLevel   =  0.0;    // dBm  — RFmx ref level
private const double SampleRate       = 50.0e6;  // S/s  — IQ sample rate
private const double AcquisitionTime  = 10.0e-6; // s    — record length (→ 500 samples)
```

## Expected result

With a direct loopback cable (insertion loss ≈ 0–1 dB) you should see:

- The IQ trace oscillating at the IF alias frequency (there is no downconversion image 
  because the baseband is centred at DC after digital downconversion inside the VST).
- The spectrum showing a sharp spike very close to 0 MHz offset.
- Measured mean power ≈ −10 dBm to −11 dBm depending on cable loss.
