"""
UI Layer — Browser Rendering Pipeline panel (Module 15).

Illustrative simulation only — prominently labeled. Shows the 6 real
pipeline stages (DOM Construction → CSSOM → Render Tree → Layout → Paint
→ Composite) with durations scaled from the page's real DOM metrics and
real resource sizes. The source badge and explanatory text make the
simulation status unmistakable.
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data.models import RenderingPipelineResult, RenderStage
from ui.theme import DARK
from ui.widgets import Card, EmptyState

_STAGE_COLORS = [
    "#3DDC97",  # DOM Construction
    "#5EA8FF",  # CSSOM Construction
    "#F0B459",  # Render Tree
    "#C77DFF",  # Layout
    "#F2607A",  # Paint
    "#8C7CFF",  # Composite
]


def _fmt_ms(ms: float) -> str:
    return f"{ms:.1f} ms"


class StageBarsWidget(QWidget):
    """Custom-painted horizontal bars — one per stage, proportional to duration."""

    def __init__(self, stages: list[RenderStage], parent: QWidget | None = None):
        super().__init__(parent)
        self._stages = stages
        self.setMinimumHeight(len(stages) * 42 + 8)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._total = sum(s.duration_ms for s in stages) or 1.0

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        label_w = 160
        right_w = 80
        chart_w = w - label_w - right_w

        for i, stage in enumerate(self._stages):
            y = 4 + i * 42
            bar_h = 26
            frac = stage.duration_ms / self._total
            bar_w = max(int(chart_w * frac), 4)
            color = QColor(_STAGE_COLORS[i % len(_STAGE_COLORS)])

            # Stage name
            painter.setPen(QColor(DARK["text_primary"]))
            font = QFont("Segoe UI", 9)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                QRectF(0, y, label_w - 4, bar_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                stage.name,
            )

            # Colored bar
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(label_w, y, bar_w, bar_h), 4, 4)

            # Background remainder
            painter.setBrush(QColor(DARK["bg_elevated"]))
            painter.drawRoundedRect(QRectF(label_w + bar_w, y, max(chart_w - bar_w, 0), bar_h), 4, 4)

            # Duration text
            painter.setPen(QColor(DARK["text_muted"]))
            painter.setFont(QFont("Consolas", 9))
            painter.drawText(
                QRectF(label_w + chart_w + 6, y, right_w - 6, bar_h),
                Qt.AlignmentFlag.AlignVCenter,
                _fmt_ms(stage.duration_ms),
            )


class RenderingPipelinePanel(QWidget):
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
            "Enter a URL above and click Explore to see a rendering pipeline "
            "model for that real page.\n\n"
            "Stage durations are illustrative — no real browser is instrumented — "
            "but are scaled from this page's actual DOM element count, CSS volume, "
            "and resource complexity."
        )
        self._layout.addWidget(self._empty_state)
        self._widgets: list[QWidget] = []

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, url: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        loading = EmptyState(f"Waiting for page structure of {url} to model the pipeline…")
        self._layout.insertWidget(0, loading)
        self._widgets.append(loading)

    def show_result(self, result: RenderingPipelineResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if result.error:
            self.show_error(result.error)
            return

        # --- Prominent simulation disclaimer ---
        disclaimer_card = Card("")
        badge_row = QWidget()
        badge_layout = QHBoxLayout(badge_row)
        badge_layout.setContentsMargins(0, 0, 0, 0)

        badge = QLabel("◆ ILLUSTRATIVE SIMULATION")
        badge.setStyleSheet(f"""
            color: {DARK['accent_blue']};
            background-color: {DARK['accent_blue_bg']};
            border-radius: 4px; padding: 4px 10px;
            font-size: 11px; font-weight: 700;
        """)
        badge_layout.addWidget(badge)
        badge_layout.addStretch()

        meta = QLabel(f"Total illustrative pipeline time: {_fmt_ms(result.total_time_ms)}")
        meta.setObjectName("cardMeta")
        badge_layout.addWidget(meta)
        disclaimer_card.add_widget(badge_row)

        m = result.dom_metrics
        note = QLabel(
            "These timings are not from a real browser trace. Stage durations are "
            f"scaled from this page's real measured DOM complexity "
            f"({m.element_count:,} elements, max depth {m.max_depth}, "
            f"{m.script_tag_count} script tags), real CSS volume, and real resource "
            "counts — but the constant factors depend on the browser engine, CPU, "
            "GPU, and caching state, none of which this app can observe."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
        disclaimer_card.add_widget(note)

        self._layout.insertWidget(0, disclaimer_card)
        self._widgets.append(disclaimer_card)

        # --- Stage bars ---
        bars_card = Card("Pipeline Stages")
        bars_card.add_widget(StageBarsWidget(result.stages))
        self._layout.insertWidget(1, bars_card)
        self._widgets.append(bars_card)

        # --- Stage descriptions ---
        details_card = Card("What Each Stage Does")
        for i, stage in enumerate(result.stages):
            color = _STAGE_COLORS[i % len(_STAGE_COLORS)]
            header = QLabel(f"<b style='color:{color};'>{stage.name}</b> — {_fmt_ms(stage.duration_ms)}")
            header.setStyleSheet("font-size: 13px; margin-top: 6px;")
            details_card.add_widget(header)

            desc = QLabel(stage.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 12px; margin-left: 8px;")
            details_card.add_widget(desc)

        self._layout.insertWidget(2, details_card)
        self._widgets.append(details_card)

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        card = Card("Could Not Model Rendering Pipeline")
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
