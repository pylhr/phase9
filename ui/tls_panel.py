"""
UI Layer — TLS Handshake Explorer panel (Module 5).

Shows: the negotiation flow (Client Hello -> Server Hello -> Cert Exchange ->
Key Exchange -> Session Established), TLS version, cipher suite, certificate
chain, and certificate expiration — all from a real handshake.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from data.models import TLSResult
from ui.theme import DARK
from ui.widgets import Card, EmptyState


class StageBox(QLabel):
    """One stage in the TLS negotiation flow diagram."""

    def __init__(self, title: str, active: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        color = DARK["accent"] if active else DARK["text_muted"]
        self.setText(f"<span style='color:{color}; font-size:12px; font-weight:600;'>{title}</span>")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        border = color if active else DARK["border"]
        self.setStyleSheet(f"""
            background-color: {DARK['bg_elevated']};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 12px 10px;
        """)
        self.setMinimumWidth(130)
        self.setWordWrap(True)


class DownArrow(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("↓", parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 16px;")


def _kv_row(label: str, value: str, value_color: str | None = None) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    lab = QLabel(label)
    lab.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 12px;")
    lab.setMinimumWidth(160)
    layout.addWidget(lab)
    val = QLabel(value)
    val.setStyleSheet(f"color: {value_color or DARK['text_primary']}; font-size: 12px; font-weight: 500;")
    val.setWordWrap(True)
    layout.addWidget(val, stretch=1)
    return row


class TLSExplorerPanel(QWidget):
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
            "Enter a URL above and click Explore to perform a real TLS handshake.\n"
            "You'll see exactly when encryption begins, which cipher was negotiated, "
            "and the server's certificate."
        )
        self._layout.addWidget(self._empty_state)

        self._widgets: list[QWidget] = []

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, hostname: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        loading = EmptyState(f"Negotiating TLS with {hostname}…")
        self._layout.insertWidget(0, loading)
        self._widgets.append(loading)

    def show_result(self, result: TLSResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if result.error:
            self.show_error(result.hostname, result.error)
            return

        # --- Negotiation flow diagram ---
        flow_card = Card("TLS Negotiation Flow")
        flow_col = QWidget()
        flow_layout = QVBoxLayout(flow_col)
        flow_layout.setContentsMargins(8, 4, 8, 4)
        flow_layout.setSpacing(2)
        flow_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        stages = ["Client Hello", "Server Hello", "Certificate Exchange", "Key Exchange", "Session Established"]
        for i, stage in enumerate(stages):
            box = StageBox(stage, active=True)
            box.setMaximumWidth(260)
            flow_layout.addWidget(box, alignment=Qt.AlignmentFlag.AlignHCenter)
            if i < len(stages) - 1:
                flow_layout.addWidget(DownArrow(), alignment=Qt.AlignmentFlag.AlignHCenter)

        flow_layout.addSpacing(4)
        encryption_note = QLabel(
            f"🔒 Encryption begins after <b>Key Exchange</b> — the handshake completed in "
            f"<b>{result.handshake_time_ms:.1f} ms</b>"
        )
        encryption_note.setStyleSheet(f"color: {DARK['accent']}; font-size: 12px;")
        encryption_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        flow_layout.addWidget(encryption_note)

        flow_card.add_widget(flow_col)
        self._layout.insertWidget(0, flow_card)
        self._widgets.append(flow_card)

        # --- Negotiated parameters ---
        params_card = Card("Negotiated Parameters")
        params_card.add_widget(_kv_row("TLS Version", result.tls_version or "Unknown", DARK["accent"]))
        cipher_text = result.cipher_suite or "Unknown"
        if result.cipher_bits:
            cipher_text += f"  ({result.cipher_bits}-bit)"
        params_card.add_widget(_kv_row("Cipher Suite", cipher_text))
        self._layout.insertWidget(1, params_card)
        self._widgets.append(params_card)

        # --- Certificate chain ---
        cert_card = Card("Certificate")
        cert = result.leaf_certificate
        if cert is None:
            cert_card.add_widget(QLabel("No certificate details were available from this connection."))
        else:
            cert_card.add_widget(_kv_row("Subject", cert.subject))
            cert_card.add_widget(_kv_row("Issuer", cert.issuer))

            valid_from = cert.not_before.strftime("%Y-%m-%d") if cert.not_before else "Unknown"
            valid_until = cert.not_after.strftime("%Y-%m-%d") if cert.not_after else "Unknown"
            cert_card.add_widget(_kv_row("Valid From", valid_from))

            expiry_color = DARK["text_primary"]
            expiry_suffix = ""
            if cert.is_expired:
                expiry_color = DARK["error"]
                expiry_suffix = "  ⚠ EXPIRED"
            elif cert.days_until_expiry is not None and cert.days_until_expiry <= 30:
                expiry_color = DARK["warning"]
                expiry_suffix = f"  ⚠ expires in {cert.days_until_expiry} days"

            cert_card.add_widget(_kv_row("Valid Until", valid_until + expiry_suffix, expiry_color))

            if cert.serial_number:
                cert_card.add_widget(_kv_row("Serial Number", cert.serial_number))

        self._layout.insertWidget(2, cert_card)
        self._widgets.append(cert_card)

    def show_not_applicable(self, hostname: str, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("TLS Not Applicable")
        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {DARK['text_secondary']}; font-size:13px;")
        card.add_widget(label)
        self._layout.insertWidget(0, card)
        self._widgets.append(card)

    def show_error(self, hostname: str, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("TLS Handshake Failed")
        label = QLabel(f"Could not establish a TLS session with <b>{hostname}</b>:<br>{message}")
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
