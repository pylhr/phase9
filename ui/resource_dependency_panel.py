"""
UI Layer — Resource Dependency Analyzer panel (Module 8).

Shows the real resources a page depends on: a dependency graph (HTML at the
center, branching out to CSS/JS/Images/Fonts/API), plus a detailed
per-resource list grouped by type with real size and download time.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data.models import PageLoadResult, PageResource
from ui.theme import DARK, resource_color
from ui.widgets import Card, EmptyState

TYPE_ORDER = ["css", "javascript", "image", "font", "other"]
TYPE_LABELS = {
    "css": "CSS",
    "javascript": "JavaScript",
    "image": "Images",
    "font": "Fonts",
    "other": "Other",
}


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def _short_name(url: str) -> str:
    from urllib.parse import urlparse
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] or path or url
    if len(name) > 30:
        name = name[:27] + "…"
    return name


class DependencyGraph(QWidget):
    """
    Custom-painted radial graph: HTML at the center, one branch node per
    resource type, with a count badge. Kept at the category level (not one
    node per individual resource) so it stays readable even when a real
    page references 100+ assets.
    """

    def __init__(self, result: PageLoadResult, parent: QWidget | None = None):
        super().__init__(parent)
        self._type_counts = result.type_counts()
        self._type_counts.pop("html", None)  # HTML is the center node, not a branch
        self.setMinimumHeight(320)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        center = QPointF(w / 2, h / 2)
        radius = min(w, h) / 2 - 70

        branches = [(t, self._type_counts[t]) for t in TYPE_ORDER if self._type_counts.get(t)]
        if not branches:
            painter.setPen(QPen(QColor(DARK["text_muted"])))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No dependent resources found.")
            return

        n = len(branches)
        angle_step = (2 * math.pi) / n

        # Draw connecting lines first so nodes paint on top.
        positions: list[QPointF] = []
        for i, (rtype, count) in enumerate(branches):
            angle = -math.pi / 2 + i * angle_step
            x = center.x() + radius * math.cos(angle)
            y = center.y() + radius * math.sin(angle)
            pos = QPointF(x, y)
            positions.append(pos)

            painter.setPen(QPen(QColor(DARK["border"]), 1.5))
            painter.drawLine(center, pos)

        # Center node (HTML)
        center_radius = 38
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(DARK["res_html"]))
        painter.drawEllipse(center, center_radius, center_radius)
        painter.setPen(QPen(QColor(DARK["bg_app"])))
        font = QFont("Segoe UI", 10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRectF(center.x() - center_radius, center.y() - center_radius, center_radius * 2, center_radius * 2),
            Qt.AlignmentFlag.AlignCenter,
            "HTML",
        )

        # Branch nodes
        for (rtype, count), pos in zip(branches, positions):
            node_radius = 28
            color = QColor(resource_color(rtype))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(pos, node_radius, node_radius)

            painter.setPen(QPen(QColor(DARK["bg_app"])))
            count_font = QFont("Segoe UI", 11)
            count_font.setBold(True)
            painter.setFont(count_font)
            painter.drawText(
                QRectF(pos.x() - node_radius, pos.y() - node_radius - 4, node_radius * 2, node_radius * 2),
                Qt.AlignmentFlag.AlignCenter,
                str(count),
            )

            painter.setPen(QPen(QColor(DARK["text_secondary"])))
            label_font = QFont("Segoe UI", 9)
            painter.setFont(label_font)
            label_rect = QRectF(pos.x() - 50, pos.y() + node_radius + 2, 100, 18)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, TYPE_LABELS.get(rtype, rtype))


class ResourceTypeSection(QWidget):
    """One collapsible-looking section listing all resources of one type."""

    def __init__(self, resource_type: str, resources: list[PageResource], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        total_size = sum(r.size_bytes for r in resources)
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        swatch = QLabel()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(f"background-color: {resource_color(resource_type)}; border-radius: 2px;")
        header_layout.addWidget(swatch)

        title = QLabel(f"{TYPE_LABELS.get(resource_type, resource_type)} ({len(resources)})")
        title.setStyleSheet(f"color: {DARK['text_primary']}; font-size: 12px; font-weight: 600;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        size_label = QLabel(_format_bytes(total_size))
        size_label.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
        header_layout.addWidget(size_label)

        layout.addWidget(header)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Resource", "Status", "Size", "Time"])
        table.setRowCount(len(resources))
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(min(36 + 28 * max(len(resources), 1), 220))

        for row, res in enumerate(resources):
            name_item = QTableWidgetItem(_short_name(res.url))
            name_item.setToolTip(res.url)
            table.setItem(row, 0, name_item)

            if res.error:
                status_item = QTableWidgetItem(res.error)
                status_item.setForeground(QColor(DARK["error"]))
            elif res.status_code:
                status_item = QTableWidgetItem(str(res.status_code))
                status_item.setForeground(QColor(
                    DARK["success"] if res.status_code < 400 else DARK["warning"]
                ))
            else:
                status_item = QTableWidgetItem("not fetched")
                status_item.setForeground(QColor(DARK["text_muted"]))
            table.setItem(row, 1, status_item)

            size_text = _format_bytes(res.size_bytes) if res.size_bytes else "—"
            table.setItem(row, 2, QTableWidgetItem(size_text))

            time_text = f"{res.timing.total_ms:.0f} ms" if res.timing.total_ms else "—"
            table.setItem(row, 3, QTableWidgetItem(time_text))

        layout.addWidget(table)


class ResourceDependencyPanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(24, 20, 24, 24)
        self._layout.setSpacing(16)

        self._empty_state = EmptyState(
            "Enter a URL above and click Explore to map a page's real dependencies.\n"
            "This parses the actual HTML for CSS, JavaScript, image, and font references."
        )
        self._layout.addWidget(self._empty_state)

        self._widgets: list[QWidget] = []

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, url: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        loading = EmptyState(f"Parsing {url} for real CSS, JS, image, and font dependencies…")
        self._layout.insertWidget(0, loading)
        self._widgets.append(loading)

    def show_result(self, result: PageLoadResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if result.error:
            self.show_error(result.error)
            return

        non_html = [r for r in result.resources if r.resource_type != "html"]

        if not non_html:
            empty = Card("Resource Dependencies")
            empty.add_widget(QLabel(
                "This page's HTML didn't reference any external CSS, JS, image, or font files "
                "we could detect — it may be a minimal page or load resources dynamically via JavaScript "
                "after the initial HTML loads."
            ))
            self._layout.insertWidget(0, empty)
            self._widgets.append(empty)
            return

        # --- Dependency graph ---
        graph_card = Card("Dependency Graph")
        graph_card.add_widget(DependencyGraph(result))
        self._layout.insertWidget(0, graph_card)
        self._widgets.append(graph_card)

        # --- Per-type breakdown ---
        list_card = Card("Resources by Type")

        sample_note = QLabel(
            f"Found <b>{len(non_html)}</b> real dependencies in the page HTML. "
            f"A representative sample was actually downloaded for timing; the rest are "
            f"listed as discovered but show no size/time."
        )
        sample_note.setWordWrap(True)
        sample_note.setObjectName("cardMeta")
        list_card.add_widget(sample_note)

        by_type: dict[str, list[PageResource]] = {}
        for r in non_html:
            by_type.setdefault(r.resource_type, []).append(r)

        for rtype in TYPE_ORDER:
            items = by_type.get(rtype)
            if items:
                list_card.add_widget(ResourceTypeSection(rtype, items))

        self._layout.insertWidget(1, list_card)
        self._widgets.append(list_card)

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("Could Not Analyze Page")
        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {DARK['error']}; font-size:13px;")
        card.add_widget(label)
        self._layout.insertWidget(0, card)
        self._widgets.append(card)

    def _teardown(self) -> None:
        for widget in self._widgets:
            self._layout.removeWidget(widget)
            widget.deleteLater()
        self._widgets = []
