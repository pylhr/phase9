"""
Service Layer — HTTP Service.

Bridges the protocol layer's blocking httpx call to the Qt UI thread via a
QThread worker, mirroring the DNSService pattern exactly.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from data.models import HTTPExchangeResult
from protocols.http_protocol import fetch_http_exchange


class _HTTPWorker(QObject):
    finished = pyqtSignal(object)   # emits HTTPExchangeResult
    failed = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self) -> None:
        try:
            result = fetch_http_exchange(self._url)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - last-resort guard
            self.failed.emit(str(exc))


class HTTPService(QObject):
    """
    Public service used by the UI layer to kick off an HTTP request/response
    inspection.

    Usage:
        service = HTTPService()
        service.result_ready.connect(on_result)
        service.error.connect(on_error)
        service.fetch("https://github.com")
    """

    result_ready = pyqtSignal(object)   # HTTPExchangeResult
    fetch_started = pyqtSignal(str)     # url
    error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _HTTPWorker | None = None

    def fetch(self, url: str) -> None:
        if self._thread is not None and self._thread.isRunning():
            self.error.emit("An HTTP request is already in progress.")
            return

        self.fetch_started.emit(url)

        self._thread = QThread()
        self._worker = _HTTPWorker(url)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)

        self._thread.start()

    def _on_finished(self, result: HTTPExchangeResult) -> None:
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
