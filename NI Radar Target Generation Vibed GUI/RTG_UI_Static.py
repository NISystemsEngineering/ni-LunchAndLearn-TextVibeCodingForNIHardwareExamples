"""PyQt6 desktop UI for controlling the NI Radar Target Generation (RTG) system."""
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QCheckBox,
    QComboBox, QTextEdit, QDoubleSpinBox, QSpinBox, QStatusBar, QSplitter,
    QFrame, QTabWidget,
)

sys.path.insert(0, str(Path(__file__).parent))
from client import RtgClient, RtgError, SyncMode, SignalMonitor

RTG_SERVER_EXE = Path(r"C:\Program Files\National Instruments\RTG\app\RTG Server.exe")
DEFAULT_SERVER = "localhost:50052"
DEFAULT_INSTRUMENT = "5841_8"
MAX_TARGETS = 4


# ---------------------------------------------------------------------------
# Background worker — keeps gRPC calls off the UI thread
# ---------------------------------------------------------------------------

class RtgWorker(QObject):
    result = pyqtSignal(str)        # success message
    error = pyqtSignal(str)         # error message
    state_changed = pyqtSignal(str) # RTG state string
    monitor_data = pyqtSignal(float, float, bool)  # max_pwr, min_pwr, overflow

    def __init__(self) -> None:
        super().__init__()
        self._client: RtgClient | None = None

    def connect(self, address: str) -> None:
        try:
            self._client = RtgClient(address)
            self._client.connect()
            self.result.emit(f"Connected to {address}")
            self._refresh_state()
        except Exception as e:
            self.error.emit(f"Connection failed: {e}")

    def disconnect(self) -> None:
        if self._client:
            self._client.close_channel()
            self._client = None
        self.result.emit("Disconnected.")
        self.state_changed.emit("—")

    def _refresh_state(self) -> None:
        if self._client:
            try:
                s = self._client.get_status()
                self.state_changed.emit(s["state"])
            except Exception:
                pass

    def initialize(self, instrument: str) -> None:
        try:
            self._client.initialize([instrument])
            self.result.emit(f"Initialized: {instrument}")
            self._refresh_state()
        except RtgError as e:
            self.error.emit(str(e))

    def start(self) -> None:
        try:
            self._client.start()
            self.result.emit("RTG started.")
            self._refresh_state()
        except RtgError as e:
            self.error.emit(str(e))

    def stop(self) -> None:
        try:
            self._client.stop()
            self.result.emit("RTG stopped.")
            self._refresh_state()
        except RtgError as e:
            self.error.emit(str(e))

    def close_rtg(self) -> None:
        try:
            self._client.close()
            self.result.emit("RTG closed.")
            self._refresh_state()
        except RtgError as e:
            self.error.emit(str(e))

    def apply_config(self, device: int, freq: float, ref_level: float,
                     attenuation: float, freq_correction: bool) -> None:
        try:
            self._client.set_center_frequency(device, freq)
            self._client.set_reference_level(device, ref_level)
            coerced = self._client.set_common_attenuation(device, attenuation)
            self._client.enable_frequency_correction(device, freq_correction)
            self.result.emit(
                f"Config applied. Coerced attenuation: {coerced:.2f} dB"
            )
        except RtgError as e:
            self.error.emit(str(e))

    def send_targets(self, device: int, targets: list[dict],
                     sync_mode: SyncMode, sync_offset: float) -> None:
        try:
            self._client.send_targets_range_velocity(
                device, targets, sync_mode=sync_mode, sync_time_offset=sync_offset
            )
            self.result.emit(f"Sent {len(targets)} target(s).")
        except RtgError as e:
            self.error.emit(str(e))

    def send_software_trigger(self, device: int) -> None:
        try:
            self._client.send_software_trigger(device)
            self.result.emit("Software trigger sent.")
        except RtgError as e:
            self.error.emit(str(e))

    def read_signal_monitor(self, device: int, monitor: SignalMonitor) -> None:
        try:
            max_pwr = self._client.read_max_power(device, monitor)
            min_pwr = self._client.read_min_power(device, monitor)
            overflow = self._client.read_overflow_status(device, monitor)
            self.monitor_data.emit(max_pwr, min_pwr, overflow)
        except RtgError as e:
            self.error.emit(str(e))

    def reset_monitor(self, device: int, monitor: SignalMonitor) -> None:
        try:
            self._client.reset_max_power(device, monitor)
            self._client.reset_overflow_status(device, monitor)
            self.result.emit("Signal monitor reset.")
        except RtgError as e:
            self.error.emit(str(e))

    def query_resources(self) -> None:
        try:
            r = self._client.query_system_resources()
            self.result.emit("Devices: " + ", ".join(r["resource_names"]))
        except RtgError as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Target row widget
# ---------------------------------------------------------------------------

class TargetRow(QWidget):
    def __init__(self, index: int, default_range: float, default_velocity: float,
                 default_attenuation: float, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.enable = QCheckBox()
        self.enable.setChecked(True)
        self.enable.setFixedWidth(24)

        self.range = QDoubleSpinBox()
        self.range.setRange(0, 5846)
        self.range.setSuffix(" m")
        self.range.setValue(default_range)
        self.range.setDecimals(1)

        self.velocity = QDoubleSpinBox()
        self.velocity.setRange(-300, 300)
        self.velocity.setSuffix(" m/s")
        self.velocity.setValue(default_velocity)
        self.velocity.setDecimals(1)

        self.attenuation = QDoubleSpinBox()
        self.attenuation.setRange(0, 130)
        self.attenuation.setSuffix(" dB")
        self.attenuation.setValue(default_attenuation)
        self.attenuation.setDecimals(1)

        lbl_range = QLabel("Range:")
        lbl_vel = QLabel("Velocity:")
        lbl_atten = QLabel("Atten:")
        for lbl in (lbl_range, lbl_vel, lbl_atten):
            lbl.setContentsMargins(8, 0, 0, 0)

        layout.addWidget(QLabel(f"T{index + 1}"))
        layout.addWidget(self.enable)
        layout.addWidget(lbl_range)
        layout.addWidget(self.range)
        layout.addWidget(lbl_vel)
        layout.addWidget(self.velocity)
        layout.addWidget(lbl_atten)
        layout.addWidget(self.attenuation)
        layout.addStretch()

    def to_dict(self) -> dict:
        return {
            "range": self.range.value(),
            "velocity": self.velocity.value(),
            "attenuation": self.attenuation.value(),
            "enable": self.enable.isChecked(),
        }


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NI Radar Target Generation Control")

        self._worker = RtgWorker()
        self._worker.result.connect(self._log)
        self._worker.error.connect(self._log_error)
        self._worker.state_changed.connect(self._on_state_changed)
        self._worker.monitor_data.connect(self._on_monitor_data)

        self._build_ui()
        self._set_connected(False)
        self._on_connect()
        self._auto_start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)

        # --- Tabs ---
        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(self.tabs.sizePolicy().horizontalPolicy(),
                           __import__('PyQt6.QtWidgets', fromlist=['QSizePolicy']).QSizePolicy.Policy.Minimum)

        init_tab = QWidget()
        init_layout = QVBoxLayout(init_tab)
        init_layout.setSpacing(8)
        init_layout.setContentsMargins(6, 6, 6, 6)
        init_layout.addWidget(self._build_connection_group())
        init_layout.addWidget(self._build_system_group())
        init_layout.addWidget(self._build_config_group())
        self.tabs.addTab(init_tab, "Init")

        targets_tab = QWidget()
        targets_layout = QVBoxLayout(targets_tab)
        targets_layout.setContentsMargins(6, 6, 6, 6)
        targets_layout.addWidget(self._build_targets_group())
        targets_layout.addStretch()
        self.tabs.addTab(targets_tab, "Static Targets")

        monitor_tab = QWidget()
        monitor_layout = QVBoxLayout(monitor_tab)
        monitor_layout.setContentsMargins(6, 6, 6, 6)
        monitor_layout.addWidget(self._build_monitor_group())
        monitor_layout.addStretch()
        self.tabs.addTab(monitor_tab, "Signal Monitor")

        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setContentsMargins(6, 6, 6, 6)
        log_layout.addWidget(self._build_log_group())
        self.tabs.addTab(log_tab, "Log")

        root.addWidget(self.tabs, 0)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Not connected.")

    def _build_connection_group(self) -> QGroupBox:
        box = QGroupBox("Connection")
        layout = QHBoxLayout(box)

        layout.addWidget(QLabel("Server:"))
        self.server_edit = QLineEdit(DEFAULT_SERVER)
        self.server_edit.setFixedWidth(180)
        layout.addWidget(self.server_edit)

        layout.addWidget(QLabel("Instrument:"))
        self.instrument_edit = QLineEdit(DEFAULT_INSTRUMENT)
        self.instrument_edit.setFixedWidth(120)
        layout.addWidget(self.instrument_edit)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self._on_connect)
        layout.addWidget(self.btn_connect)

        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        layout.addWidget(self.btn_disconnect)

        self.btn_query = QPushButton("Query Resources")
        self.btn_query.clicked.connect(self._on_query)
        layout.addWidget(self.btn_query)

        layout.addStretch()

        self.state_label = QLabel("State: —")
        self.state_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(self.state_label)

        return box

    def _build_system_group(self) -> QGroupBox:
        box = QGroupBox("System Control")
        layout = QHBoxLayout(box)

        self.btn_init = QPushButton("Initialize")
        self.btn_init.clicked.connect(self._on_initialize)
        layout.addWidget(self.btn_init)

        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self._on_start)
        self._style_btn(self.btn_start, "#2e7d32")
        layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self._on_stop)
        self._style_btn(self.btn_stop, "#c62828")
        layout.addWidget(self.btn_stop)

        self.btn_close_rtg = QPushButton("Close")
        self.btn_close_rtg.clicked.connect(self._on_close_rtg)
        layout.addWidget(self.btn_close_rtg)

        layout.addStretch()
        return box

    def _build_config_group(self) -> QGroupBox:
        box = QGroupBox("Configuration  (applied before Start)")
        layout = QGridLayout(box)

        layout.addWidget(QLabel("Device ID:"), 0, 0)
        self.device_spin = QSpinBox()
        self.device_spin.setRange(0, 7)
        self.device_spin.setFixedWidth(60)
        layout.addWidget(self.device_spin, 0, 1)

        layout.addWidget(QLabel("Center Frequency:"), 0, 2)
        self.freq_spin = QDoubleSpinBox()
        self.freq_spin.setRange(9e3, 6.5e9)
        self.freq_spin.setValue(5.5e9)
        self.freq_spin.setSuffix(" Hz")
        self.freq_spin.setDecimals(0)
        self.freq_spin.setSingleStep(1e6)
        self.freq_spin.setFixedWidth(160)
        layout.addWidget(self.freq_spin, 0, 3)

        layout.addWidget(QLabel("Reference Level:"), 0, 4)
        self.ref_spin = QDoubleSpinBox()
        self.ref_spin.setRange(-100, 30)
        self.ref_spin.setValue(-10.0)
        self.ref_spin.setSuffix(" dBm")
        self.ref_spin.setDecimals(1)
        self.ref_spin.setFixedWidth(100)
        layout.addWidget(self.ref_spin, 0, 5)

        layout.addWidget(QLabel("Common Attenuation:"), 1, 0)
        self.atten_spin = QDoubleSpinBox()
        self.atten_spin.setRange(0, 130)
        self.atten_spin.setValue(20.0)
        self.atten_spin.setSuffix(" dB")
        self.atten_spin.setDecimals(1)
        self.atten_spin.setFixedWidth(100)
        layout.addWidget(self.atten_spin, 1, 1)

        layout.addWidget(QLabel("Frequency Correction:"), 1, 2)
        self.freq_corr_check = QCheckBox()
        self.freq_corr_check.setChecked(True)
        layout.addWidget(self.freq_corr_check, 1, 3)

        self.btn_apply_config = QPushButton("Apply Configuration")
        self.btn_apply_config.clicked.connect(self._on_apply_config)
        layout.addWidget(self.btn_apply_config, 1, 5)

        return box

    def _build_targets_group(self) -> QGroupBox:
        box = QGroupBox("Targets")
        layout = QVBoxLayout(box)

        defaults = [
            (4500, 250, 35),
            (3500, 150, 25),
            (2500, 100, 15),
            (1500,  50,  0),
        ]
        self.target_rows = [TargetRow(i, *defaults[i]) for i in range(MAX_TARGETS)]
        for row in self.target_rows:
            layout.addWidget(row)

        # Sync controls + send buttons
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Sync Mode:"))
        self.sync_combo = QComboBox()
        for mode in SyncMode:
            self.sync_combo.addItem(mode.name.replace("_", " ").title(), mode)
        ctrl.addWidget(self.sync_combo)

        ctrl.addWidget(QLabel("Sync Time Offset:"))
        self.sync_offset_spin = QDoubleSpinBox()
        self.sync_offset_spin.setRange(0, 60)
        self.sync_offset_spin.setSuffix(" s")
        self.sync_offset_spin.setDecimals(6)
        ctrl.addWidget(self.sync_offset_spin)

        ctrl.addStretch()

        self.btn_send_targets = QPushButton("Send Targets")
        self.btn_send_targets.clicked.connect(self._on_send_targets)
        self._style_btn(self.btn_send_targets, "#1565c0")
        ctrl.addWidget(self.btn_send_targets)

        layout.addLayout(ctrl)
        return box

    def _build_monitor_group(self) -> QGroupBox:
        box = QGroupBox("Signal Monitor")
        layout = QHBoxLayout(box)

        layout.addWidget(QLabel("Monitor:"))
        self.monitor_combo = QComboBox()
        self.monitor_combo.addItem("Output", SignalMonitor.OUTPUT)
        self.monitor_combo.addItem("Input", SignalMonitor.INPUT)
        layout.addWidget(self.monitor_combo)

        self.btn_read_monitor = QPushButton("Read")
        self.btn_read_monitor.clicked.connect(self._on_read_monitor)
        layout.addWidget(self.btn_read_monitor)

        self.btn_reset_monitor = QPushButton("Reset")
        self.btn_reset_monitor.clicked.connect(self._on_reset_monitor)
        layout.addWidget(self.btn_reset_monitor)

        layout.addWidget(QLabel("Max Power:"))
        self.max_power_label = QLabel("—")
        self.max_power_label.setFixedWidth(120)
        layout.addWidget(self.max_power_label)

        layout.addWidget(QLabel("Min Power:"))
        self.min_power_label = QLabel("—")
        self.min_power_label.setFixedWidth(120)
        layout.addWidget(self.min_power_label)

        layout.addWidget(QLabel("Overflow:"))
        self.overflow_label = QLabel("—")
        self.overflow_label.setFixedWidth(50)
        layout.addWidget(self.overflow_label)

        layout.addStretch()
        return box

    def _build_log_group(self) -> QGroupBox:
        box = QGroupBox("Log")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(120)
        self.log_edit.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_edit)
        btn_clear = QPushButton("Clear Log")
        btn_clear.setFixedWidth(90)
        btn_clear.setFixedHeight(24)
        btn_clear.clicked.connect(self.log_edit.clear)
        layout.addWidget(btn_clear)
        return box

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _style_btn(self, btn: QPushButton, color: str) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: white; font-weight: bold; }}"
            f"QPushButton:disabled {{ background-color: #888; }}"
        )

    def _set_connected(self, connected: bool) -> None:
        self.btn_disconnect.setEnabled(connected)
        self.btn_query.setEnabled(connected)
        self.btn_init.setEnabled(connected)
        self.btn_start.setEnabled(connected)
        self.btn_stop.setEnabled(connected)
        self.btn_close_rtg.setEnabled(connected)
        self.btn_apply_config.setEnabled(connected)
        self.btn_send_targets.setEnabled(connected)
        self.btn_read_monitor.setEnabled(connected)
        self.btn_reset_monitor.setEnabled(connected)
        self.btn_connect.setEnabled(not connected)

    def _log(self, msg: str) -> None:
        self.log_edit.append(f"[OK]  {msg}")
        self.status_bar.showMessage(msg)

    def _log_error(self, msg: str) -> None:
        self.log_edit.append(f'<span style="color:red">[ERR] {msg}</span>')
        self.status_bar.showMessage(f"Error: {msg}")

    def _on_state_changed(self, state: str) -> None:
        self.state_label.setText(f"State: {state}")
        colors = {"idle": "#555", "inactive": "#e65100", "active": "#2e7d32"}
        color = colors.get(state.lower(), "#555")
        self.state_label.setStyleSheet(f"color: {color};")

    def _on_monitor_data(self, max_pwr: float, min_pwr: float, overflow: bool) -> None:
        self.max_power_label.setText(f"{max_pwr:.6f}")
        self.min_power_label.setText(f"{min_pwr:.6f}")
        self.overflow_label.setText("YES" if overflow else "NO")
        self.overflow_label.setStyleSheet("color: red;" if overflow else "color: green;")

    # ------------------------------------------------------------------
    # Button handlers (run worker calls directly on main thread via
    # simple method calls — fast enough for one-shot gRPC calls)
    # ------------------------------------------------------------------

    def _auto_start(self) -> None:
        state = self._worker._client.get_status()["state"].lower() if self._worker._client else ""
        if state == "idle":
            self._worker.initialize(self.instrument_edit.text().strip())
        if state in ("idle", "inactive"):
            self._worker.start()
            self.tabs.setCurrentIndex(1)

    def _on_connect(self) -> None:
        self._worker.connect(self.server_edit.text().strip())
        self._set_connected(True)

    def _on_disconnect(self) -> None:
        self._worker.disconnect()
        self._set_connected(False)

    def _on_query(self) -> None:
        self._worker.query_resources()

    def _on_initialize(self) -> None:
        self._worker.initialize(self.instrument_edit.text().strip())

    def _on_start(self) -> None:
        self._worker.start()
        self.tabs.setCurrentIndex(1)  # switch to Static Targets tab

    def _on_stop(self) -> None:
        self._worker.stop()

    def _shutdown_rtg(self) -> None:
        """Stop and close RTG gracefully, ignoring errors if already inactive/idle."""
        self._worker.stop()
        self._worker.close_rtg()

    def _on_close_rtg(self) -> None:
        self._shutdown_rtg()

    def closeEvent(self, event) -> None:
        self._shutdown_rtg()
        self._worker.disconnect()
        event.accept()

    def _on_apply_config(self) -> None:
        self._worker.apply_config(
            device=self.device_spin.value(),
            freq=self.freq_spin.value(),
            ref_level=self.ref_spin.value(),
            attenuation=self.atten_spin.value(),
            freq_correction=self.freq_corr_check.isChecked(),
        )

    def _on_send_targets(self) -> None:
        targets = [row.to_dict() for row in self.target_rows if row.enable.isChecked()]
        if not targets:
            self._log_error("No targets enabled.")
            return
        sync_mode = self.sync_combo.currentData()
        sync_offset = self.sync_offset_spin.value()
        self._worker.send_targets(self.device_spin.value(), targets, sync_mode, sync_offset)
        self._worker.send_software_trigger(self.device_spin.value())

    def _on_read_monitor(self) -> None:
        self._worker.read_signal_monitor(
            self.device_spin.value(), self.monitor_combo.currentData()
        )

    def _on_reset_monitor(self) -> None:
        self._worker.reset_monitor(
            self.device_spin.value(), self.monitor_combo.currentData()
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    window.adjustSize()
    sys.exit(app.exec())
