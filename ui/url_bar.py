"""
UI Layer — URL Exploration Workspace top bar (Module 1).

Central URL input + Explore button that kicks off a session. In Phase 1 this
drives the DNS Explorer; later phases will fan the same "explore" event out
to HTTP, TLS, waterfall, etc.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

from ui.widgets import StatusPill
from data.models import SessionStatus


class URLBar(QWidget):
    explore_requested = pyqtSignal(str)  # emits raw URL text

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("topBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(10)

        self.input = QLineEdit()
        self.input.setObjectName("urlInput")
        self.input.setPlaceholderText("Enter a URL, e.g. github.com or https://example.com")
        self.input.returnPressed.connect(self._emit_explore)
        layout.addWidget(self.input, stretch=1)

        self.explore_btn = QPushButton("Explore")
        self.explore_btn.setObjectName("exploreBtn")
        self.explore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.explore_btn.clicked.connect(self._emit_explore)
        layout.addWidget(self.explore_btn)

        self.status_pill = StatusPill()
        layout.addWidget(self.status_pill)

    def _emit_explore(self) -> None:
        text = self.input.text().strip()
        if text:
            self.explore_requested.emit(text)

    def set_status(self, status: SessionStatus, detail: str | None = None) -> None:
        self.status_pill.set_status(status, detail)

    def set_busy(self, busy: bool) -> None:
        self.explore_btn.setEnabled(not busy)
        self.explore_btn.setText("Exploring…" if busy else "Explore")
