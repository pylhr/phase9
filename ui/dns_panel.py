"""
UI Layer — DNS Explorer panel (Module 2).

Shows:
  - the Domain -> Resolver -> IP flow visualization
  - query time and resolver used
  - a records table (type, value, TTL, priority)
  - per-type errors (e.g. no MX record, NXDOMAIN) surfaced honestly
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

from data.models import DNSResult
from ui.theme import DARK, chip_color
from ui.widgets import Card, EmptyState


class FlowStep(QLabel):
    """One box in the Domain -> Resolver -> IP flow diagram."""

    def __init__(self, title: str, subtitle: str, color: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setText(f"<b style='color:{color}; font-size:13px;'>{title}</b>"
                      f"<br><span style='color:{DARK['text_muted']}; font-size:11px;'>{subtitle}</span>")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            background-color: {DARK['bg_elevated']};
            border: 1px solid {color};
            border-radius: 8px;
            padding: 14px 18px;
        """)
        self.setMinimumWidth(160)


class FlowArrow(QLabel):
    def __init__(self, label: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        text = f"→<br><span style='font-size:10px; color:{DARK['text_muted']};'>{label}</span>" if label else "→"
        self.setText(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"color: {DARK['text_secondary']}; font-size:18px;")


class DNSExplorerPanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        self._content = QWidget()
        scroll.setWidget(self._content)

        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(24, 20, 24, 24)
        self._layout.setSpacing(16)

        self._empty_state = EmptyState(
            "Enter a URL above and click Explore to run a live DNS lookup.\n"
            "You'll see every record type returned, the resolver used, and how long it took."
        )
        self._layout.addWidget(self._empty_state)

        self._flow_card: Card | None = None
        self._table_card: Card | None = None
        self._errors_card: Card | None = None
        self._loading_widget: QWidget | None = None

    def clear(self) -> None:
        self._teardown_result_widgets()
        self._empty_state.setVisible(True)

    def show_loading(self, domain: str) -> None:
        self._teardown_result_widgets()
        self._empty_state.setVisible(False)

        loading = EmptyState(f"Resolving {domain}…")
        loading.setObjectName("loadingPlaceholder")
        self._layout.insertWidget(0, loading)
        self._loading_widget = loading

    def show_result(self, result: DNSResult) -> None:
        self._teardown_result_widgets()
        self._empty_state.setVisible(False)

        # --- Flow diagram ---
        flow_card = Card("Resolution Flow")
        flow_row = QWidget()
        flow_layout = QHBoxLayout(flow_row)
        flow_layout.setContentsMargins(8, 8, 8, 8)
        flow_layout.setSpacing(4)

        a_records = result.records_of_type("A")
        ip_subtitle = a_records[0].value if a_records else "no A record"
        if len(a_records) > 1:
            ip_subtitle += f"  (+{len(a_records) - 1} more)"

        flow_layout.addStretch()
        flow_layout.addWidget(FlowStep("Domain", result.domain, DARK["accent_blue"]))
        flow_layout.addWidget(FlowArrow(f"{result.query_time_ms:.0f} ms"))
        flow_layout.addWidget(FlowStep("DNS Resolver", result.resolver_used, DARK["accent"]))
        flow_layout.addWidget(FlowArrow())
        flow_layout.addWidget(FlowStep("IP Address", ip_subtitle, DARK["chip_mx"]))
        flow_layout.addStretch()

        flow_card.add_widget(flow_row)

        meta = QLabel(
            f"Resolver: <b>{result.resolver_used}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Total query time: <b>{result.query_time_ms:.1f} ms</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Records found: <b>{len(result.records)}</b>"
        )
        meta.setObjectName("cardMeta")
        flow_card.add_widget(meta)

        self._layout.insertWidget(0, flow_card)
        self._flow_card = flow_card

        # --- Records table ---
        table_card = Card("DNS Records")
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Type", "Value", "TTL", "Priority"])
        table.setRowCount(len(result.records))
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(min(40 + 32 * max(len(result.records), 1), 320))

        for row, rec in enumerate(result.records):
            type_item = QTableWidgetItem(rec.record_type)
            type_item.setForeground(QColor(chip_color(rec.record_type)))
            table.setItem(row, 0, type_item)
            table.setItem(row, 1, QTableWidgetItem(rec.value))
            table.setItem(row, 2, QTableWidgetItem(f"{rec.ttl}s" if rec.ttl is not None else "—"))
            table.setItem(row, 3, QTableWidgetItem(str(rec.priority) if rec.priority is not None else "—"))

        if not result.records:
            table.setVisible(False)
            table_card.add_widget(QLabel("No DNS records were returned for this domain."))
        else:
            table_card.add_widget(table)

        self._layout.insertWidget(1, table_card)
        self._table_card = table_card

        # --- Errors / notes (e.g. no MX, NXDOMAIN) ---
        if result.errors:
            errors_card = Card("Notes")
            for rtype, msg in result.errors.items():
                line = QLabel(f"<b>{rtype}:</b> {msg}")
                line.setStyleSheet(f"color: {DARK['text_secondary']}; font-size:12px;")
                errors_card.add_widget(line)
            self._layout.insertWidget(2, errors_card)
            self._errors_card = errors_card

    def show_error(self, message: str) -> None:
        self._teardown_result_widgets()
        self._empty_state.setVisible(False)

        error_card = Card("Lookup Failed")
        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {DARK['error']}; font-size:13px;")
        error_card.add_widget(label)
        self._layout.insertWidget(0, error_card)
        self._flow_card = error_card

    def _teardown_result_widgets(self) -> None:
        if self._loading_widget is not None:
            self._layout.removeWidget(self._loading_widget)
            self._loading_widget.deleteLater()
            self._loading_widget = None

        for attr in ("_flow_card", "_table_card", "_errors_card"):
            widget = getattr(self, attr)
            if widget is not None:
                self._layout.removeWidget(widget)
                widget.deleteLater()
                setattr(self, attr, None)
