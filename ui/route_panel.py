"""
UI Layer — Internet Route Explorer panel (Module 3).

Shows the path from My Computer -> Router -> ISP -> Backbone -> Destination
as a real traceroute (when raw-socket privileges are available) or a
realistic simulation. The Real/Simulation toggle is always visible and the
result is always labeled with a DataSourceBadge so it's never ambiguous
which kind of data is on screen.
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

from data.models import PrivilegeStatus, RouteResult
from ui.theme import DARK
from ui.widgets import Card, DataSourceBadge, EmptyState, SegmentedToggle


class RouteFlowDiagram(QWidget):
    """The My Computer -> Router -> ISP -> Backbone -> Destination overview strip."""

    def __init__(self, result: RouteResult, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        hop_count = len(result.hops)
        stages = [
            ("My Computer", "you"),
            ("Router", "local network"),
            ("ISP", f"~{min(3, hop_count)} hops in"),
            ("Backbone", "long-haul internet"),
            (result.destination, "destination"),
        ]

        layout.addStretch()
        for i, (title, subtitle) in enumerate(stages):
            box = QLabel(f"<b style='color:{DARK['accent']}; font-size:12px;'>{title}</b>"
                         f"<br><span style='color:{DARK['text_muted']}; font-size:10px;'>{subtitle}</span>")
            box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.setWordWrap(True)
            box.setStyleSheet(f"""
                background-color: {DARK['bg_elevated']};
                border: 1px solid {DARK['accent_dim']};
                border-radius: 8px;
                padding: 10px 14px;
            """)
            box.setMinimumWidth(130)
            box.setMaximumWidth(150)
            layout.addWidget(box)
            if i < len(stages) - 1:
                arrow = QLabel("→")
                arrow.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 16px;")
                layout.addWidget(arrow)
        layout.addStretch()


def _rtt_color(rtt_ms: float | None) -> str:
    if rtt_ms is None:
        return DARK["text_muted"]
    if rtt_ms < 20:
        return DARK["success"]
    if rtt_ms < 80:
        return DARK["warning"]
    return DARK["error"]


class RouteExplorerPanel(QWidget):
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

        # --- Mode toggle, always visible at the top of this module ---
        self._mode_card = Card("")
        mode_row = QWidget()
        mode_layout = QHBoxLayout(mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)

        mode_label = QLabel("Mode:")
        mode_label.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 12px;")
        mode_layout.addWidget(mode_label)

        self.mode_toggle = SegmentedToggle([("real", "Real Traceroute"), ("simulated", "Simulation")])
        mode_layout.addWidget(self.mode_toggle)
        self._mode_card.add_widget(mode_row)

        self._privilege_note = QLabel("")
        self._privilege_note.setWordWrap(True)
        self._privilege_note.setObjectName("cardMeta")
        self._mode_card.add_widget(self._privilege_note)

        self._layout.addWidget(self._mode_card)

        self._empty_state = EmptyState(
            "Enter a URL above and click Explore to trace the real network path to its server.\n"
            "If raw-socket privileges aren't available, this falls back to a realistic simulation — "
            "use the toggle above to switch modes any time."
        )
        self._layout.addWidget(self._empty_state)

        self._widgets: list[QWidget] = []

    def set_privilege_status(self, status: PrivilegeStatus) -> None:
        if status.can_raw_traceroute:
            self._privilege_note.setText(
                "✓ This system can run real traceroutes (raw socket access detected)."
            )
            self._privilege_note.setStyleSheet(f"color: {DARK['success']}; font-size: 11px;")
        else:
            self._privilege_note.setText(
                "Real traceroute isn't available right now, so Simulation mode is selected. "
                + status.detail.split("Packet capture:")[0].replace("Traceroute: ", "")
            )
            self._privilege_note.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
            self.mode_toggle._buttons["simulated"].setChecked(True)
            self.mode_toggle._buttons["real"].setEnabled(False)

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, destination: str, use_real: bool) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        mode_text = "a real traceroute" if use_real else "a simulated traceroute"
        loading = EmptyState(f"Running {mode_text} to {destination}…")
        self._layout.insertWidget(1, loading)
        self._widgets.append(loading)

    def show_result(self, result: RouteResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if result.error:
            self.show_error(result.error)
            return

        # --- Badge + flow diagram ---
        flow_card = Card("Route Overview")
        badge_row = QWidget()
        badge_layout = QHBoxLayout(badge_row)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.addWidget(DataSourceBadge(result.source.value == "real"))
        badge_layout.addStretch()
        meta = QLabel(
            f"{len(result.hops)} hops  •  {result.total_time_ms:.0f} ms total"
            + ("  •  reached destination" if result.reached_destination else "  •  did not reach destination")
        )
        meta.setObjectName("cardMeta")
        badge_layout.addWidget(meta)
        flow_card.add_widget(badge_row)

        flow_card.add_widget(RouteFlowDiagram(result))
        self._layout.insertWidget(1, flow_card)
        self._widgets.append(flow_card)

        # --- Hop table ---
        table_card = Card("Hop-by-Hop Path")
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Hop", "IP Address", "Hostname", "Latency"])
        table.setRowCount(len(result.hops))
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setMinimumSectionSize(110)
        table.setMinimumHeight(min(40 + 30 * max(len(result.hops), 1), 480))

        for row, hop in enumerate(result.hops):
            table.setItem(row, 0, QTableWidgetItem(str(hop.hop_number)))

            if hop.timed_out:
                ip_item = QTableWidgetItem("* * *")
                ip_item.setForeground(QColor(DARK["text_muted"]))
                table.setItem(row, 1, ip_item)
                table.setItem(row, 2, QTableWidgetItem("(no response)"))
                table.setItem(row, 3, QTableWidgetItem("—"))
            else:
                ip_item = QTableWidgetItem(hop.ip_address or "—")
                if hop.is_destination:
                    ip_item.setForeground(QColor(DARK["accent"]))
                table.setItem(row, 1, ip_item)
                table.setItem(row, 2, QTableWidgetItem(hop.hostname or "(no reverse DNS)"))

                rtt_item = QTableWidgetItem(f"{hop.rtt_ms:.1f} ms" if hop.rtt_ms is not None else "—")
                rtt_item.setForeground(QColor(_rtt_color(hop.rtt_ms)))
                table.setItem(row, 3, rtt_item)

        table_card.add_widget(table)
        self._layout.insertWidget(2, table_card)
        self._widgets.append(table_card)

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("Traceroute Failed")
        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {DARK['error']}; font-size:13px;")
        card.add_widget(label)
        self._layout.insertWidget(1, card)
        self._widgets.append(card)

    def _teardown(self) -> None:
        for widget in self._widgets:
            self._layout.removeWidget(widget)
            widget.deleteLater()
        self._widgets = []
