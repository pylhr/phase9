"""
UI Layer — Session Recording & Replay panel (Module 17 equivalent).

Lets the user save the current exploration session to disk, browse past
sessions, and replay any saved one — restoring all module panels to the
exact state they were in after the original Explore, without any new network
calls. Saved sessions are stored as human-readable JSON files.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data.models import ExplorationSession
from protocols.storage_protocol import delete_session, list_sessions, load_session, save_session
from ui.theme import DARK
from ui.widgets import Card, EmptyState


class SessionRow(QWidget):
    """One row in the sessions list — URL, date, load/delete buttons."""

    load_requested = pyqtSignal(str)    # emits path string
    delete_requested = pyqtSignal(str)  # emits path string

    def __init__(self, path: Path, url: str, started_at: datetime,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._path = str(path)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)

        info = QWidget()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        url_label = QLabel(url)
        url_label.setStyleSheet(
            f"color: {DARK['text_primary']}; font-size: 13px; font-weight: 600;"
        )
        info_layout.addWidget(url_label)

        ts = started_at.strftime("%Y-%m-%d %H:%M")
        meta = QLabel(f"Saved {ts}  •  {path.name}")
        meta.setObjectName("cardMeta")
        info_layout.addWidget(meta)

        layout.addWidget(info, stretch=1)

        load_btn = QPushButton("Load")
        load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        load_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {DARK['accent_bg']};
                color: {DARK['accent']};
                border: 1px solid {DARK['accent_dim']};
                border-radius: 5px;
                padding: 5px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {DARK['accent_dim']};
            }}
        """)
        load_btn.clicked.connect(lambda: self.load_requested.emit(self._path))
        layout.addWidget(load_btn)

        del_btn = QPushButton("Delete")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DARK['text_muted']};
                border: 1px solid {DARK['border']};
                border-radius: 5px;
                padding: 5px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {DARK['error']};
                border-color: {DARK['error']};
            }}
        """)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._path))
        layout.addWidget(del_btn)


class SessionRecordingPanel(QWidget):
    """
    The Session Recording & Replay panel.

    Signals:
        replay_requested(ExplorationSession) — emitted when the user clicks
            Load on a saved session; the main window connects to this to
            replay the session across all module panels.
    """

    replay_requested = pyqtSignal(object)  # ExplorationSession

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

        # --- Save current session card (always visible) ---
        self._save_card = Card("Save Current Session")

        save_desc = QLabel(
            "After exploring a URL, save the full session to disk — every module's "
            "results, captured packets, rendering model, and more. Saved sessions can "
            "be replayed instantly without any network calls."
        )
        save_desc.setWordWrap(True)
        save_desc.setObjectName("cardMeta")
        self._save_card.add_widget(save_desc)

        self._save_btn = QPushButton("Save Current Session")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setEnabled(False)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {DARK['accent']};
                color: {DARK['bg_app']};
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 700;
            }}
            QPushButton:hover:enabled {{
                background-color: {DARK['accent']};
            }}
            QPushButton:disabled {{
                background-color: {DARK['bg_elevated']};
                color: {DARK['text_muted']};
            }}
        """)
        self._save_btn.clicked.connect(self._on_save)
        self._save_card.add_widget(self._save_btn)

        self._save_status = QLabel("")
        self._save_status.setObjectName("cardMeta")
        self._save_card.add_widget(self._save_status)

        self._layout.addWidget(self._save_card)

        # --- Sessions list ---
        self._sessions_card = Card("Saved Sessions")
        self._layout.addWidget(self._sessions_card)

        self._session_rows_widget = QWidget()
        self._session_rows_layout = QVBoxLayout(self._session_rows_widget)
        self._session_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._session_rows_layout.setSpacing(4)
        self._sessions_card.add_widget(self._session_rows_widget)

        self._layout.addStretch()

        self._current_session: ExplorationSession | None = None
        self._refresh_sessions_list()

    # ------------------------------------------------------------------
    # Public API called from main_window
    # ------------------------------------------------------------------

    def set_current_session(self, session: ExplorationSession | None) -> None:
        self._current_session = session
        # Allow saving both successful and partially-failed sessions — even a
        # session where one job failed (e.g., TCP capture timing race) has
        # all the other modules' data and is worth keeping.
        has_session = (session is not None and
                       session.status.value in ("complete", "failed"))
        self._save_btn.setEnabled(has_session)
        if has_session:
            status_note = "" if session.status.value == "complete" else " (some modules failed)"
            self._save_status.setText(f"Ready to save session for {session.url}{status_note}")
        else:
            self._save_status.setText("")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        if self._current_session is None:
            return
        try:
            path = save_session(self._current_session)
            self._save_status.setText(f"Saved to {path.name}")
            self._save_status.setStyleSheet(f"color: {DARK['success']}; font-size: 12px;")
            self._refresh_sessions_list()
        except Exception as exc:  # noqa: BLE001
            self._save_status.setText(f"Error saving: {exc}")
            self._save_status.setStyleSheet(f"color: {DARK['error']}; font-size: 12px;")

    def _refresh_sessions_list(self) -> None:
        # Clear existing rows
        while self._session_rows_layout.count():
            item = self._session_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sessions = list_sessions()
        if not sessions:
            empty = QLabel("No saved sessions yet. Complete an exploration above and click Save.")
            empty.setObjectName("cardMeta")
            empty.setWordWrap(True)
            self._session_rows_layout.addWidget(empty)
            return

        for path, url, started_at in sessions:
            row = SessionRow(path, url, started_at)
            row.load_requested.connect(self._on_load)
            row.delete_requested.connect(self._on_delete)

            # Separator line between rows
            sep = QWidget()
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"background-color: {DARK['border']};")

            self._session_rows_layout.addWidget(row)
            self._session_rows_layout.addWidget(sep)

    def _on_load(self, path_str: str) -> None:
        try:
            session = load_session(Path(path_str))
            self.replay_requested.emit(session)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self, "Could Not Load Session",
                f"Failed to load {Path(path_str).name}:\n\n{exc}"
            )

    def _on_delete(self, path_str: str) -> None:
        path = Path(path_str)
        reply = QMessageBox.question(
            self, "Delete Session",
            f"Delete session file {path.name}?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_session(path)
            self._refresh_sessions_list()
