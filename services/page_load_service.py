"""
Service Layer — Page Load Service.

Bridges the protocol layer's blocking page-load-and-fetch-resources call to
the Qt UI thread via a QThread worker, mirroring the other services exactly.
This is the slowest of the four jobs kicked off by Explore (it does its own
HTML fetch plus up to ~24 concurrent resource fetches), so running it off
the UI thread matters even more here than for DNS/HTTP/TLS.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from data.models import PageLoadResult
from protocols.page_load_protocol import load_page


class _PageLoadWorker(QObject):
    finished = pyqtSignal(object)   # emits PageLoadResult
    failed = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self) -> None:
        try:
            result = load_page(self._url)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - last-resort guard
            self.failed.emit(str(exc))


class PageLoadService(QObject):
    """
    Public service used by the UI layer to kick off a full page load
    (HTML + discovered resources).

    Usage:
        service = PageLoadService()
        service.result_ready.connect(on_result)
        service.error.connect(on_error)
        service.load("https://github.com")
    """

    result_ready = pyqtSignal(object)   # PageLoadResult
    load_started = pyqtSignal(str)      # url
    error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _PageLoadWorker | None = None

    def load(self, url: str) -> None:
        if self._thread is not None and self._thread.isRunning():
            self.error.emit("A page load is already in progress.")
            return

        self.load_started.emit(url)

        self._thread = QThread()
        self._worker = _PageLoadWorker(url)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)

        self._thread.start()

    def _on_finished(self, result: PageLoadResult) -> None:
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
