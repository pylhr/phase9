"""
Service Layer — Packet Service.

Bridges the protocol layer's blocking packet capture (real or simulated) to
the Qt UI thread via a QThread worker. Mode is chosen by the caller
per-request, mirroring RouteService.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from data.models import PacketCaptureResult
from protocols.packet_protocol import capture_packets
from protocols.packet_simulation_protocol import simulate_packet_capture


class _PacketWorker(QObject):
    finished = pyqtSignal(object)   # emits PacketCaptureResult
    failed = pyqtSignal(str)

    def __init__(self, target: str, use_real: bool):
        super().__init__()
        self._target = target
        self._use_real = use_real

    def run(self) -> None:
        try:
            if self._use_real:
                result = capture_packets(self._target)
            else:
                result = simulate_packet_capture(self._target)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - last-resort guard
            self.failed.emit(str(exc))


class PacketService(QObject):
    """
    Public service used by the UI layer to kick off a packet capture.

    Usage:
        service = PacketService()
        service.result_ready.connect(on_result)
        service.error.connect(on_error)
        service.capture("github.com", use_real=True)
    """

    result_ready = pyqtSignal(object)   # PacketCaptureResult
    capture_started = pyqtSignal(str)   # target
    error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _PacketWorker | None = None

    def capture(self, target: str, use_real: bool) -> None:
        if self._thread is not None and self._thread.isRunning():
            self.error.emit("A packet capture is already in progress.")
            return

        self.capture_started.emit(target)

        self._thread = QThread()
        self._worker = _PacketWorker(target, use_real)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)

        self._thread.start()

    def _on_finished(self, result: PacketCaptureResult) -> None:
        self.result_ready.emit(result)

    def _on_failed(self, message: str) -> None:
        self.error.emit(message)

    def _cleanup(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
