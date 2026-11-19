"""
Service Layer — DNS Service.

Bridges the protocol layer (real dnspython calls, which block) to the Qt UI
thread. Network calls run on a QThread worker so the UI never freezes during
a lookup, and results come back via signals.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from data.models import DNSResult
from protocols.dns_protocol import resolve_domain


class _DNSWorker(QObject):
    """Runs one DNS resolution on a background thread."""

    finished = pyqtSignal(object)   # emits DNSResult on success
    failed = pyqtSignal(str)        # emits error message on unexpected failure

    def __init__(self, domain: str, nameserver: str | None = None):
        super().__init__()
        self._domain = domain
        self._nameserver = nameserver

    def run(self) -> None:
        try:
            result = resolve_domain(self._domain, nameserver=self._nameserver)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - last-resort guard so the thread always reports back
            self.failed.emit(str(exc))


class DNSService(QObject):
    """
    Public service used by the UI layer to kick off DNS lookups.

    Usage:
        service = DNSService()
        service.result_ready.connect(on_result)
        service.error.connect(on_error)
        service.lookup("github.com")
    """

    result_ready = pyqtSignal(object)   # DNSResult
    lookup_started = pyqtSignal(str)    # domain
    error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _DNSWorker | None = None

    def lookup(self, domain: str, nameserver: str | None = None) -> None:
        # Guard against overlapping lookups stomping on each other.
        if self._thread is not None and self._thread.isRunning():
            self.error.emit("A DNS lookup is already in progress.")
            return

        self.lookup_started.emit(domain)

        self._thread = QThread()
        self._worker = _DNSWorker(domain, nameserver)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        # Always tear the thread down cleanly, regardless of outcome.
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)

        self._thread.start()

    def _on_finished(self, result: DNSResult) -> None:
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
