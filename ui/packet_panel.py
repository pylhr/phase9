"""
UI Layer — Packet Explorer panel (Module 10).

Shows captured packets (real, when Npcap/raw-capture privileges are
available, or simulated) with protocol filtering and a detail view per
packet. Like the Route Explorer, mode is always visible via a toggle and
results are always labeled with a DataSourceBadge.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data.models import PacketCaptureResult, PrivilegeStatus
from ui.theme import DARK, protocol_color
from ui.widgets import Card, DataSourceBadge, EmptyState, MonoBlock, SegmentedToggle

ALL_PROTOCOLS = "All"


class ProtocolFilterBar(QWidget):
    """Pill-style filter buttons, one per protocol seen in the capture, plus 'All'."""

    def __init__(self, protocol_counts: dict[str, int], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}

        total = sum(protocol_counts.values())
        ordered = [(ALL_PROTOCOLS, total)] + sorted(protocol_counts.items(), key=lambda kv: -kv[1])

        for protocol, count in ordered:
            btn = QPushButton(f"{protocol} ({count})")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            color = DARK["text_secondary"] if protocol == ALL_PROTOCOLS else protocol_color(protocol)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {color};
                    border: 1px solid {DARK['border']};
                    padding: 4px 12px;
                    font-size: 11px;
                    border-radius: 5px;
                    font-weight: 600;
                }}
                QPushButton:checked {{
                    background-color: {DARK['bg_elevated']};
                    border: 1px solid {color};
                }}
                QPushButton:hover:!checked {{
                    border: 1px solid {DARK['text_secondary']};
                }}
            """)
            if protocol == ALL_PROTOCOLS:
                btn.setChecked(True)
            self._group.addButton(btn)
            self.buttons[protocol] = btn
            layout.addWidget(btn)

        layout.addStretch()


class PacketExplorerPanel(QWidget):
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

        self.mode_toggle = SegmentedToggle([("real", "Real Capture"), ("simulated", "Simulation")])
        mode_layout.addWidget(self.mode_toggle)
        self._mode_card.add_widget(mode_row)

        self._privilege_note = QLabel("")
        self._privilege_note.setWordWrap(True)
        self._privilege_note.setObjectName("cardMeta")
        self._mode_card.add_widget(self._privilege_note)

        self._layout.addWidget(self._mode_card)

        self._empty_state = EmptyState(
            "Enter a URL above and click Explore to capture real packets for that connection.\n"
            "If packet capture privileges (Npcap on Windows) aren't available, this falls back "
            "to a realistic simulation of a full TCP+TLS+HTTP exchange — use the toggle above "
            "to switch modes any time."
        )
        self._layout.addWidget(self._empty_state)

        self._widgets: list[QWidget] = []
        self._all_packets = []
        self._table: QTableWidget | None = None
        self._detail_block: MonoBlock | None = None

    def set_privilege_status(self, status: PrivilegeStatus) -> None:
        if status.can_capture_packets:
            self._privilege_note.setText(
                "✓ This system can run real packet capture (scapy + capture backend detected)."
            )
            self._privilege_note.setStyleSheet(f"color: {DARK['success']}; font-size: 11px;")
        else:
            note = status.detail
            if "Packet capture:" in status.detail:
                note = status.detail.split("Packet capture:")[1].strip()
            self._privilege_note.setText(
                "Real packet capture isn't available right now, so Simulation mode is selected. " + note
            )
            self._privilege_note.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
            self.mode_toggle._buttons["simulated"].setChecked(True)
            self.mode_toggle._buttons["real"].setEnabled(False)

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, target: str, use_real: bool) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        mode_text = "Capturing real packets for" if use_real else "Generating a simulated capture for"
        loading = EmptyState(f"{mode_text} {target}…")
        self._layout.insertWidget(1, loading)
        self._widgets.append(loading)

    def show_result(self, result: PacketCaptureResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if result.error:
            self.show_error(result.error)
            return

        if not result.packets:
            empty = Card("No Packets Captured")
            msg = ("No packets matching this connection were seen during the capture window. "
                   "Real captures depend on timing — try again, or switch to Simulation mode."
                   if result.source.value == "real" else
                   "The simulation produced no packets, which shouldn't normally happen.")
            empty.add_widget(QLabel(msg))
            self._layout.insertWidget(1, empty)
            self._widgets.append(empty)
            return

        self._all_packets = result.packets

        # --- Header: badge + filter ---
        header_card = Card("Captured Packets")
        badge_row = QWidget()
        badge_layout = QHBoxLayout(badge_row)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.addWidget(DataSourceBadge(result.source.value == "real"))
        badge_layout.addStretch()
        meta = QLabel(f"{len(result.packets)} packets  •  {result.capture_duration_ms:.0f} ms capture window")
        meta.setObjectName("cardMeta")
        badge_layout.addWidget(meta)
        header_card.add_widget(badge_row)

        filter_bar = ProtocolFilterBar(result.protocol_counts())
        for protocol, btn in filter_bar.buttons.items():
            btn.clicked.connect(lambda _checked, p=protocol: self._apply_filter(p))
        header_card.add_widget(filter_bar)

        self._layout.insertWidget(1, header_card)
        self._widgets.append(header_card)

        # --- Packet table + detail split ---
        split_card = Card("")
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["#", "Protocol", "Source", "Destination", "Length"])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(220)
        self._table = table

        detail_block = MonoBlock("Select a packet above to see its details.")
        detail_block.setMinimumHeight(140)
        self._detail_block = detail_block

        table.itemSelectionChanged.connect(self._on_selection_changed)

        splitter.addWidget(table)
        splitter.addWidget(detail_block)
        splitter.setSizes([320, 160])

        split_card.add_widget(splitter)
        self._layout.insertWidget(2, split_card)
        self._widgets.append(split_card)

        self._populate_table(result.packets)

    def _populate_table(self, packets) -> None:
        if self._table is None:
            return
        table = self._table
        table.setRowCount(len(packets))

        for row, pkt in enumerate(packets):
            table.setItem(row, 0, QTableWidgetItem(str(pkt.packet_number)))

            proto_item = QTableWidgetItem(pkt.protocol)
            proto_item.setForeground(QColor(protocol_color(pkt.protocol)))
            table.setItem(row, 1, proto_item)

            table.setItem(row, 2, QTableWidgetItem(pkt.source))
            table.setItem(row, 3, QTableWidgetItem(pkt.destination))
            table.setItem(row, 4, QTableWidgetItem(f"{pkt.length_bytes} B"))

        table.setProperty("packets_ref", packets)

    def _apply_filter(self, protocol: str) -> None:
        if protocol == ALL_PROTOCOLS:
            filtered = self._all_packets
        else:
            filtered = [p for p in self._all_packets if p.protocol == protocol]
        self._populate_table(filtered)

    def _on_selection_changed(self) -> None:
        if self._table is None or self._detail_block is None:
            return
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        packets = self._table.property("packets_ref") or []
        if 0 <= row < len(packets):
            pkt = packets[row]
            header = f"Packet #{pkt.packet_number}  •  {pkt.protocol}  •  t={pkt.timestamp_offset_ms:.1f}ms\n"
            header += f"{pkt.source} -> {pkt.destination}  •  {pkt.length_bytes} bytes\n"
            if pkt.flags:
                header += f"Flags: {', '.join(pkt.flags)}\n"
            header += "\n" + (pkt.detail or pkt.summary)
            self._detail_block.set_text(header)

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("Packet Capture Failed")
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
        self._table = None
        self._detail_block = None
        self._all_packets = []
