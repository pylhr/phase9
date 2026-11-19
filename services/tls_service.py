"""
Service Layer — TLS Service.

Bridges the protocol layer's blocking ssl handshake to the Qt UI thread via
a QThread worker, mirroring the DNSService/HTTPService pattern exactly.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from data.models import TLSResult
from protocols.tls_protocol import inspect_tls


class _TLSWorker(QObject):
    finished = pyqtSignal(object)   # emits TLSResult
    failed = pyqtSignal(str)

    def __init__(self, hostname: str, port: int = 443):
        super().__init__()
        self._hostname = hostname
        self._port = port

    def run(self) -> None:
        try:
            result = inspect_tls(self._hostname, port=self._port)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - last-resort guard
            self.failed.emit(str(exc))


class TLSService(QObject):
    """
    Public service used by the UI layer to kick off a TLS handshake
    inspection.

    Usage:
        service = TLSService()
        service.result_ready.connect(on_result)
        service.error.connect(on_error)
        service.inspect("github.com")
    """

    result_ready = pyqtSignal(object)   # TLSResult
    inspect_started = pyqtSignal(str)   # hostname
    error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _TLSWorker | None = None

    def inspect(self, hostname: str, port: int = 443) -> None:
        if self._thread is not None and self._thread.isRunning():
            self.error.emit("A TLS inspection is already in progress.")
            return

        self.inspect_started.emit(hostname)

        self._thread = QThread()
        self._worker = _TLSWorker(hostname, port)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)

        self._thread.start()

    def _on_finished(self, result: TLSResult) -> None:
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
