"""
UI Layer — HTTP Request Inspector panel (Module 6).

Shows the outgoing request: method, URL, headers, cookies, body — in both
a human-readable form and raw HTTP wire format.
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

from data.models import HTTPRequestRecord
from ui.theme import DARK
from ui.widgets import Card, EmptyState, MonoBlock, SegmentedToggle


class HTTPRequestPanel(QWidget):
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
            "Enter a URL above and click Explore to inspect the real outgoing HTTP request.\n"
            "You'll see the exact method, headers, and body sent to the server."
        )
        self._layout.addWidget(self._empty_state)

        self._result_widget: QWidget | None = None

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, url: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        loading = EmptyState(f"Sending request to {url}…")
        self._layout.insertWidget(0, loading)
        self._result_widget = loading

    def show_request(self, request: HTTPRequestRecord) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("Outgoing Request")

        summary = QLabel(
            f"<span style='color:{DARK['accent']}; font-weight:600;'>{request.method}</span> "
            f"<span style='color:{DARK['text_secondary']};'>{request.url}</span>"
        )
        summary.setWordWrap(True)
        summary.setObjectName("cardMeta")
        card.add_widget(summary)

        toggle = SegmentedToggle([("parsed", "Human-Readable"), ("raw", "Raw HTTP")])
        card.add_widget(toggle)

        stack_container = QWidget()
        stack = QStackedLayout(stack_container)

        # --- Parsed / human-readable view ---
        parsed_widget = QWidget()
        parsed_layout = QVBoxLayout(parsed_widget)
        parsed_layout.setContentsMargins(0, 8, 0, 0)
        parsed_layout.setSpacing(12)

        headers_label = QLabel("HEADERS")
        headers_label.setObjectName("sectionLabel")
        parsed_layout.addWidget(headers_label)

        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Header", "Value"])
        table.setRowCount(len(request.headers))
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setMinimumSectionSize(110)
        table.setMinimumHeight(min(40 + 30 * max(len(request.headers), 1), 280))

        for row, (key, value) in enumerate(request.headers.items()):
            table.setItem(row, 0, QTableWidgetItem(key))
            table.setItem(row, 1, QTableWidgetItem(value))

        parsed_layout.addWidget(table)

        if request.body:
            body_label = QLabel("BODY")
            body_label.setObjectName("sectionLabel")
            parsed_layout.addWidget(body_label)
            parsed_layout.addWidget(MonoBlock(request.body))
        else:
            no_body = QLabel("This request has no body (GET requests typically don't send one).")
            no_body.setObjectName("cardMeta")
            parsed_layout.addWidget(no_body)

        stack.addWidget(parsed_widget)

        # --- Raw HTTP view ---
        raw_widget = MonoBlock(request.raw_format())
        raw_widget.setMinimumHeight(280)
        stack.addWidget(raw_widget)

        toggle.option_changed.connect(
            lambda key: stack.setCurrentIndex(0 if key == "parsed" else 1)
        )

        card.add_widget(stack_container)

        self._layout.insertWidget(0, card)
        self._result_widget = card

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("Request Failed")
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
