"""
UI Layer — Compression Analyzer panel (Module 11).

Compares real original (decompressed) size vs real compressed (wire) size,
showing the algorithm used, compression ratio, and bandwidth saved.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from data.models import CompressionAnalysis, HTTPExchangeResult
from protocols.compression_protocol import analyze_compression
from ui.theme import DARK
from ui.widgets import Card, EmptyState


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


class CompressionBar(QWidget):
    """A simple two-segment horizontal bar: compressed size vs size saved."""

    def __init__(self, analysis: CompressionAnalysis, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self._analysis = analysis

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        a = self._analysis

        if not a.is_compressed or a.decompressed_size_bytes == 0:
            painter.setBrush(QColor(DARK["bg_elevated"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(0, 0, width, height, 4, 4)
            return

        compressed_frac = a.compressed_size_bytes / a.decompressed_size_bytes
        compressed_width = int(width * compressed_frac)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(DARK["accent"]))
        painter.drawRoundedRect(0, 0, max(compressed_width, 3), height, 4, 4)

        painter.setBrush(QColor(DARK["bg_elevated"]))
        painter.drawRoundedRect(compressed_width, 0, width - compressed_width, height, 4, 4)


class CompressionAnalyzerPanel(QWidget):
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
            "Enter a URL above and click Explore to compare real compressed vs "
            "uncompressed response size.\nThe compressed size is the actual number of "
            "bytes transferred over the wire, not an estimate."
        )
        self._layout.addWidget(self._empty_state)

        self._widgets: list[QWidget] = []

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, url: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        loading = EmptyState(f"Waiting for the response from {url} to analyze compression…")
        self._layout.insertWidget(0, loading)
        self._widgets.append(loading)

    def show_exchange(self, exchange: HTTPExchangeResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if exchange.error or exchange.response is None:
            self.show_error(exchange.error or "No response was received.")
            return

        analysis = analyze_compression(exchange.response)
        card = Card("Compression Analysis")

        if not analysis.is_compressed:
            card.add_widget(QLabel(
                f"This response was <b>not compressed</b> "
                f"(Content-Type: {analysis.content_type or 'unknown'}). "
                f"Size: {_format_bytes(analysis.decompressed_size_bytes)}.<br><br>"
                f"Text-based content (HTML, CSS, JS, JSON) usually benefits from compression; "
                f"already-compressed formats like JPEG, PNG, or video typically don't, since "
                f"compressing them again rarely helps and can even add overhead."
            ))
            self._layout.insertWidget(0, card)
            self._widgets.append(card)
            return

        stat_row = QWidget()
        stat_layout = QHBoxLayout(stat_row)
        stat_layout.setContentsMargins(0, 0, 0, 0)
        stat_layout.setSpacing(28)

        for label, value, color in [
            ("ALGORITHM", analysis.algorithm.upper(), DARK["accent"]),
            ("ORIGINAL SIZE", _format_bytes(analysis.decompressed_size_bytes), DARK["text_primary"]),
            ("COMPRESSED SIZE", _format_bytes(analysis.compressed_size_bytes), DARK["text_primary"]),
            ("SAVED", f"{analysis.compression_ratio_pct:.1f}%", DARK["success"]),
        ]:
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(2)
            lab = QLabel(label)
            lab.setObjectName("sectionLabel")
            cell_layout.addWidget(lab)
            val = QLabel(value)
            val.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: 700;")
            cell_layout.addWidget(val)
            stat_layout.addWidget(cell)

        stat_layout.addStretch()
        card.add_widget(stat_row)

        card.add_widget(CompressionBar(analysis))

        bar_caption = QLabel(
            f"Green = {_format_bytes(analysis.compressed_size_bytes)} actually transferred  •  "
            f"Gray = {_format_bytes(analysis.bytes_saved)} saved by {analysis.algorithm.upper()} compression"
        )
        bar_caption.setObjectName("cardMeta")
        card.add_widget(bar_caption)

        explanation = QLabel(
            f"This page would have transferred <b>{_format_bytes(analysis.decompressed_size_bytes)}</b> "
            f"uncompressed. With {analysis.algorithm.upper()}, the server actually sent "
            f"<b>{_format_bytes(analysis.compressed_size_bytes)}</b> — a "
            f"<b>{analysis.compression_ratio_pct:.1f}%</b> reduction in bandwidth for this response."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 12px;")
        card.add_widget(explanation)

        self._layout.insertWidget(0, card)
        self._widgets.append(card)

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("Could Not Analyze Compression")
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
