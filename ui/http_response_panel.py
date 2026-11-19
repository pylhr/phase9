"""
UI Layer — HTTP Response Inspector panel (Module 7).

Shows: status code, headers, body size, compression method, response time,
plus raw and parsed views, and a content-type summary.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data.models import HTTPExchangeResult
from ui.theme import DARK
from ui.widgets import Card, EmptyState, MonoBlock, SegmentedToggle


def _status_color(status_code: int) -> str:
    if 200 <= status_code < 300:
        return DARK["success"]
    if 300 <= status_code < 400:
        return DARK["accent_blue"]
    if 400 <= status_code < 500:
        return DARK["warning"]
    return DARK["error"]


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


class StatCell(QWidget):
    """One stat in the response summary strip (label above value)."""

    def __init__(self, label: str, value: str, value_color: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        lab = QLabel(label)
        lab.setObjectName("sectionLabel")
        layout.addWidget(lab)

        val = QLabel(value)
        color = value_color or DARK["text_primary"]
        val.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: 600;")
        layout.addWidget(val)


class HTTPResponsePanel(QWidget):
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
            "Enter a URL above and click Explore to inspect the real HTTP response.\n"
            "You'll see the status code, headers, timing, and body content."
        )
        self._layout.addWidget(self._empty_state)

        self._result_widget: QWidget | None = None
        self._extra_widget: QWidget | None = None

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, url: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        loading = EmptyState(f"Waiting for response from {url}…")
        self._layout.insertWidget(0, loading)
        self._result_widget = loading

    def show_exchange(self, exchange: HTTPExchangeResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if exchange.error or exchange.response is None:
            self.show_error(exchange.error or "No response was received.")
            return

        response = exchange.response

        # --- Summary stat strip ---
        summary_card = Card("Response Summary")
        stat_row = QWidget()
        stat_layout = QHBoxLayout(stat_row)
        stat_layout.setContentsMargins(0, 4, 0, 0)
        stat_layout.setSpacing(28)

        stat_layout.addWidget(StatCell(
            "STATUS", f"{response.status_code} {response.reason}",
            value_color=_status_color(response.status_code),
        ))
        stat_layout.addWidget(StatCell("HTTP VERSION", response.http_version or "—"))
        stat_layout.addWidget(StatCell("BODY SIZE", _format_bytes(response.body_size_bytes)))
        stat_layout.addWidget(StatCell("COMPRESSION", response.compression or "none"))
        stat_layout.addWidget(StatCell("RESPONSE TIME", f"{response.response_time_ms:.0f} ms"))
        stat_layout.addStretch()

        summary_card.add_widget(stat_row)

        content_type_label = QLabel(f"Content-Type: <b>{response.content_type or 'unknown'}</b>")
        content_type_label.setObjectName("cardMeta")
        summary_card.add_widget(content_type_label)

        self._layout.insertWidget(0, summary_card)

        # --- Headers + body card ---
        detail_card = Card("Response Detail")

        toggle = SegmentedToggle([
            ("parsed", "Parsed"),
            ("raw_headers", "Raw Headers"),
            ("body", "Body Preview"),
        ])
        detail_card.add_widget(toggle)

        stack_container = QWidget()
        stack = QStackedLayout(stack_container)

        # Parsed headers table
        parsed_widget = QWidget()
        parsed_layout = QVBoxLayout(parsed_widget)
        parsed_layout.setContentsMargins(0, 8, 0, 0)

        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Header", "Value"])
        table.setRowCount(len(response.headers))
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setMinimumSectionSize(110)
        table.setMinimumHeight(min(40 + 30 * max(len(response.headers), 1), 320))

        for row, (key, value) in enumerate(response.headers.items()):
            table.setItem(row, 0, QTableWidgetItem(key))
            table.setItem(row, 1, QTableWidgetItem(value))

        parsed_layout.addWidget(table)

        if response.raw_set_cookie_headers:
            cookie_note = QLabel(
                f"This response also set {len(response.raw_set_cookie_headers)} cookie"
                f"{'s' if len(response.raw_set_cookie_headers) != 1 else ''} — see the "
                f"Cookie Explorer for a parsed view, or Raw Headers below for the exact wire format."
            )
            cookie_note.setWordWrap(True)
            cookie_note.setObjectName("cardMeta")
            parsed_layout.addWidget(cookie_note)

        stack.addWidget(parsed_widget)

        # Raw headers
        raw_headers = MonoBlock(response.raw_format())
        raw_headers.setMinimumHeight(280)
        stack.addWidget(raw_headers)

        # Body preview
        body_widget = MonoBlock(response.body_preview)
        body_widget.setMinimumHeight(280)
        stack.addWidget(body_widget)

        toggle.option_changed.connect(lambda key: stack.setCurrentIndex(
            {"parsed": 0, "raw_headers": 1, "body": 2}[key]
        ))

        detail_card.add_widget(stack_container)
        self._layout.insertWidget(1, detail_card)

        # Track both cards for teardown.
        self._result_widget = summary_card
        self._extra_widget = detail_card

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("No Response")
        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {DARK['error']}; font-size:13px;")
        card.add_widget(label)
        self._layout.insertWidget(0, card)
        self._result_widget = card

    def _teardown(self) -> None:
        if self._result_widget is not None:
            self._layout.removeWidget(self._result_widget)
            self._result_widget.deleteLater()
            self._result_widget = None
        if self._extra_widget is not None:
            self._layout.removeWidget(self._extra_widget)
            self._extra_widget.deleteLater()
            self._extra_widget = None
