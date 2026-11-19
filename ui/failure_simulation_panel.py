"""
UI Layer — Failure Simulation Laboratory (Module 18).

Lets the user pick a failure scenario from a left-hand list and see a
detailed animated timeline of what that failure looks like: which stages
succeed, which stall, and which fail — with technical explanations and
real-world mitigations.

The panel is fully interactive standalone (no Explore needed), but becomes
richer when a real PageLoadResult is available, since basline timing
estimates are then grounded in the actual page's complexity.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QRectF, QTimer
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data.models import PageLoadResult
from protocols.failure_simulation_protocol import (
    ALL_SCENARIOS,
    FailureSimulationResult,
    FailureType,
    SimulatedStageResult,
    simulate_failure,
)
from ui.theme import DARK, FONT_MONO_FALLBACK
from ui.widgets import Card


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ms_label(ms: float) -> str:
    if ms >= 60_000:
        return f"{ms/1000:.0f}s"
    if ms >= 1000:
        return f"{ms/1000:.1f}s"
    return f"{ms:.0f}ms"


def _divider(color: str | None = None) -> QWidget:
    w = QWidget()
    w.setFixedHeight(1)
    w.setStyleSheet(f"background-color: {color or DARK['border_subtle']};")
    return w


# ---------------------------------------------------------------------------
# Animated Waterfall / Timeline for one scenario
# ---------------------------------------------------------------------------

class FailureTimeline(QWidget):
    """
    Horizontal bar timeline for one FailureSimulationResult.
    Bars animate in from left, coloured by stage status.
    Skipped stages are shown as a thin grey bar.
    """

    _BAR_H    = 26
    _LABEL_W  = 200
    _TIME_W   = 80
    _ROW_GAP  = 6

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._stages: list[SimulatedStageResult] = []
        self._fracs: list[float] = []
        self._max_ms = 1.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_result(self, result: FailureSimulationResult) -> None:
        self._stages = result.stages
        positive = [s.duration_ms for s in result.stages if s.duration_ms > 0]
        self._max_ms = max(positive) if positive else 1.0
        self._fracs = [0.0] * len(self._stages)
        total_h = len(self._stages) * (self._BAR_H + self._ROW_GAP) + 10
        self.setFixedHeight(total_h)
        self._timer.start()
        self.update()

    def _tick(self) -> None:
        done = True
        for i, s in enumerate(self._stages):
            if s.duration_ms > 0 and self._fracs[i] < 1.0:
                # Stagger: each bar starts after the previous has reached 30%
                start_gate = max(0.0, (i * 0.12) - 0.1)
                progress_sum = sum(self._fracs[:i]) / max(1, i) if i > 0 else 1.0
                if progress_sum >= start_gate or i == 0:
                    self._fracs[i] = min(1.0, self._fracs[i] + 0.05)
                done = False
            elif s.duration_ms == 0:
                self._fracs[i] = 1.0
        self.update()
        if done:
            self._timer.stop()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._stages:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        bar_area_w = w - self._LABEL_W - self._TIME_W - 16

        row_h = self._BAR_H + self._ROW_GAP
        lbl_font = QFont()
        lbl_font.setPointSize(10)
        time_font = QFont()
        time_font.setFamily(FONT_MONO_FALLBACK)
        time_font.setPointSize(9)

        for i, (stage, frac) in enumerate(zip(self._stages, self._fracs)):
            y = i * row_h + 4

            # Label
            p.setPen(QColor(DARK["text_secondary"] if stage.status != "skipped" else DARK["text_disabled"]))
            p.setFont(lbl_font)
            p.drawText(0, y, self._LABEL_W - 8, self._BAR_H,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       stage.stage_name)

            bar_x = self._LABEL_W
            bar_y = y + (self._BAR_H - 16) // 2
            bar_track_w = bar_area_w

            # Track
            p.setBrush(QBrush(QColor(DARK["bg_elevated"])))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(bar_x, bar_y, bar_track_w, 16), 3, 3)

            if stage.status == "skipped":
                # Thin line for skipped
                p.setBrush(QBrush(QColor(DARK["border"])))
                p.drawRoundedRect(QRectF(bar_x, bar_y + 6, bar_track_w, 4), 2, 2)
            elif stage.duration_ms > 0:
                # Proportion of max
                proportion = stage.duration_ms / self._max_ms
                fill_w = max(8.0, bar_track_w * proportion * frac)

                # Gradient-ish: use base color with a subtle fade
                bar_color = QColor(stage.color)
                if stage.status in ("ok",):
                    bar_color.setAlphaF(0.85)

                p.setBrush(QBrush(bar_color))
                p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, 16), 3, 3)

            # Time label
            p.setPen(QColor(stage.color if stage.status != "skipped" else DARK["text_disabled"]))
            p.setFont(time_font)
            time_str = "—" if stage.status == "skipped" else _ms_label(stage.duration_ms)
            p.drawText(bar_x + bar_area_w + 4, y, self._TIME_W, self._BAR_H,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       time_str)

        p.end()


# ---------------------------------------------------------------------------
# Scenario result view
# ---------------------------------------------------------------------------

class ScenarioResultView(QWidget):
    """Full view for a selected FailureSimulationResult."""

    def __init__(self, result: FailureSimulationResult, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        sc = result.scenario

        # --- Header ---
        hdr_card = QFrame()
        hdr_card.setObjectName("card")
        hdr_layout = QVBoxLayout(hdr_card)
        hdr_layout.setContentsMargins(16, 14, 16, 14)
        hdr_layout.setSpacing(6)

        title_row = QHBoxLayout()
        icon_lbl = QLabel(sc.icon)
        icon_lbl.setStyleSheet("font-size: 22px;")
        icon_lbl.setFixedWidth(32)
        title_row.addWidget(icon_lbl)
        name_lbl = QLabel(sc.name)
        name_lbl.setStyleSheet(
            f"color: {sc.color}; font-size: 18px; font-weight: 700;"
        )
        title_row.addWidget(name_lbl)
        title_row.addStretch()

        # Total time badge
        total_lbl = QLabel(_ms_label(result.total_ms))
        total_lbl.setStyleSheet(f"""
            color: {result.outcome_color};
            background: {DARK['bg_elevated']};
            border: 1px solid {result.outcome_color};
            border-radius: 4px;
            padding: 4px 12px;
            font-size: 14px;
            font-weight: 700;
            font-family: '{FONT_MONO_FALLBACK}';
        """)
        title_row.addWidget(total_lbl)

        hdr_layout.addLayout(title_row)

        desc = QLabel(sc.short_description)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 12px;")
        hdr_layout.addWidget(desc)

        layout.addWidget(hdr_card)

        # --- Outcome ---
        outcome_card = QFrame()
        outcome_card.setObjectName("card")
        oc_layout = QVBoxLayout(outcome_card)
        oc_layout.setContentsMargins(16, 12, 16, 12)
        oc_layout.setSpacing(4)

        oc_title = QLabel("WHAT THE USER SEES")
        oc_title.setObjectName("sectionLabel")
        oc_layout.addWidget(oc_title)

        outcome_lbl = QLabel(result.outcome)
        outcome_lbl.setWordWrap(True)
        outcome_lbl.setStyleSheet(
            f"color: {result.outcome_color}; font-size: 13px; font-weight: 600;"
        )
        oc_layout.addWidget(outcome_lbl)

        layout.addWidget(outcome_card)

        # --- Timeline ---
        timeline_card = Card("Stage-by-Stage Timeline")
        legend_row = QHBoxLayout()
        for status, label, color in [
            ("ok",      "Succeeded",  DARK["success"]),
            ("slow",    "Degraded",   DARK["warning"]),
            ("failed",  "Failed",     DARK["error"]),
            ("skipped", "Skipped",    DARK["text_muted"]),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 11px;")
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 11px;")
            legend_row.addWidget(dot)
            legend_row.addWidget(lbl)
            legend_row.addSpacing(12)
        legend_row.addStretch()
        timeline_card.add_widget(self._layout_widget(legend_row))

        timeline = FailureTimeline()
        timeline.set_result(result)
        timeline_card.add_widget(timeline)

        if result.baseline_ms:
            ratio = result.total_ms / result.baseline_ms
            cmp_lbl = QLabel(
                f"Normal load:  {_ms_label(result.baseline_ms)}  ·  "
                f"This scenario:  {_ms_label(result.total_ms)}  ·  "
                f"{ratio:.1f}× slower"
            )
            cmp_lbl.setStyleSheet(
                f"color: {DARK['text_muted']}; font-size: 11px;"
                f" font-family: '{FONT_MONO_FALLBACK}';"
            )
            timeline_card.add_widget(cmp_lbl)

        layout.addWidget(timeline_card)

        # Stage detail table
        detail_card = Card("Stage Details")
        for stage in result.stages:
            self._add_stage_row(detail_card, stage)
        layout.addWidget(detail_card)

        # --- What happened ---
        wh_card = Card("Technical Explanation")
        wh_lbl = QLabel(result.what_happened)
        wh_lbl.setWordWrap(True)
        wh_lbl.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 12px; line-height: 1.5;")
        wh_card.add_widget(wh_lbl)
        layout.addWidget(wh_card)

        # --- Mitigation ---
        mit_card = Card("Real-World Mitigation")
        mit_lbl = QLabel(result.mitigation)
        mit_lbl.setWordWrap(True)
        mit_lbl.setStyleSheet(f"color: {DARK['success']}; font-size: 12px; line-height: 1.5;")
        mit_card.add_widget(mit_lbl)
        layout.addWidget(mit_card)

        layout.addStretch()

    @staticmethod
    def _layout_widget(layout: QHBoxLayout) -> QWidget:
        w = QWidget()
        w.setLayout(layout)
        return w

    def _add_stage_row(self, card: Card, stage: SimulatedStageResult) -> None:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 2, 0, 2)
        rl.setSpacing(10)

        status_icon = {"ok": "✓", "slow": "⚠", "failed": "✕", "skipped": "–"}.get(stage.status, "?")
        icon_lbl = QLabel(status_icon)
        icon_lbl.setFixedWidth(14)
        icon_lbl.setStyleSheet(f"color: {stage.color}; font-size: 13px; font-weight: 700;")
        rl.addWidget(icon_lbl)

        name_lbl = QLabel(stage.stage_name)
        name_color = DARK["text_primary"] if stage.status != "skipped" else DARK["text_muted"]
        name_lbl.setStyleSheet(f"color: {name_color}; font-size: 12px;")
        rl.addWidget(name_lbl, stretch=1)

        time_lbl = QLabel("—" if stage.status == "skipped" else _ms_label(stage.duration_ms))
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        time_lbl.setStyleSheet(
            f"color: {stage.color}; font-size: 12px; font-weight: 600;"
            f" font-family: '{FONT_MONO_FALLBACK}';"
        )
        time_lbl.setFixedWidth(80)
        rl.addWidget(time_lbl)

        card.add_widget(row)

        if stage.detail:
            detail_lbl = QLabel(stage.detail)
            detail_lbl.setWordWrap(True)
            detail_lbl.setStyleSheet(
                f"color: {DARK['text_muted']}; font-size: 11px; margin-left: 24px; padding-bottom: 4px;"
            )
            card.add_widget(detail_lbl)


# ---------------------------------------------------------------------------
# Scenario sidebar button
# ---------------------------------------------------------------------------

class ScenarioButton(QPushButton):
    """One clickable scenario entry in the left panel."""

    def __init__(self, scenario, parent: QWidget | None = None):
        super().__init__(parent)
        self._scenario = scenario
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        icon_lbl = QLabel(scenario.icon)
        icon_lbl.setStyleSheet("font-size: 18px;")
        icon_lbl.setFixedWidth(24)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(scenario.name)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(name_lbl, stretch=1)

        self._refresh_style(False)

    def _refresh_style(self, checked: bool) -> None:
        sc = self._scenario
        if checked:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DARK['bg_elevated']};
                    border: 1px solid {sc.color};
                    border-radius: 6px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: {DARK['bg_elevated']};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid {DARK['border_subtle']};
                    border-radius: 6px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: {DARK['bg_elevated']};
                    border: 1px solid {DARK['border']};
                }}
            """)

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._refresh_style(checked)


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

class FailureSimulationPanel(QWidget):
    """
    Module 18: Failure Simulation Laboratory.

    Left: scrollable list of scenario buttons.
    Right: animated result view for the selected scenario.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._baseline_ms: float = 800.0
        self._buttons: dict[FailureType, ScenarioButton] = {}
        self._current_type: FailureType | None = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Left panel: scenario list ---
        left = QWidget()
        left.setObjectName("sidebar")   # reuse sidebar style (dark bg)
        left.setFixedWidth(220)
        left.setStyleSheet(f"""
            QWidget {{
                background-color: {DARK['bg_panel']};
                border-right: 1px solid {DARK['border']};
            }}
        """)

        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 16, 10, 16)
        left_layout.setSpacing(6)

        lab_title = QLabel("Failure Scenarios")
        lab_title.setStyleSheet(
            f"color: {DARK['text_primary']}; font-size: 14px; font-weight: 700;"
        )
        left_layout.addWidget(lab_title)

        sub = QLabel("Select a scenario to simulate")
        sub.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
        sub.setWordWrap(True)
        left_layout.addWidget(sub)
        left_layout.addSpacing(4)

        for sc in ALL_SCENARIOS:
            btn = ScenarioButton(sc)
            btn.clicked.connect(lambda _, ft=sc.failure_type: self._on_scenario_selected(ft))
            self._buttons[sc.failure_type] = btn
            left_layout.addWidget(btn)

        left_layout.addStretch()
        outer.addWidget(left)

        # --- Right panel: result ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        outer.addWidget(right, stretch=1)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        right_layout.addWidget(self._scroll)

        self._right_content = QWidget()
        self._scroll.setWidget(self._right_content)

        self._right_layout = QVBoxLayout(self._right_content)
        self._right_layout.setContentsMargins(24, 20, 24, 24)
        self._right_layout.setSpacing(0)

        # Default landing
        self._show_landing()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_baseline(self, page_load: PageLoadResult) -> None:
        """
        Called from main_window when a real PageLoadResult arrives so
        failure timelines can be compared against the real page's load time.
        """
        if page_load.total_time_ms > 0:
            self._baseline_ms = page_load.total_time_ms
        # Re-render current scenario with updated baseline
        if self._current_type is not None:
            self._run_scenario(self._current_type)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _show_landing(self) -> None:
        self._clear_right()
        landing = QWidget()
        ll = QVBoxLayout(landing)
        ll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.setSpacing(12)

        icon = QLabel("⚡")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        ll.addWidget(icon)

        title = QLabel("Failure Simulation Laboratory")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {DARK['text_primary']}; font-size: 18px; font-weight: 700;"
        )
        ll.addWidget(title)

        desc = QLabel(
            "Select a failure scenario from the left panel to simulate what happens\n"
            "to a web page load under different network and server failure conditions.\n\n"
            "Each scenario shows the full stage-by-stage timeline, a technical explanation\n"
            "of what caused the failure, and real-world mitigation strategies."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 13px;")
        ll.addWidget(desc)

        note = QLabel("Tip: Explore a URL first to calibrate baseline timings to a real page.")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
        ll.addWidget(note)

        self._right_layout.addWidget(landing, stretch=1)

    def _on_scenario_selected(self, failure_type: FailureType) -> None:
        # Toggle check state
        for ft, btn in self._buttons.items():
            btn.setChecked(ft == failure_type)

        if self._current_type == failure_type:
            # Clicking the same one again re-runs the animation
            pass
        self._current_type = failure_type
        self._run_scenario(failure_type)

    def _run_scenario(self, failure_type: FailureType) -> None:
        result = simulate_failure(failure_type, baseline_ms=self._baseline_ms)
        self._clear_right()
        view = ScenarioResultView(result)
        self._right_layout.addWidget(view)

    def _clear_right(self) -> None:
        while self._right_layout.count():
            item = self._right_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
