"""
UI Layer — JavaScript Execution Analyzer panel (Module 16).

Illustrative simulation only — prominently labeled. Shows each discovered
JS resource with download/parse/execution time modeled from its real byte
size, blocking vs. async classification, and a total blocking time summary.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
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

from data.models import JSExecutionResult
from ui.theme import DARK
from ui.widgets import Card, EmptyState


def _fmt_ms(ms: float) -> str:
    return f"{ms:.1f} ms"


def _fmt_kb(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    return f"{n / 1024:.1f} KB"


class JSExecutionPanel(QWidget):
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
            "Enter a URL above and click Explore to see a JavaScript execution model "
            "for that real page.\n\nDownload, parse, and execution times are illustrative"
            " — no real JS engine is instrumented — but are scaled from each script's "
            "real measured byte size and the page's actual script count."
        )
        self._layout.addWidget(self._empty_state)
        self._widgets: list[QWidget] = []

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, url: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        loading = EmptyState(f"Waiting for page script data of {url}...")
        self._layout.insertWidget(0, loading)
        self._widgets.append(loading)

    def show_result(self, result: JSExecutionResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if result.error:
            self.show_error(result.error)
            return

        if not result.scripts:
            card = Card("No Scripts Found")
            card.add_widget(QLabel(
                "This page appears to reference no JavaScript resources. "
                "That is unusual for modern sites but possible for simple/static pages."
            ))
            self._layout.insertWidget(0, card)
            self._widgets.append(card)
            return

        # Prominent simulation disclaimer + summary stats
        disclaimer_card = Card("")
        badge_row = QWidget()
        badge_layout = QHBoxLayout(badge_row)
        badge_layout.setContentsMargins(0, 0, 0, 0)

        badge = QLabel("ILLUSTRATIVE SIMULATION")
        badge.setStyleSheet(
            f"color: {DARK['accent_blue']}; background-color: {DARK['accent_blue_bg']};"
            " border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 700;"
        )
        badge_layout.addWidget(badge)
        badge_layout.addStretch()
        disclaimer_card.add_widget(badge_row)

        blocking_count = len(result.blocking_scripts)
        total_count = len(result.scripts)

        stat_row = QWidget()
        stat_layout = QHBoxLayout(stat_row)
        stat_layout.setContentsMargins(0, 4, 0, 4)
        stat_layout.setSpacing(24)

        for lbl_text, val_text, color in [
            ("SCRIPTS", str(total_count), DARK["text_primary"]),
            ("BLOCKING", str(blocking_count),
             DARK["error"] if blocking_count > 5 else DARK["warning"]),
            ("TOTAL BLOCKING TIME", _fmt_ms(result.total_blocking_time_ms),
             DARK["error"] if result.total_blocking_time_ms > 100 else DARK["warning"]),
        ]:
            cell = QWidget()
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(2)
            lbl = QLabel(lbl_text)
            lbl.setObjectName("sectionLabel")
            cl.addWidget(lbl)
            val = QLabel(val_text)
            val.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: 700;")
            cl.addWidget(val)
            stat_layout.addWidget(cell)

        stat_layout.addStretch()
        disclaimer_card.add_widget(stat_row)

        note = QLabel(
            "Download times use the page's real measured transfer timing where available. "
            "Parse and execution times are modeled at ~1 ms/10 KB parse throughput "
            "(a documented V8 benchmark range for bundled JS), which will differ from "
            "the actual browser on any specific machine."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
        disclaimer_card.add_widget(note)

        self._layout.insertWidget(0, disclaimer_card)
        self._widgets.append(disclaimer_card)

        # Script table
        table_card = Card("Script Breakdown")
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Script", "Size", "Download", "Parse", "Execute", "Type"])
        table.setRowCount(len(result.scripts))
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(min(40 + 28 * len(result.scripts), 380))

        for row, script in enumerate(result.scripts):
            url = script.url
            if len(url) > 55 and not script.is_inline:
                url = "..." + url[-52:]
            table.setItem(row, 0, QTableWidgetItem(url))
            table.setItem(row, 1, QTableWidgetItem(_fmt_kb(script.size_bytes)))
            table.setItem(row, 2, QTableWidgetItem(_fmt_ms(script.download_ms)))
            table.setItem(row, 3, QTableWidgetItem(_fmt_ms(script.parse_ms)))
            table.setItem(row, 4, QTableWidgetItem(_fmt_ms(script.execution_ms)))

            type_text = "BLOCKING" if script.is_blocking else "async/defer"
            type_color = DARK["error"] if script.is_blocking else DARK["success"]
            type_item = QTableWidgetItem(type_text)
            type_item.setForeground(QColor(type_color))
            table.setItem(row, 5, type_item)

        table_card.add_widget(table)
        self._layout.insertWidget(1, table_card)
        self._widgets.append(table_card)

        # Blocking explanation
        if blocking_count > 0:
            explain_card = Card("About Parser Blocking")
            explain = QLabel(
                "A blocking script is a <script> tag without an async or defer attribute"
                " — the browser must pause HTML parsing, download the script, parse it,"
                " and execute it before continuing to build the DOM. This is the single"
                " biggest contributor to time-to-interactive on most pages. Modern best"
                " practice is to use async or defer for all non-critical scripts, or"
                " move them to the end of <body>.\n\n"
                "Blocking classification here is a heuristic based on the script URL."
                " Scripts with 'async', 'defer', 'lazy', or 'worker' in their URL are"
                " treated as non-blocking; everything else is treated as blocking."
            )
            explain.setWordWrap(True)
            explain.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 12px;")
            explain_card.add_widget(explain)
            self._layout.insertWidget(2, explain_card)
            self._widgets.append(explain_card)

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        card = Card("Could Not Model JS Execution")
        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {DARK['error']}; font-size:13px;")
        card.add_widget(label)
        self._layout.insertWidget(0, card)
        self._widgets.append(card)

    def _teardown(self) -> None:
        for w in self._widgets:
            self._layout.removeWidget(w)
            w.deleteLater()
        self._widgets = []
