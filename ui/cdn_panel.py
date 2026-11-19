"""
UI Layer — CDN Explorer panel (Module 13).

Shows whether a CDN fronts the site, the detected provider, and the real
evidence (response headers, IP range membership) behind that determination
— plus the User -> CDN Edge -> Origin Server flow when a CDN is detected.
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

from data.models import CDNResult
from ui.theme import DARK
from ui.widgets import Card, EmptyState

_CONFIDENCE_COLOR = {
    "high": DARK["success"],
    "medium": DARK["warning"],
    "low": DARK["text_secondary"],
    "none": DARK["text_muted"],
}


class FlowBox(QLabel):
    def __init__(self, title: str, subtitle: str, color: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setText(f"<b style='color:{color}; font-size:13px;'>{title}</b>"
                      f"<br><span style='color:{DARK['text_muted']}; font-size:11px;'>{subtitle}</span>")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(f"""
            background-color: {DARK['bg_elevated']};
            border: 1px solid {color};
            border-radius: 8px;
            padding: 14px 16px;
        """)
        self.setMinimumWidth(150)
        self.setMaximumWidth(190)


def _kv_row(label: str, value: str, value_color: str | None = None) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    lab = QLabel(label)
    lab.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 12px;")
    lab.setMinimumWidth(140)
    layout.addWidget(lab)
    val = QLabel(value)
    val.setStyleSheet(f"color: {value_color or DARK['text_primary']}; font-size: 12px; font-weight: 500;")
    val.setWordWrap(True)
    layout.addWidget(val, stretch=1)
    return row


class CDNExplorerPanel(QWidget):
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
            "Enter a URL above and click Explore to check for a real CDN.\n"
            "This looks at the actual response headers and the resolved IP's "
            "real published address ranges — no guessing."
        )
        self._layout.addWidget(self._empty_state)

        self._widgets: list[QWidget] = []

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, url: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        loading = EmptyState(f"Checking {url} for CDN signals…")
        self._layout.insertWidget(0, loading)
        self._widgets.append(loading)

    def show_result(self, result: CDNResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if result.error:
            self.show_error(result.error)
            return

        # --- Summary card ---
        summary_card = Card("CDN Detection")

        confidence_color = _CONFIDENCE_COLOR.get(result.confidence, DARK["text_muted"])

        if result.is_cdn_detected:
            provider_text = result.detected_provider or "Unknown CDN/proxy"
            headline = QLabel(
                f"<b style='font-size:16px; color:{DARK['accent']};'>✓ CDN Detected: {provider_text}</b>"
            )
        else:
            headline = QLabel(
                f"<b style='font-size:16px; color:{DARK['text_secondary']};'>No CDN Detected</b>"
            )
        summary_card.add_widget(headline)

        summary_card.add_widget(_kv_row("Confidence", result.confidence.capitalize(), confidence_color))
        summary_card.add_widget(_kv_row("Hostname", result.hostname))
        if result.resolved_ip:
            summary_card.add_widget(_kv_row("Resolved IP", result.resolved_ip))

        self._layout.insertWidget(0, summary_card)
        self._widgets.append(summary_card)

        # --- Flow diagram (only meaningful when a CDN is actually detected) ---
        if result.is_cdn_detected:
            flow_card = Card("Request Path")
            flow_row = QWidget()
            flow_layout = QHBoxLayout(flow_row)
            flow_layout.setContentsMargins(8, 8, 8, 8)
            flow_layout.setSpacing(4)

            provider_label = result.detected_provider or "CDN Edge"
            flow_layout.addStretch()
            flow_layout.addWidget(FlowBox("User", "your computer", DARK["accent_blue"]))
            arrow1 = QLabel("→")
            arrow1.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 16px;")
            flow_layout.addWidget(arrow1)
            flow_layout.addWidget(FlowBox(provider_label, "nearest edge node", DARK["accent"]))
            arrow2 = QLabel("→")
            arrow2.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 16px;")
            flow_layout.addWidget(arrow2)
            flow_layout.addWidget(FlowBox("Origin Server", "the real backend", DARK["chip_mx"]))
            flow_layout.addStretch()

            flow_card.add_widget(flow_row)

            explanation = QLabel(
                f"Your request likely hits a {provider_label} edge server near you first, which "
                f"either serves a cached copy or forwards the request to the real origin server. "
                f"This app can't directly observe the origin's actual location from here — only "
                f"that {provider_label} is in the path, based on the evidence below."
            )
            explanation.setWordWrap(True)
            explanation.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
            flow_card.add_widget(explanation)

            self._layout.insertWidget(1, flow_card)
            self._widgets.append(flow_card)

        # --- Evidence ---
        if result.signals:
            evidence_card = Card("Evidence")
            for signal in result.signals:
                provider_text = (f" → {signal.indicates_provider}" if signal.indicates_provider
                                  else " (generic CDN/proxy signal)")
                line = QLabel(
                    f"<code>{signal.header_name}</code>: {signal.header_value}"
                    f"<span style='color:{DARK['accent']};'>{provider_text}</span>"
                )
                line.setWordWrap(True)
                line.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 12px; padding: 2px 0;")
                evidence_card.add_widget(line)

            insertion_index = 2 if result.is_cdn_detected else 1
            self._layout.insertWidget(insertion_index, evidence_card)
            self._widgets.append(evidence_card)
        elif not result.is_cdn_detected:
            note_card = Card("")
            note = QLabel(
                "No CDN-identifying headers or known CDN IP ranges were found. This site may be "
                "served directly from its own infrastructure, or may use a CDN whose signals "
                "aren't in this app's detection list."
            )
            note.setWordWrap(True)
            note.setObjectName("cardMeta")
            note_card.add_widget(note)
            self._layout.insertWidget(1, note_card)
            self._widgets.append(note_card)

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("CDN Check Failed")
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
