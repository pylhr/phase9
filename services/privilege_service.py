"""
Service Layer — Privilege Service.

Runs the (cheap but not instant — scapy's import and interface enumeration
can take a moment) privilege detection off the UI thread, once per app
launch. Both Packet Explorer and Internet Route Explorer read the cached
result to decide whether Real mode should be offered/defaulted.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from data.models import PrivilegeStatus
from protocols.privilege_protocol import detect_privileges


class _PrivilegeWorker(QObject):
    finished = pyqtSignal(object)  # emits PrivilegeStatus

    def run(self) -> None:
        result = detect_privileges()
        self.finished.emit(result)


class PrivilegeService(QObject):
    """
    Usage:
        service = PrivilegeService()
        service.result_ready.connect(on_result)
        service.check()
    """

    result_ready = pyqtSignal(object)  # PrivilegeStatus

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _PrivilegeWorker | None = None
        self.last_status: PrivilegeStatus | None = None

    def check(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return

        self._thread = QThread()
        self._worker = _PrivilegeWorker()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)

        self._thread.start()

    def _on_finished(self, result: PrivilegeStatus) -> None:
        self.last_status = result
        self.result_ready.emit(result)

    def _cleanup(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
