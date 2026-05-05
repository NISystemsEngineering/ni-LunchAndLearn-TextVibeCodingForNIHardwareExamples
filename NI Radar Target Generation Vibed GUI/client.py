"""Python gRPC client for NI Radar Target Generation (RTG)."""
from __future__ import annotations

import sys
from enum import IntEnum
from pathlib import Path
from typing import Optional

import grpc

# Ensure the generated stubs directory is on the path
sys.path.insert(0, str(Path(__file__).parent / "generated"))

import rtg_api_service_pb2 as pb2
import rtg_api_service_pb2_grpc as pb2_grpc


class SyncMode(IntEnum):
    SOFTWARE_TRIGGER = 0
    HARDWARE_TRIGGER = 1
    PULSE_RISING_EDGE = 2
    PULSE_FALLING_EDGE = 3
    RELATIVE_TO_FIRST = 4
    RELATIVE_TO_LAST = 5


class SignalMonitor(IntEnum):
    INPUT = 0
    OUTPUT = 1


class RtgError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"RTG error {code}: {message}")
        self.code = code


def _check(status: pb2.Status) -> None:
    if status.error_status:
        raise RtgError(status.error_code, status.error_message)


class RtgClient:
    """Client for the NI RTG gRPC service.

    Usage::

        with RtgClient("localhost:50052") as rtg:
            rtg.initialize(["VST1"])
            rtg.set_center_frequency(0, 77e9)
            rtg.start()
            rtg.send_targets_range_velocity(0, [{"range": 50.0, "velocity": 10.0, "attenuation": 20.0}])
            rtg.stop()
    """

    def __init__(self, address: str = "localhost:50052", timeout: float = 10.0) -> None:
        self._address = address
        self._timeout = timeout
        self._channel: Optional[grpc.Channel] = None
        self._stub: Optional[pb2_grpc.RtgApiServiceStub] = None

    def connect(self) -> "RtgClient":
        self._channel = grpc.insecure_channel(self._address)
        self._stub = pb2_grpc.RtgApiServiceStub(self._channel)
        return self

    def close_channel(self) -> None:
        if self._channel:
            self._channel.close()
            self._channel = None
            self._stub = None

    def __enter__(self) -> "RtgClient":
        return self.connect()

    def __exit__(self, *_) -> None:
        self.close_channel()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _s(self) -> pb2_grpc.RtgApiServiceStub:
        if self._stub is None:
            raise RuntimeError("Not connected. Call connect() or use as a context manager.")
        return self._stub

    def _device(self, device_id: int) -> pb2.DeviceId:
        return pb2.DeviceId(device_id=device_id)

    def _device_double(self, device_id: int, value: float) -> pb2.DeviceIdDouble:
        return pb2.DeviceIdDouble(device_id=self._device(device_id), parameter=value)

    def _sync(self, mode: SyncMode, time_offset: float = 0.0) -> pb2.Synchronization:
        return pb2.Synchronization(sync_mode=int(mode), time_offset=time_offset)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def query_system_resources(self, experts: str = "") -> dict:
        """Return resource names, product names, and serial numbers discovered on the system."""
        resp = self._s.QuerySystemResources(
            pb2.QuerySystemResourcesRequest(experts=experts),
            timeout=self._timeout,
        )
        _check(resp.error)
        return {
            "resource_names": list(resp.resource_names),
            "product_names": list(resp.product_names),
            "serial_numbers": list(resp.serial_numbers),
        }

    def initialize(self, instrument_names: list[str], options: str = "") -> None:
        """Initialize the RTG system, opening sessions to the specified instruments."""
        resp = self._s.Initialize(
            pb2.InitializeRequest(instrument_names=instrument_names, options=options),
            timeout=self._timeout,
        )
        _check(resp.error)

    def set_center_frequency(self, device_id: int, frequency_hz: float) -> None:
        """Set center frequency (Hz) for the specified device."""
        resp = self._s.SetCenterFrequency(
            pb2.SetCenterFrequencyRequest(parameter=self._device_double(device_id, frequency_hz)),
            timeout=self._timeout,
        )
        _check(resp.error)

    def set_reference_level(self, device_id: int, level_dbm: float) -> None:
        """Set reference level (dBm) for the specified device."""
        resp = self._s.SetReferenceLevel(
            pb2.SetReferenceLevelRequest(parameter=self._device_double(device_id, level_dbm)),
            timeout=self._timeout,
        )
        _check(resp.error)

    def set_common_attenuation(self, device_id: int, attenuation_db: float) -> float:
        """Set common attenuation (dB). Returns the coerced (actual) attenuation applied."""
        resp = self._s.SetCommonAttenuation(
            pb2.SetCommonAttenuationRequest(parameter=self._device_double(device_id, attenuation_db)),
            timeout=self._timeout,
        )
        _check(resp.error)
        return resp.coerced_attenuation

    def set_output_external_attenuation(self, device_id: int, attenuation_db: float) -> None:
        """Set the external output attenuation (dB) connected to the specified device."""
        resp = self._s.SetOutputExternalAttenuation(
            pb2.SetOutputExternalAttenuationRequest(
                parameter=self._device_double(device_id, attenuation_db)
            ),
            timeout=self._timeout,
        )
        _check(resp.error)

    def set_external_time_delay(self, device_id: int, delay_s: float) -> None:
        """Set external cable delay (seconds) for the specified device."""
        resp = self._s.SetExternalTimeDelay(
            pb2.SetExternalTimeDelayRequest(parameter=self._device_double(device_id, delay_s)),
            timeout=self._timeout,
        )
        _check(resp.error)

    def set_offset_frequency(self, device_id: int, offset_hz: float) -> None:
        """Set offset frequency (Hz) to improve SNR for narrow-band radars."""
        resp = self._s.SetOffsetFrequency(
            pb2.SetOffsetFrequencyRequest(parameter=self._device_double(device_id, offset_hz)),
            timeout=self._timeout,
        )
        _check(resp.error)

    def set_pri(self, device_id: int, pri_s: float) -> None:
        """Set the Pulse Repetition Interval (PRI) in seconds."""
        resp = self._s.SetPri(
            pb2.SetPriRequest(parameter=self._device_double(device_id, pri_s)),
            timeout=self._timeout,
        )
        _check(resp.error)

    def set_hardware_trigger(self, device_id: int, trigger_source: str) -> None:
        """Configure the hardware trigger source string (e.g. 'PFI0', 'PXI_Trig0')."""
        resp = self._s.SetHardwareTrigger(
            pb2.SetHardwareTriggerRequest(
                device_id=self._device(device_id), parameter=trigger_source
            ),
            timeout=self._timeout,
        )
        _check(resp.error)

    def enable_frequency_correction(self, device_id: int, enable: bool) -> None:
        """Enable or disable frequency correction for the specified device."""
        resp = self._s.EnableFrequencyCorrection(
            pb2.EnableFrequencyCorrectionRequest(
                device_id=self._device(device_id), parameter=enable
            ),
            timeout=self._timeout,
        )
        _check(resp.error)

    def enable_mmwave(self, device_id: int, enable: bool) -> None:
        """Enable or disable the mmWave head for the specified device."""
        resp = self._s.EnableMmWave(
            pb2.EnableMmWaveRequest(device_id=self._device(device_id), parameter=enable),
            timeout=self._timeout,
        )
        _check(resp.error)

    def set_external_lo(
        self,
        device_id: int,
        enable: bool,
        lo_frequency_hz: float = 0.0,
        lo_power_dbm: float = 0.0,
    ) -> None:
        """Configure the external LO for the specified device."""
        resp = self._s.SetExternalLo(
            pb2.SetExternalLoRequest(
                device_id=self._device(device_id),
                external_lo_parameters=pb2.ExternalLoParameters(
                    enable_external_lo=enable,
                    lo_in_frequency=lo_frequency_hz,
                    lo_in_power=lo_power_dbm,
                ),
            ),
            timeout=self._timeout,
        )
        _check(resp.error)

    def get_external_lo(self, device_id: int) -> dict:
        """Get external LO configuration for the specified device."""
        resp = self._s.GetExternalLo(
            pb2.GetExternalLoRequest(device_id=self._device(device_id)),
            timeout=self._timeout,
        )
        _check(resp.error)
        p = resp.external_lo_parameters
        return {
            "enable_external_lo": p.enable_external_lo,
            "lo_in_frequency": p.lo_in_frequency,
            "lo_in_power": p.lo_in_power,
        }

    def get_minimum_attenuations(self, device_id: int) -> dict:
        """Return the list of valid common attenuations (dB) from calibration."""
        resp = self._s.GetMinimumAttenuations(
            pb2.GetMinimumAttenuationsRequest(device_id=self._device(device_id)),
            timeout=self._timeout,
        )
        _check(resp.error)
        return {
            "attenuations_db": list(resp.cal_data),
            "from_calibration": resp.cal_data_found,
        }

    def get_minimum_time_delay(self, device_id: int) -> dict:
        """Return the minimum achievable time delay (seconds) from calibration."""
        resp = self._s.GetMinimumTimeDelay(
            pb2.GetMinimumTimeDelayRequest(device_id=self._device(device_id)),
            timeout=self._timeout,
        )
        _check(resp.error)
        return {
            "min_delay_s": resp.cal_data,
            "from_calibration": resp.cal_data_found,
        }

    def pulse_detection_calibration(self, device_id: int) -> None:
        """Run pulse detection calibration on the specified device."""
        resp = self._s.PulseDetectionCalibration(
            pb2.PulseDetectionCalibrationRequest(device_id=self._device(device_id)),
            timeout=self._timeout,
        )
        _check(resp.error)

    # ------------------------------------------------------------------
    # System control
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the RTG system, moving it to the active state."""
        resp = self._s.Start(pb2.StartRequest(), timeout=self._timeout)
        _check(resp.error)

    def stop(self) -> None:
        """Stop the RTG system, moving it to the inactive state."""
        resp = self._s.Stop(pb2.StopRequest(), timeout=self._timeout)
        _check(resp.error)

    def close(self) -> None:
        """Release hardware references, moving RTG to the idle state."""
        resp = self._s.Close(pb2.CloseRequest(), timeout=self._timeout)
        _check(resp.error)

    def get_status(self) -> dict:
        """Return the current RTG state and any status detail messages."""
        resp = self._s.GetRtgStatus(pb2.GetRtgStatusRequest(), timeout=self._timeout)
        _check(resp.error)
        return {"state": resp.rtg_state, "details": resp.rtg_details}

    def get_version(self, device_id: int) -> str:
        """Return the firmware/software version string for the specified device."""
        resp = self._s.GetVersion(
            pb2.GetVersionRequest(device_id=self._device(device_id)),
            timeout=self._timeout,
        )
        _check(resp.error)
        return resp.version

    # ------------------------------------------------------------------
    # Target configuration
    # ------------------------------------------------------------------

    def send_targets(
        self,
        device_id: int,
        targets: list[dict],
        sync_mode: SyncMode = SyncMode.SOFTWARE_TRIGGER,
        sync_time_offset: float = 0.0,
    ) -> bool:
        """Send a target configuration using raw time-offset / Hz-doppler values.

        Each target dict may contain:
            time_offset (s), attenuation (dB), doppler (Hz or m/s),
            enable (bool), relative_velocity_enable (bool)
        """
        pb_targets = [
            pb2.BasicTarget(
                target_time_offset=t.get("time_offset", 0.0),
                target_attenuation=t.get("attenuation", 0.0),
                target_doppler=t.get("doppler", 0.0),
                target_enable=t.get("enable", True),
                target_relative_velocity_enable=t.get("relative_velocity_enable", False),
            )
            for t in targets
        ]
        resp = self._s.SendTargetConfiguration(
            pb2.SendTargetConfigurationRequest(
                device_id=self._device(device_id),
                sync=self._sync(sync_mode, sync_time_offset),
                targets=pb_targets,
            ),
            timeout=self._timeout,
        )
        _check(resp.error)
        return resp.response

    def send_targets_range_velocity(
        self,
        device_id: int,
        targets: list[dict],
        sync_mode: SyncMode = SyncMode.SOFTWARE_TRIGGER,
        sync_time_offset: float = 0.0,
    ) -> bool:
        """Send targets specified by range (m) and velocity (m/s).

        Each target dict may contain:
            range (m), attenuation (dB), velocity (m/s), enable (bool)
        """
        pb_targets = [
            pb2.TargetRangeVelocity(
                target_range=t.get("range", 0.0),
                target_attenuation=t.get("attenuation", 0.0),
                target_velocity_offset=t.get("velocity", 0.0),
                target_enable=t.get("enable", True),
            )
            for t in targets
        ]
        resp = self._s.SendTargetConfigurationRangeVelocity(
            pb2.SendTargetConfigurationRangeVelocityRequest(
                device_id=self._device(device_id),
                sync=self._sync(sync_mode, sync_time_offset),
                targets=pb_targets,
            ),
            timeout=self._timeout,
        )
        _check(resp.error)
        return resp.response

    def send_targets_time_frequency(
        self,
        device_id: int,
        targets: list[dict],
        sync_mode: SyncMode = SyncMode.SOFTWARE_TRIGGER,
        sync_time_offset: float = 0.0,
    ) -> bool:
        """Send targets specified by time offset (s) and frequency offset (Hz).

        Each target dict may contain:
            time_offset (s), attenuation (dB), frequency_offset (Hz), enable (bool)
        """
        pb_targets = [
            pb2.TargetTimeFrequency(
                target_time_offset=t.get("time_offset", 0.0),
                target_attenuation=t.get("attenuation", 0.0),
                target_frequency_offset=t.get("frequency_offset", 0.0),
                target_enable=t.get("enable", True),
            )
            for t in targets
        ]
        resp = self._s.SendTargetConfigurationTimeFrequency(
            pb2.SendTargetConfigurationTimeFrequencyRequest(
                device_id=self._device(device_id),
                sync=self._sync(sync_mode, sync_time_offset),
                targets=pb_targets,
            ),
            timeout=self._timeout,
        )
        _check(resp.error)
        return resp.response

    def send_target_list_files(self, device_id: int, file_paths: list[str]) -> None:
        """Send target configurations from CSV files on the RTG controller."""
        resp = self._s.SendTargetConfigurationListFiles(
            pb2.SendTargetConfigurationListFilesRequest(
                device_id=self._device(device_id),
                file_paths=file_paths,
            ),
            timeout=self._timeout,
        )
        _check(resp.error)

    def send_target_parameter_sweep(
        self,
        device_id: int,
        sweeps: list[dict],
        scenario_duration_s: float,
        configuration_update_rate_hz: float,
    ) -> None:
        """Send a parameter sweep scenario.

        Each sweep dict may contain:
            enable (bool), start_time_offset (s), time_offset_rate (s/s),
            start_attenuation (dB), attenuation_rate (dB/s),
            start_freq_shift (Hz), freq_shift_rate (Hz/s)
        """
        pb_sweeps = [
            pb2.TargetConfigurationParameterSweep(
                target_enable=s.get("enable", True),
                start_time_offset=s.get("start_time_offset", 0.0),
                time_offset_rate_of_change=s.get("time_offset_rate", 0.0),
                start_attenuation=s.get("start_attenuation", 0.0),
                attenuation_rate_of_change=s.get("attenuation_rate", 0.0),
                start_freq_shift=s.get("start_freq_shift", 0.0),
                freq_shift_rate_of_change=s.get("freq_shift_rate", 0.0),
            )
            for s in sweeps
        ]
        resp = self._s.SendTargetConfigurationParameterSweep(
            pb2.SendTargetConfigurationParameterSweepRequest(
                device_id=self._device(device_id),
                target_configuration_parameter_sweeps=pb_sweeps,
                scenerio_duration=scenario_duration_s,
                configuration_update_rate=configuration_update_rate_hz,
            ),
            timeout=self._timeout,
        )
        _check(resp.error)

    def send_software_trigger(self, device_id: int) -> None:
        """Send a software trigger to apply a pending target configuration."""
        resp = self._s.SendSoftwareTrigger(
            pb2.SendSoftwareTriggerRequest(device_id=self._device(device_id)),
            timeout=self._timeout,
        )
        _check(resp.error)

    # ------------------------------------------------------------------
    # Signal monitor
    # ------------------------------------------------------------------

    def read_max_power(self, device_id: int, monitor: SignalMonitor = SignalMonitor.OUTPUT) -> float:
        """Return the maximum power (magnitude squared) from the signal monitor."""
        resp = self._s.ReadMaxPower(
            pb2.ReadMaxPowerRequest(
                device_id=self._device(device_id),
                signal_monitor=pb2.SignalMonitor(signal_monitor=int(monitor)),
            ),
            timeout=self._timeout,
        )
        _check(resp.error)
        return resp.max_power

    def read_min_power(self, device_id: int, monitor: SignalMonitor = SignalMonitor.OUTPUT) -> float:
        """Return the minimum power (magnitude squared) from the signal monitor."""
        resp = self._s.ReadMinPower(
            pb2.ReadMinPowerRequest(
                device_id=self._device(device_id),
                signal_monitor=pb2.SignalMonitor(signal_monitor=int(monitor)),
            ),
            timeout=self._timeout,
        )
        _check(resp.error)
        return resp.min_power

    def read_overflow_status(
        self, device_id: int, monitor: SignalMonitor = SignalMonitor.OUTPUT
    ) -> bool:
        """Return True if the signal monitor has overflowed."""
        resp = self._s.ReadOverflowStatus(
            pb2.ReadOverflowStatusRequest(
                device_id=self._device(device_id),
                signal_monitor=pb2.SignalMonitor(signal_monitor=int(monitor)),
            ),
            timeout=self._timeout,
        )
        _check(resp.error)
        return resp.response

    def reset_max_power(self, device_id: int, monitor: SignalMonitor = SignalMonitor.OUTPUT) -> None:
        """Reset the maximum power measurement in the signal monitor."""
        resp = self._s.ResetMaxPower(
            pb2.ResetMaxPowerRequest(
                device_id=self._device(device_id),
                signal_monitor=pb2.SignalMonitor(signal_monitor=int(monitor)),
            ),
            timeout=self._timeout,
        )
        _check(resp.error)

    def reset_overflow_status(
        self, device_id: int, monitor: SignalMonitor = SignalMonitor.OUTPUT
    ) -> None:
        """Reset the overflow status flag in the signal monitor."""
        resp = self._s.ResetOverflowStatus(
            pb2.ResetOverflowStatusRequest(
                device_id=self._device(device_id),
                signal_monitor=pb2.SignalMonitor(signal_monitor=int(monitor)),
            ),
            timeout=self._timeout,
        )
        _check(resp.error)

    # ------------------------------------------------------------------
    # ISP DMA
    # ------------------------------------------------------------------

    def arm_isp_dma(self, device_id: int) -> None:
        """Arm the ISP DMA to prepare it for reading."""
        resp = self._s.WriteArmIspDma(
            pb2.WriteArmIspDmaRequest(device_id=self._device(device_id)),
            timeout=self._timeout,
        )
        _check(resp.error)

    def read_isp_dma_data(self, device_id: int) -> list[float]:
        """Read complex data from the ISP DMA FIFO (returned as a flat list of doubles)."""
        resp = self._s.ReadIspDmaData(
            pb2.ReadIspDmaDataRequest(device_id=self._device(device_id)),
            timeout=self._timeout,
        )
        _check(resp.error)
        return list(resp.isp_dma_data)
