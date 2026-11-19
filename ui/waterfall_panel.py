"""
UI Layer — Network Waterfall Timeline panel (Module 9).

A Chrome-DevTools-style waterfall: one row per resource, with a horizontal
bar showing when it started and how long it took, all on a shared timeline.
Built as a custom-painted widget since no stock Qt widget gives this
overlapping-bars-on-a-shared-axis layout.
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from data.models import PageLoadResult
from ui.theme import DARK, FONT_MONO_FALLBACK, resource_color
from ui.widgets import Card, EmptyState

ROW_HEIGHT = 26
LABEL_WIDTH = 280
RULER_HEIGHT = 24
MIN_BAR_WIDTH = 3


def _short_name(url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path
    name = path.rsplit("/", 1)[-1] or path or url

    # Some paths (redirect proxies, encoded tracking URLs) share a long
    # common prefix — truncating only from the end makes different
    # resources display as identical text. Keep a head and tail fragment
    # instead so distinct resources stay visually distinguishable.
    max_len = 38
    if len(name) > max_len:
        head_len = 20
        tail_len = max_len - head_len - 1  # reserve 1 char for the ellipsis
        name = f"{name[:head_len]}…{name[-tail_len:]}"

    return name


def _full_label(url: str) -> str:
    """Used for tooltips — the full URL, not the chart's shortened label."""
    return url


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


class WaterfallChart(QWidget):
    """Custom-painted waterfall: ruler + one bar per resource."""

    def __init__(self, result: PageLoadResult, parent: QWidget | None = None):
        super().__init__(parent)
        # Only chart resources we actually timed (skip ones merely discovered
        # but not sampled) — an untimed 0ms bar would misrepresent them as
        # instantaneous rather than honestly "not measured".
        self._resources = [r for r in result.resources if r.timing.total_ms > 0 or r.error]
        self._max_time = max(
            (r.start_offset_ms + r.timing.total_ms for r in self._resources),
            default=1.0,
        )
        self._max_time = max(self._max_time, 1.0)

        row_count = len(self._resources)
        self.setMinimumHeight(RULER_HEIGHT + row_count * ROW_HEIGHT + 8)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def _chart_x(self, width: int, time_ms: float) -> float:
        chart_width = width - LABEL_WIDTH - 16
        return LABEL_WIDTH + (time_ms / self._max_time) * chart_width

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        y = event.position().y()
        if y < RULER_HEIGHT:
            self.setToolTip("")
            return
        row = int((y - RULER_HEIGHT) // ROW_HEIGHT)
        if 0 <= row < len(self._resources):
            self.setToolTip(self._resources[row].url)
        else:
            self.setToolTip("")

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        chart_right = width - 8

        # --- Ruler ---
        font = QFont(FONT_MONO_FALLBACK, 9)
        painter.setFont(font)

        step_count = 5
        prev_label_right = -1.0  # tracks the right edge of the last-drawn label, to avoid overlap
        for i in range(step_count + 1):
            t = (self._max_time / step_count) * i
            x = self._chart_x(width, t)
            painter.setPen(QPen(QColor(DARK["border_subtle"])))
            painter.drawLine(int(x), RULER_HEIGHT, int(x), self.height())
            painter.setPen(QPen(QColor(DARK["text_muted"])))

            label = f"{t:.0f}ms"
            label_width = painter.fontMetrics().horizontalAdvance(label)

            # Default: left-aligned from the tick, 3px gap.
            label_left = x + 3
            # The last tick sits at the chart's right edge — left-aligning
            # its label from that point would overflow past the widget
            # boundary, so right-align it against the edge instead.
            if i == step_count:
                label_left = x - label_width
            # If this label would overlap the previous one (common at
            # narrow widths, where ticks sit close together), push it right
            # just enough to clear it, so adjacent labels never merge into
            # unreadable text.
            if label_left < prev_label_right + 4:
                label_left = prev_label_right + 4

            painter.drawText(int(label_left), 15, label)
            prev_label_right = label_left + label_width

        # Baseline under ruler
        painter.setPen(QPen(QColor(DARK["border"])))
        painter.drawLine(0, RULER_HEIGHT, chart_right, RULER_HEIGHT)

        # --- Rows ---
        label_font = QFont(FONT_MONO_FALLBACK, 9)
        painter.setFont(label_font)

        for i, resource in enumerate(self._resources):
            y = RULER_HEIGHT + i * ROW_HEIGHT
            row_mid = y + ROW_HEIGHT / 2

            # Alternating row background for scannability
            if i % 2 == 1:
                painter.fillRect(QRectF(0, y, width, ROW_HEIGHT), QColor(DARK["bg_elevated"]))

            # Label (resource name)
            painter.setPen(QPen(QColor(DARK["text_secondary"])))
            label = _short_name(resource.url)
            painter.drawText(8, int(row_mid) + 4, label)

            # Bar
            start_x = self._chart_x(width, resource.start_offset_ms)
            end_x = self._chart_x(width, resource.start_offset_ms + resource.timing.total_ms)
            bar_width = max(end_x - start_x, MIN_BAR_WIDTH)

            color = QColor("#F2607A") if resource.error else QColor(resource_color(resource.resource_type))
            bar_height = 12
            bar_y = row_mid - bar_height / 2

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(start_x, bar_y, bar_width, bar_height), 2, 2)

            # Duration label: after the bar if there's room, before it if
            # there's room there instead, and inside the bar (in a
            # contrasting color) as a last resort for bars wide enough to
            # span most of the chart — this avoids the label landing in a
            # disconnected, ambiguous position for long-running resources.
            dur_text = f"{resource.timing.total_ms:.0f}ms" if not resource.error else "error"
            text_width = painter.fontMetrics().horizontalAdvance(dur_text)

            after_x = end_x + 6
            before_x = start_x - 6 - text_width

            if after_x + text_width <= chart_right:
                painter.setPen(QPen(QColor(DARK["text_muted"])))
                painter.drawText(int(after_x), int(row_mid) + 4, dur_text)
            elif before_x >= LABEL_WIDTH + 4:
                painter.setPen(QPen(QColor(DARK["text_muted"])))
                painter.drawText(int(before_x), int(row_mid) + 4, dur_text)
            else:
                # Bar is wide enough to cover both fallback positions —
                # draw the label inside it, right-aligned, in a color that
                # reads against the bar's own fill.
                inside_x = end_x - 6 - text_width
                painter.setPen(QPen(QColor(DARK["bg_app"])))
                painter.drawText(int(max(inside_x, start_x + 4)), int(row_mid) + 4, dur_text)


class WaterfallLegend(QWidget):
    """Small color-key row for the resource type colors used in the chart."""

    def __init__(self, type_counts: dict[str, int], parent: QWidget | None = None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        order = ["html", "css", "javascript", "image", "font", "other"]
        for rtype in order:
            count = type_counts.get(rtype)
            if not count:
                continue
            item = QWidget()
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(6)

            swatch = QLabel()
            swatch.setFixedSize(10, 10)
            swatch.setStyleSheet(
                f"background-color: {resource_color(rtype)}; border-radius: 2px;"
            )
            item_layout.addWidget(swatch)

            text = QLabel(f"{rtype.upper()} ({count})")
            text.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 11px;")
            item_layout.addWidget(text)

            layout.addWidget(item)

        layout.addStretch()


class WaterfallPanel(QWidget):
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
            "Enter a URL above and click Explore to see a real network waterfall.\n"
            "Every bar reflects an actual measured fetch — DNS, TLS, and HTTP timings, "
            "plus the page's real CSS, JS, image, and font requests."
        )
        self._layout.addWidget(self._empty_state)

        self._widgets: list[QWidget] = []

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, url: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        loading = EmptyState(
            f"Loading {url} and fetching its real CSS, JS, image, and font resources…\n"
            "This can take a few seconds since it's a real concurrent network fetch."
        )
        self._layout.insertWidget(0, loading)
        self._widgets.append(loading)

    def show_result(self, result: PageLoadResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if result.error:
            self.show_error(result.error)
            return

        timed = [r for r in result.resources if r.timing.total_ms > 0 or r.error]

        if not timed:
            empty = Card("Network Waterfall")
            empty.add_widget(QLabel("No resources were fetched with timing data for this page."))
            self._layout.insertWidget(0, empty)
            self._widgets.append(empty)
            return

        summary_card = Card("Network Waterfall")

        summary_label = QLabel(
            f"<b>{len(timed)}</b> resources timed &nbsp;|&nbsp; "
            f"<b>{result.total_time_ms:.0f} ms</b> total page load &nbsp;|&nbsp; "
            f"<b>{_format_bytes(result.total_bytes)}</b> transferred"
        )
        summary_label.setObjectName("cardMeta")
        summary_card.add_widget(summary_label)

        summary_card.add_widget(WaterfallLegend(result.type_counts()))

        chart = WaterfallChart(result)
        summary_card.add_widget(chart)

        note = QLabel(
            "Resource bars show real measured fetch time (a single combined span — "
            "this app doesn't currently break each resource fetch into its own "
            "DNS/connect/TLS sub-phases the way the dedicated TLS module does for the main page)."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {DARK['text_muted']}; font-size: 11px;")
        summary_card.add_widget(note)

        self._layout.insertWidget(0, summary_card)
        self._widgets.append(summary_card)

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("Could Not Load Page")
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
