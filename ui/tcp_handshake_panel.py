"""
UI Layer — TCP Handshake Visualizer panel (Module 4).

Shows the three-way handshake (Client -SYN-> Server, Client <-SYN/ACK-
Server, Client -ACK-> Server) as a custom-painted diagram with two columns
(Client, Server) and diagonal arrows between them, annotated with real
sequence numbers, ACK numbers, flags, and per-step timing.
"""
from __future__ import annotations

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

from data.models import PrivilegeStatus, TCPHandshakeResult, TCPHandshakeStep
from ui.theme import DARK, FONT_MONO_FALLBACK
from ui.widgets import Card, DataSourceBadge, EmptyState, SegmentedToggle

ROW_HEIGHT = 90
COLUMN_INSET = 90


class HandshakeDiagram(QWidget):
    """Custom-painted Client/Server columns with arrows for each handshake step."""

    def __init__(self, steps: list[TCPHandshakeStep], parent: QWidget | None = None):
        super().__init__(parent)
        self._steps = steps
        self.setMinimumHeight(60 + len(steps) * ROW_HEIGHT)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        client_x = COLUMN_INSET
        server_x = width - COLUMN_INSET

        # --- Column headers ---
        header_font = QFont("Segoe UI", 11)
        header_font.setBold(True)
        painter.setFont(header_font)

        for x, label, color in [(client_x, "CLIENT", DARK["accent_blue"]), (server_x, "SERVER", DARK["accent"])]:
            painter.setPen(QPen(QColor(color)))
            painter.drawText(QRectF(x - 60, 4, 120, 24), Qt.AlignmentFlag.AlignCenter, label)

        # Vertical lifelines
        painter.setPen(QPen(QColor(DARK["border"]), 1.5))
        painter.drawLine(client_x, 32, client_x, self.height() - 8)
        painter.drawLine(server_x, 32, server_x, self.height() - 8)

        mono_font = QFont(FONT_MONO_FALLBACK, 9)

        for i, step in enumerate(self._steps):
            y = 50 + i * ROW_HEIGHT
            is_client_to_server = step.direction == "client_to_server"
            start_x = client_x if is_client_to_server else server_x
            end_x = server_x if is_client_to_server else client_x

            color = QColor(DARK["accent"] if "SYN" in step.flags and "ACK" not in step.flags
                            else DARK["accent_blue"] if "ACK" in step.flags and "SYN" not in step.flags
                            else DARK["chip_mx"])

            # Arrow line
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(start_x, y), QPointF(end_x, y))

            # Arrowhead
            direction = 1 if end_x > start_x else -1
            arrow_size = 7
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            tip = QPointF(end_x - direction * 2, y)
            painter.drawPolygon([
                tip,
                QPointF(tip.x() - direction * arrow_size, tip.y() - arrow_size / 1.6),
                QPointF(tip.x() - direction * arrow_size, tip.y() + arrow_size / 1.6),
            ])

            # Flag label above the arrow
            flag_text = "/".join(step.flags)
            painter.setPen(QPen(color))
            label_font = QFont("Segoe UI", 10)
            label_font.setBold(True)
            painter.setFont(label_font)
            mid_x = (start_x + end_x) / 2
            painter.drawText(QRectF(mid_x - 80, y - 28, 160, 18), Qt.AlignmentFlag.AlignCenter, flag_text)

            # Detail line below the arrow: seq/ack/window
            painter.setFont(mono_font)
            painter.setPen(QPen(QColor(DARK["text_muted"])))
            detail_parts = []
            if step.sequence_number is not None:
                detail_parts.append(f"seq={step.sequence_number}")
            if step.ack_number is not None:
                detail_parts.append(f"ack={step.ack_number}")
            if step.window_size is not None:
                detail_parts.append(f"win={step.window_size}")
            detail_text = "  ".join(detail_parts)
            painter.drawText(QRectF(mid_x - 160, y + 8, 320, 16), Qt.AlignmentFlag.AlignCenter, detail_text)

            if step.rtt_ms is not None:
                painter.setPen(QPen(QColor(DARK["text_secondary"])))
                painter.drawText(QRectF(mid_x - 80, y + 24, 160, 16), Qt.AlignmentFlag.AlignCenter,
                                  f"+{step.rtt_ms:.2f} ms")


class TCPHandshakePanel(QWidget):
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

        # --- Mode toggle ---
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
            "Enter a URL above and click Explore to capture a real TCP three-way handshake.\n"
            "You'll see the genuine SYN, SYN-ACK, and ACK packets with their real sequence numbers."
        )
        self._layout.addWidget(self._empty_state)

        self._widgets: list[QWidget] = []

    def set_privilege_status(self, status: PrivilegeStatus) -> None:
        if status.can_capture_packets:
            self._privilege_note.setText(
                "✓ This system can capture a real TCP handshake (scapy + capture backend detected)."
            )
            self._privilege_note.setStyleSheet(f"color: {DARK['success']}; font-size: 11px;")
        else:
            note = status.detail
            if "Packet capture:" in status.detail:
                note = status.detail.split("Packet capture:")[1].strip()
            self._privilege_note.setText(
                "Real handshake capture isn't available right now, so Simulation mode is selected. " + note
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
        mode_text = "Capturing a real TCP handshake with" if use_real else "Simulating a TCP handshake with"
        loading = EmptyState(f"{mode_text} {target}…")
        self._layout.insertWidget(1, loading)
        self._widgets.append(loading)

    def show_result(self, result: TCPHandshakeResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if result.error and not result.steps:
            self.show_error(result.error)
            return

        # --- Badge + diagram ---
        diagram_card = Card("Three-Way Handshake")
        badge_row = QWidget()
        badge_layout = QHBoxLayout(badge_row)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.addWidget(DataSourceBadge(result.source.value == "real"))
        badge_layout.addStretch()
        meta = QLabel(f"{result.target}:{result.port}  •  {result.total_time_ms:.2f} ms handshake time")
        meta.setObjectName("cardMeta")
        badge_layout.addWidget(meta)
        diagram_card.add_widget(badge_row)

        if result.error:
            warn = QLabel(f"⚠ {result.error}")
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {DARK['warning']}; font-size: 12px;")
            diagram_card.add_widget(warn)

        diagram_card.add_widget(HandshakeDiagram(result.steps))
        self._layout.insertWidget(1, diagram_card)
        self._widgets.append(diagram_card)

        # --- Step detail table ---
        if result.steps:
            table_card = Card("Packet Detail")
            table = QTableWidget()
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["#", "Direction", "Flags", "Sequence", "Ack", "Window"])
            table.setRowCount(len(result.steps))
            table.verticalHeader().setVisible(False)
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

            for row, step in enumerate(result.steps):
                table.setItem(row, 0, QTableWidgetItem(str(step.step_number)))
                direction_text = "Client → Server" if step.direction == "client_to_server" else "Server → Client"
                table.setItem(row, 1, QTableWidgetItem(direction_text))
                table.setItem(row, 2, QTableWidgetItem("/".join(step.flags)))
                table.setItem(row, 3, QTableWidgetItem(
                    str(step.sequence_number) if step.sequence_number is not None else "—"))
                table.setItem(row, 4, QTableWidgetItem(
                    str(step.ack_number) if step.ack_number is not None else "—"))
                table.setItem(row, 5, QTableWidgetItem(
                    str(step.window_size) if step.window_size is not None else "—"))

            table.setMinimumHeight(min(40 + 30 * max(len(result.steps), 1), 200))
            table_card.add_widget(table)
            self._layout.insertWidget(2, table_card)
            self._widgets.append(table_card)

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("Handshake Capture Failed")
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
