"""
Service Layer — Route Service.

Bridges the protocol layer's blocking traceroute (real or simulated) to the
Qt UI thread via a QThread worker. Mode is chosen by the caller per-request
rather than being a fixed setting on the service, since the user can toggle
Real/Simulation per exploration from the UI.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from data.models import RouteResult
from protocols.route_protocol import trace_route
from protocols.route_simulation_protocol import simulate_traceroute


class _RouteWorker(QObject):
    finished = pyqtSignal(object)   # emits RouteResult
    failed = pyqtSignal(str)

    def __init__(self, destination: str, use_real: bool):
        super().__init__()
        self._destination = destination
        self._use_real = use_real

    def run(self) -> None:
        try:
            if self._use_real:
                result = trace_route(self._destination)
            else:
                result = simulate_traceroute(self._destination)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - last-resort guard
            self.failed.emit(str(exc))


class RouteService(QObject):
    """
    Public service used by the UI layer to kick off a traceroute.

    Usage:
        service = RouteService()
        service.result_ready.connect(on_result)
        service.error.connect(on_error)
        service.trace("github.com", use_real=True)
    """

    result_ready = pyqtSignal(object)   # RouteResult
    trace_started = pyqtSignal(str)     # destination
    error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _RouteWorker | None = None

    def trace(self, destination: str, use_real: bool) -> None:
        if self._thread is not None and self._thread.isRunning():
            self.error.emit("A traceroute is already in progress.")
            return

        self.trace_started.emit(destination)

        self._thread = QThread()
        self._worker = _RouteWorker(destination, use_real)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)

        self._thread.start()

    def _on_finished(self, result: RouteResult) -> None:
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
