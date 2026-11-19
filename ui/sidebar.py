"""
UI Layer — Sidebar navigation.

Lists every module from the spec so the roadmap is visible inside the app
itself. Modules not yet built in the current phase are shown but disabled,
with a tooltip explaining which phase delivers them — this keeps the full
19-module scope honest and visible rather than hiding it until later.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget, QLabel

# (module key, display label, phase delivered)
MODULES: list[tuple[str, str, int]] = [
    ("url_workspace", "URL Exploration Workspace", 1),
    ("dns", "DNS Explorer", 1),
    ("route", "Internet Route Explorer", 5),
    ("tcp", "TCP Handshake Visualizer", 6),
    ("tls", "TLS Handshake Explorer", 2),
    ("http_request", "HTTP Request Inspector", 2),
    ("http_response", "HTTP Response Inspector", 2),
    ("resource_graph", "Resource Dependency Graph", 3),
    ("waterfall", "Network Waterfall Timeline", 3),
    ("packets", "Packet Explorer", 5),
    ("compression", "Compression Analyzer", 4),
    ("cookies", "Cookie Explorer", 4),
    ("cdn", "CDN Explorer", 6),
    ("security", "Security Inspector", 4),
    ("rendering", "Rendering Pipeline", 7),
    ("js_execution", "JS Execution Analyzer", 7),
    ("protocol_comparison", "Protocol Comparison Lab", 9),
    ("failure_sim", "Failure Simulation Lab", 9),
    ("sessions", "Session Recording & Replay", 8),
]

CURRENT_PHASE = 9


class Sidebar(QWidget):
    module_selected = pyqtSignal(str)  # emits module key

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(272)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        brand = QLabel("The Internet Explorer")
        brand.setObjectName("sidebarBrand")
        layout.addWidget(brand)

        subtitle = QLabel(f"Phase {CURRENT_PHASE} — see what's live below")
        subtitle.setObjectName("sidebarSubtitle")
        layout.addWidget(subtitle)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navList")
        self.nav_list.setFrameShape(QListWidget.Shape.NoFrame)
        self.nav_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

        self._key_for_row: dict[int, str] = {}

        for row, (key, label, phase) in enumerate(MODULES):
            item = QListWidgetItem()
            available = phase <= CURRENT_PHASE
            if available:
                item.setText(label)
            else:
                item.setText(f"{label}  ·  Phase {phase}")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip(f"Arrives in Phase {phase} of the build plan.")
            self.nav_list.addItem(item)
            self._key_for_row[row] = key

        self.nav_list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.nav_list, stretch=1)

        # Select the URL workspace by default.
        self.nav_list.setCurrentRow(0)

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            return
        key = self._key_for_row.get(row)
        if key:
            self.module_selected.emit(key)

    def select_module(self, key: str) -> None:
        for row, k in self._key_for_row.items():
            if k == key:
                self.nav_list.setCurrentRow(row)
                return
