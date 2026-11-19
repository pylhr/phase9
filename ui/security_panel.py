"""
UI Layer — Security Inspector panel (Module 14).

Shows a real security evaluation built from the actual TLS state and
response headers already fetched: TLS version, certificate validity, HSTS,
CSP, and other security headers — with a score and per-check explanations.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from data.models import HTTPExchangeResult, SecurityCheck, SecurityReport, TLSResult
from protocols.security_protocol import analyze_security
from ui.theme import DARK
from ui.widgets import Card, EmptyState

_SEVERITY_COLOR = {
    "good": DARK["success"],
    "warning": DARK["warning"],
    "critical": DARK["error"],
}


class ScoreRing(QWidget):
    """A simple circular progress ring showing the overall security score."""

    def __init__(self, score: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._score = score
        self.setFixedSize(88, 88)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(6, 6, -6, -6)

        if self._score >= 85:
            color = QColor(DARK["success"])
        elif self._score >= 60:
            color = QColor(DARK["warning"])
        else:
            color = QColor(DARK["error"])

        bg_pen = QPen(QColor(DARK["bg_elevated"]), 7)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        fg_pen = QPen(color, 7)
        fg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(fg_pen)
        span = int(360 * 16 * (self._score / 100))
        painter.drawArc(rect, 90 * 16, -span)

        painter.setPen(QPen(QColor(DARK["text_primary"])))
        font = painter.font()
        font.setPointSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self._score))


class CheckRow(QWidget):
    def __init__(self, check: SecurityCheck, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        color = _SEVERITY_COLOR.get(check.severity, DARK["text_secondary"])
        icon = "✓" if check.passed else ("✕" if check.severity == "critical" else "!")
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 700;")
        icon_label.setFixedWidth(18)
        header_layout.addWidget(icon_label)

        name_label = QLabel(check.name)
        name_label.setStyleSheet(f"color: {DARK['text_primary']}; font-size: 13px; font-weight: 600;")
        header_layout.addWidget(name_label)
        header_layout.addStretch()

        layout.addWidget(header)

        detail_label = QLabel(check.detail)
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 12px; margin-left: 26px;")
        layout.addWidget(detail_label)

        if check.header_value:
            value_text = check.header_value
            if len(value_text) > 100:
                value_text = value_text[:97] + "…"
            value_label = QLabel(value_text)
            value_label.setWordWrap(True)
            value_label.setStyleSheet(
                f"color: {DARK['text_muted']}; font-size: 11px; font-family: Consolas; margin-left: 26px;"
            )
            layout.addWidget(value_label)


class SecurityInspectorPanel(QWidget):
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
            "Enter a URL above and click Explore to run a real security check.\n"
            "This evaluates the actual TLS connection and response headers against "
            "common best practices — TLS version, certificate validity, HSTS, CSP, and more."
        )
        self._layout.addWidget(self._empty_state)

        self._widgets: list[QWidget] = []
        self._last_url: str | None = None
        self._last_exchange: HTTPExchangeResult | None = None
        self._last_tls: TLSResult | None = None

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)
        self._last_exchange = None
        self._last_tls = None

    def show_loading(self, url: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        self._last_url = url
        self._last_exchange = None
        self._last_tls = None
        loading = EmptyState(f"Evaluating {url}'s security posture…")
        self._layout.insertWidget(0, loading)
        self._widgets.append(loading)

    def set_http_exchange(self, exchange: HTTPExchangeResult) -> None:
        """Security needs both HTTP and TLS data — store each as it arrives, render once HTTP is in."""
        self._last_exchange = exchange
        self._maybe_render()

    def set_tls_result(self, tls: TLSResult) -> None:
        self._last_tls = tls
        self._maybe_render()

    def _maybe_render(self) -> None:
        # Render as soon as we have the HTTP side — TLS is optional (e.g.
        # plain HTTP sites legitimately have no TLS result at all), so we
        # don't block forever waiting for a TLS result that will never come.
        if self._last_exchange is not None:
            self._render()

    def _render(self) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        exchange = self._last_exchange
        if exchange is None:
            return

        if exchange.error or exchange.response is None:
            self.show_error(exchange.error or "No response was received.")
            return

        report = analyze_security(self._last_url or "", exchange.response, self._last_tls)
        self._render_report(report)

    def _render_report(self, report: SecurityReport) -> None:
        # --- Score card ---
        score_card = Card("Security Score")
        score_row = QWidget()
        score_layout = QHBoxLayout(score_row)
        score_layout.setContentsMargins(0, 4, 0, 4)
        score_layout.setSpacing(20)

        score_layout.addWidget(ScoreRing(report.score))

        summary_col = QWidget()
        summary_layout = QVBoxLayout(summary_col)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(4)

        passed = sum(1 for c in report.checks if c.passed)
        summary_text = QLabel(f"<b>{passed} / {len(report.checks)}</b> checks passed")
        summary_text.setStyleSheet(f"color: {DARK['text_primary']}; font-size: 14px;")
        summary_layout.addWidget(summary_text)

        if report.critical_count:
            crit_label = QLabel(f"⚠ {report.critical_count} critical issue{'s' if report.critical_count != 1 else ''}")
            crit_label.setStyleSheet(f"color: {DARK['error']}; font-size: 12px; font-weight: 600;")
            summary_layout.addWidget(crit_label)
        if report.warning_count:
            warn_label = QLabel(f"{report.warning_count} warning{'s' if report.warning_count != 1 else ''}")
            warn_label.setStyleSheet(f"color: {DARK['warning']}; font-size: 12px;")
            summary_layout.addWidget(warn_label)
        if not report.critical_count and not report.warning_count:
            ok_label = QLabel("No issues found in the checks this app runs.")
            ok_label.setStyleSheet(f"color: {DARK['success']}; font-size: 12px;")
            summary_layout.addWidget(ok_label)

        summary_layout.addStretch()
        score_layout.addWidget(summary_col, stretch=1)

        score_card.add_widget(score_row)
        self._layout.insertWidget(0, score_card)
        self._widgets.append(score_card)

        # --- Per-check breakdown ---
        checks_card = Card("Detailed Findings")
        for check in report.checks:
            checks_card.add_widget(CheckRow(check))

        scope_note = QLabel(
            "This covers TLS version, certificate validity, and common response security "
            "headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy). "
            "It isn't a full penetration test or vulnerability scan."
        )
        scope_note.setWordWrap(True)
        scope_note.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px; margin-top: 8px;")
        checks_card.add_widget(scope_note)

        self._layout.insertWidget(1, checks_card)
        self._widgets.append(checks_card)

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("Could Not Run Security Check")
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
