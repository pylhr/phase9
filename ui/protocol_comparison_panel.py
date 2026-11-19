"""
UI Layer — Protocol Comparison Laboratory (Module 17).

Side-by-side comparison of HTTP/1.1, HTTP/2, and HTTP/3. Each protocol gets
a column showing its connection lifecycle diagram, feature checklist, and key
metrics. An overview chart at the top visualises estimated page-load timing.

The panel is self-contained — it builds a comparison from the real
PageLoadResult when one is available (scaling timings to actual page
complexity), or falls back to the standard 30-resource scenario if not.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data.models import PageLoadResult
from protocols.protocol_comparison_protocol import (
    ProtocolComparisonResult,
    ProtocolFeature,
    ProtocolProfile,
    build_protocol_comparison,
)
from ui.theme import DARK, FONT_MONO_FALLBACK
from ui.widgets import Card, EmptyState


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _ms_label(ms: float) -> str:
    if ms >= 1000:
        return f"{ms/1000:.1f}s"
    return f"{ms:.0f}ms"


def _divider() -> QWidget:
    line = QWidget()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: {DARK['border_subtle']};")
    return line


# ---------------------------------------------------------------------------
# Timing bar chart (top of panel)
# ---------------------------------------------------------------------------

class TimingBarChart(QWidget):
    """
    Horizontal bar chart comparing estimated page-load time for the three
    protocols. Bars animate in from the left when show() is called.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._profiles: list[ProtocolProfile] = []
        self._fill_fractions: list[float] = []   # 0.0 → 1.0, animated
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(130)
        self.setMaximumHeight(130)

    def set_profiles(self, profiles: list[ProtocolProfile]) -> None:
        self._profiles = profiles
        self._fill_fractions = [0.0] * len(profiles)
        self._timer.start()

    def _tick(self) -> None:
        done = True
        for i in range(len(self._fill_fractions)):
            if self._fill_fractions[i] < 1.0:
                self._fill_fractions[i] = min(1.0, self._fill_fractions[i] + 0.04)
                done = False
        self.update()
        if done:
            self._timer.stop()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._profiles:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        max_ms = max(pr.metrics.estimated_page_load_ms for pr in self._profiles)
        label_w = 60
        bar_area_w = w - label_w - 80  # right margin for time label

        row_h = h // len(self._profiles)
        bar_h = min(28, row_h - 12)
        bar_y_offset = (row_h - bar_h) // 2

        for i, (pr, frac) in enumerate(zip(self._profiles, self._fill_fractions)):
            y = i * row_h

            # Protocol name label
            p.setPen(QColor(DARK["text_secondary"]))
            font = QFont()
            font.setPointSize(10)
            font.setBold(True)
            p.setFont(font)
            p.drawText(0, y, label_w, row_h, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, pr.name)

            # Background track
            track_rect = QRectF(label_w, y + bar_y_offset, bar_area_w, bar_h)
            p.setBrush(QBrush(QColor(DARK["bg_elevated"])))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(track_rect, 4, 4)

            # Filled bar
            fill_w = bar_area_w * (pr.metrics.estimated_page_load_ms / max_ms) * frac
            if fill_w > 4:
                fill_rect = QRectF(label_w, y + bar_y_offset, fill_w, bar_h)
                p.setBrush(QBrush(QColor(pr.color)))
                p.drawRoundedRect(fill_rect, 4, 4)

            # Time label
            p.setPen(QColor(pr.color))
            font2 = QFont()
            font2.setPointSize(10)
            font2.setBold(True)
            p.setFont(font2)
            p.drawText(
                int(label_w + bar_area_w + 6), y, 80, row_h,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                _ms_label(pr.metrics.estimated_page_load_ms),
            )

        p.end()


# ---------------------------------------------------------------------------
# Feature checklist row
# ---------------------------------------------------------------------------

class FeatureRow(QWidget):
    def __init__(self, feature: ProtocolFeature, color: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(8)

        icon = "✓" if feature.supported else "✕"
        icon_color = color if feature.supported else DARK["text_disabled"]
        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(16)
        icon_lbl.setStyleSheet(f"color: {icon_color}; font-size: 13px; font-weight: 700;")
        layout.addWidget(icon_lbl)

        text = QLabel(feature.name)
        text_color = DARK["text_primary"] if feature.supported else DARK["text_muted"]
        text.setStyleSheet(f"color: {text_color}; font-size: 12px;")
        text.setWordWrap(False)
        layout.addWidget(text, stretch=1)

        if feature.detail:
            text.setToolTip(feature.detail)


# ---------------------------------------------------------------------------
# Connection diagram widget
# ---------------------------------------------------------------------------

class ConnectionDiagram(QWidget):
    """
    Simplified ladder diagram showing the client↔server message flow for
    one HTTP version. Arrows are drawn left→right or right→left with labels.
    """

    def __init__(self, profile: ProtocolProfile, parent: QWidget | None = None):
        super().__init__(parent)
        self._profile = profile
        self._computed_h = max(160, len(profile.connection_diagram) * 28 + 24)
        self.setMinimumHeight(self._computed_h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w   = self.width()
        pad = 12
        col_w = (w - pad * 2) // 2       # half for each side
        client_x = pad + col_w // 4
        server_x = w - pad - col_w // 4

        # Column header labels
        p.setPen(QColor(DARK["text_muted"]))
        hdr_font = QFont()
        hdr_font.setPointSize(8)
        hdr_font.setBold(True)
        p.setFont(hdr_font)
        p.drawText(client_x - 24, 0, 48, 18, Qt.AlignmentFlag.AlignCenter, "CLIENT")
        p.drawText(server_x - 24, 0, 48, 18, Qt.AlignmentFlag.AlignCenter, "SERVER")

        # Vertical lifelines
        p.setPen(QPen(QColor(DARK["border"]), 1, Qt.PenStyle.DashLine))
        p.drawLine(client_x, 18, client_x, self._computed_h - 4)
        p.drawLine(server_x, 18, server_x, self._computed_h - 4)

        step_h = 28
        y0 = 24

        arrow_font = QFont()
        arrow_font.setFamily(FONT_MONO_FALLBACK)
        arrow_font.setPointSize(9)

        note_font = QFont()
        note_font.setPointSize(8)

        for i, step in enumerate(self._profile.connection_diagram):
            y = y0 + i * step_h
            mid_y = y + step_h // 2
            color = QColor(step.color if step.color else DARK["text_muted"])

            if step.direction == "note":
                p.setPen(QColor(DARK["text_muted"]))
                p.setFont(note_font)
                p.drawText(pad, mid_y - 8, w - pad * 2, 18,
                           Qt.AlignmentFlag.AlignCenter, step.label)
                continue

            # Arrow
            pen = QPen(color, 1.5)
            p.setPen(pen)
            if step.direction == "client_to_server":
                ax, bx = client_x, server_x
            else:
                ax, bx = server_x, client_x

            p.drawLine(ax, mid_y, bx, mid_y)
            # Arrowhead
            d = 6
            if bx > ax:
                p.drawLine(bx, mid_y, bx - d, mid_y - d)
                p.drawLine(bx, mid_y, bx - d, mid_y + d)
            else:
                p.drawLine(bx, mid_y, bx + d, mid_y - d)
                p.drawLine(bx, mid_y, bx + d, mid_y + d)

            # Label above arrow
            p.setFont(arrow_font)
            lbl_x = min(ax, bx) + 2
            lbl_w = abs(bx - ax) - 4
            p.drawText(lbl_x, mid_y - step_h // 2, lbl_w, step_h // 2,
                       Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
                       step.label)

        p.end()


# ---------------------------------------------------------------------------
# One protocol column
# ---------------------------------------------------------------------------

class ProtocolColumn(QWidget):
    """Full column for one HTTP version: header, metrics, diagram, features."""

    def __init__(self, profile: ProtocolProfile, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # --- Header ---
        header_card = QFrame()
        header_card.setObjectName("card")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(14, 12, 14, 14)
        header_layout.setSpacing(4)

        name_row = QHBoxLayout()
        name_lbl = QLabel(profile.name)
        name_lbl.setStyleSheet(
            f"color: {profile.color}; font-size: 16px; font-weight: 700;"
        )
        name_row.addWidget(name_lbl)
        name_row.addStretch()
        year_lbl = QLabel(str(profile.introduced_year))
        year_lbl.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 12px;")
        name_row.addWidget(year_lbl)
        header_layout.addLayout(name_row)

        rfc_lbl = QLabel(f"{profile.rfc}  ·  {profile.transport}")
        rfc_lbl.setStyleSheet(
            f"color: {DARK['text_muted']}; font-size: 11px;"
            f" font-family: '{FONT_MONO_FALLBACK}';"
        )
        header_layout.addWidget(rfc_lbl)

        tagline_lbl = QLabel(profile.tagline)
        tagline_lbl.setWordWrap(True)
        tagline_lbl.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 12px; margin-top: 4px;")
        header_layout.addWidget(tagline_lbl)

        layout.addWidget(header_card)

        # --- Key metrics ---
        metrics_card = QFrame()
        metrics_card.setObjectName("card")
        m_layout = QVBoxLayout(metrics_card)
        m_layout.setContentsMargins(14, 12, 14, 12)
        m_layout.setSpacing(6)

        title = QLabel("KEY METRICS")
        title.setObjectName("sectionLabel")
        m_layout.addWidget(title)

        m = profile.metrics
        rows = [
            ("TTFB (50ms RTT)",      _ms_label(m.estimated_ttfb_ms),       profile.color),
            ("Page load (30 res.)",  _ms_label(m.estimated_page_load_ms),  profile.color),
            ("TCP setup",            f"{m.tcp_handshake_rtts} RTT",        DARK["text_secondary"]),
            ("TLS setup",            f"{m.tls_handshake_rtts} RTT",        DARK["text_secondary"]),
            ("Max streams",          "∞" if m.max_concurrent_streams < 0
                                     else str(m.max_concurrent_streams),   DARK["text_secondary"]),
            ("HOL blocking",         m.hol_blocking,                       DARK["text_secondary"]),
            ("Header compression",   m.header_compression,                 DARK["text_secondary"]),
        ]
        for label, value, val_color in rows:
            row_w = QWidget()
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
            val = QLabel(value)
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            val.setStyleSheet(f"color: {val_color}; font-size: 11px; font-weight: 600;")
            rl.addWidget(lbl, stretch=1)
            rl.addWidget(val)
            m_layout.addWidget(row_w)

        layout.addWidget(metrics_card)

        # --- Connection diagram ---
        diag_card = QFrame()
        diag_card.setObjectName("card")
        diag_layout = QVBoxLayout(diag_card)
        diag_layout.setContentsMargins(14, 12, 14, 12)
        diag_layout.setSpacing(8)

        diag_title = QLabel("CONNECTION LIFECYCLE")
        diag_title.setObjectName("sectionLabel")
        diag_layout.addWidget(diag_title)

        diag = ConnectionDiagram(profile)
        diag_layout.addWidget(diag)
        layout.addWidget(diag_card)

        # --- Features ---
        feat_card = QFrame()
        feat_card.setObjectName("card")
        feat_layout = QVBoxLayout(feat_card)
        feat_layout.setContentsMargins(14, 12, 14, 12)
        feat_layout.setSpacing(0)

        feat_title = QLabel("FEATURES")
        feat_title.setObjectName("sectionLabel")
        feat_layout.addWidget(feat_title)
        feat_layout.addWidget(_divider())

        for feat in profile.features:
            feat_layout.addWidget(FeatureRow(feat, profile.color))

        layout.addWidget(feat_card)

        # --- Strengths / weaknesses ---
        sw_card = QFrame()
        sw_card.setObjectName("card")
        sw_layout = QVBoxLayout(sw_card)
        sw_layout.setContentsMargins(14, 12, 14, 12)
        sw_layout.setSpacing(4)

        sw_title = QLabel("STRENGTHS")
        sw_title.setObjectName("sectionLabel")
        sw_layout.addWidget(sw_title)
        for item in profile.strengths:
            lbl = QLabel(f"✓  {item}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {DARK['success']}; font-size: 11px; padding: 2px 0;")
            sw_layout.addWidget(lbl)

        if profile.strengths and profile.weaknesses:
            sw_layout.addWidget(_divider())

        w_title = QLabel("LIMITATIONS")
        w_title.setObjectName("sectionLabel")
        sw_layout.addWidget(w_title)
        for item in profile.weaknesses:
            lbl = QLabel(f"✕  {item}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 11px; padding: 2px 0;")
            sw_layout.addWidget(lbl)

        layout.addWidget(sw_card)
        layout.addStretch()


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

class ProtocolComparisonPanel(QWidget):
    """
    Module 17: Protocol Comparison Laboratory.

    Always shows data — uses a real PageLoadResult to tune timing estimates
    when available, otherwise falls back to the standard 30-resource scenario.
    The panel updates each time a new exploration completes.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._result: ProtocolComparisonResult | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        self._content = QWidget()
        scroll.setWidget(self._content)

        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(24, 20, 24, 24)
        self._layout.setSpacing(20)

        self._build_default()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_result(self, page_load: PageLoadResult | None = None) -> None:
        """
        Build or refresh the comparison.  Call with the PageLoadResult after
        an exploration completes to use real resource counts and sizes.
        """
        resource_count = len(page_load.resources) if page_load else None
        page_size_bytes = page_load.total_bytes if page_load else None
        page_url = page_load.page_url if page_load else None

        result = build_protocol_comparison(
            page_url=page_url,
            resource_count=resource_count,
            page_size_bytes=page_size_bytes,
        )
        self._result = result
        self._rebuild(result)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build_default(self) -> None:
        """Show generic comparison (no real page data yet)."""
        result = build_protocol_comparison()
        self._rebuild(result, is_default=True)

    def _rebuild(self, result: ProtocolComparisonResult, is_default: bool = False) -> None:
        self._clear()

        # --- Page title ---
        title_row = QWidget()
        title_layout = QHBoxLayout(title_row)
        title_layout.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel("Protocol Comparison Laboratory")
        title_lbl.setStyleSheet(
            f"color: {DARK['text_primary']}; font-size: 18px; font-weight: 700;"
        )
        title_layout.addWidget(title_lbl)
        title_layout.addStretch()

        if result.page_url and not is_default:
            ctx_lbl = QLabel(f"Tuned to  {result.page_url}"
                             f"  ({result.resource_count} resources, "
                             f"{(result.page_size_bytes or 0)//1024} KB)")
            ctx_lbl.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
            title_layout.addWidget(ctx_lbl)
        elif is_default:
            ctx_lbl = QLabel("Standard 30-resource / 500 KB scenario  ·  Explore a URL to tune to your page")
            ctx_lbl.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
            title_layout.addWidget(ctx_lbl)

        self._layout.addWidget(title_row)

        # --- Timing bar chart ---
        chart_card = Card("Estimated Page-Load Time  (50 ms RTT, 10 Mbps link)")
        chart = TimingBarChart()
        chart.set_profiles(result.protocols)
        chart_card.add_widget(chart)

        note = QLabel(
            "Timings are illustrative estimates computed from RFC handshake RTT counts and page complexity — "
            "not live network measurements. Real results depend on server location, CDN, caching, and link quality."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 10px; margin-top: 2px;")
        chart_card.add_widget(note)
        self._layout.addWidget(chart_card)

        # --- Three-column layout ---
        columns_widget = QWidget()
        cols_layout = QHBoxLayout(columns_widget)
        cols_layout.setContentsMargins(0, 0, 0, 0)
        cols_layout.setSpacing(16)

        for profile in result.protocols:
            col = ProtocolColumn(profile)
            cols_layout.addWidget(col, stretch=1)

        self._layout.addWidget(columns_widget)
        self._layout.addStretch()
