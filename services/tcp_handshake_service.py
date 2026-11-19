"""
Service Layer — TCP Handshake Service.

Bridges the protocol layer's blocking TCP handshake capture (real or
simulated) to the Qt UI thread via a QThread worker, mirroring
RouteService/PacketService exactly.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from data.models import TCPHandshakeResult
from protocols.tcp_handshake_protocol import capture_tcp_handshake
from protocols.tcp_handshake_simulation_protocol import simulate_tcp_handshake


class _TCPHandshakeWorker(QObject):
    finished = pyqtSignal(object)   # emits TCPHandshakeResult
    failed = pyqtSignal(str)

    def __init__(self, target: str, port: int, use_real: bool):
        super().__init__()
        self._target = target
        self._port = port
        self._use_real = use_real

    def run(self) -> None:
        try:
            if self._use_real:
                result = capture_tcp_handshake(self._target, self._port)
            else:
                result = simulate_tcp_handshake(self._target, self._port)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - last-resort guard
            self.failed.emit(str(exc))


class TCPHandshakeService(QObject):
    """
    Public service used by the UI layer to kick off a TCP handshake capture.

    Usage:
        service = TCPHandshakeService()
        service.result_ready.connect(on_result)
        service.error.connect(on_error)
        service.capture("github.com", 443, use_real=True)
    """

    result_ready = pyqtSignal(object)   # TCPHandshakeResult
    capture_started = pyqtSignal(str)   # target
    error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _TCPHandshakeWorker | None = None

    def capture(self, target: str, port: int, use_real: bool) -> None:
        if self._thread is not None and self._thread.isRunning():
            self.error.emit("A TCP handshake capture is already in progress.")
            return

        self.capture_started.emit(target)

        self._thread = QThread()
        self._worker = _TCPHandshakeWorker(target, port, use_real)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)

        self._thread.start()

    def _on_finished(self, result: TCPHandshakeResult) -> None:
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
