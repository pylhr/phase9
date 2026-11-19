"""
UI Layer — Qt stylesheet (QSS) built from design tokens.

Kept as a single generated string so every widget pulls from the same
token system in ui/theme.py rather than hardcoding colors inline.
"""
from __future__ import annotations

from ui.theme import DARK as T, FONT_DISPLAY, FONT_MONO_FALLBACK, RADIUS_MD, RADIUS_SM


def build_stylesheet() -> str:
    return f"""
    * {{
        font-family: '{FONT_DISPLAY}';
        color: {T['text_primary']};
        outline: none;
    }}

    QMainWindow, QWidget#root {{
        background-color: {T['bg_app']};
    }}

    QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{
        background-color: {T['bg_app']};
        border: none;
    }}

    /* ---------- Sidebar ---------- */
    QWidget#sidebar {{
        background-color: {T['bg_panel']};
        border-right: 1px solid {T['border']};
    }}

    QLabel#sidebarBrand {{
        color: {T['text_primary']};
        font-size: 15px;
        font-weight: 600;
        padding: 18px 16px 4px 16px;
    }}

    QLabel#sidebarSubtitle {{
        color: {T['text_muted']};
        font-size: 11px;
        padding: 0px 16px 16px 16px;
    }}

    QListWidget#navList {{
        background: transparent;
        border: none;
        padding: 4px 8px;
    }}

    QListWidget#navList::item {{
        color: {T['text_secondary']};
        padding: 9px 12px;
        border-radius: {RADIUS_SM}px;
        margin-bottom: 2px;
        font-size: 13px;
    }}

    QListWidget#navList::item:selected {{
        background-color: {T['accent_bg']};
        color: {T['accent']};
        font-weight: 600;
    }}

    QListWidget#navList::item:hover:!selected {{
        background-color: {T['bg_elevated']};
        color: {T['text_primary']};
    }}

    /* ---------- Top bar / URL workspace ---------- */
    QWidget#topBar {{
        background-color: {T['bg_panel']};
        border-bottom: 1px solid {T['border']};
    }}

    QLineEdit#urlInput {{
        background-color: {T['bg_input']};
        border: 1px solid {T['border']};
        border-radius: {RADIUS_MD}px;
        padding: 10px 14px;
        font-family: '{FONT_MONO_FALLBACK}';
        font-size: 13px;
        color: {T['text_primary']};
        selection-background-color: {T['accent_dim']};
    }}

    QLineEdit#urlInput:focus {{
        border: 1px solid {T['border_focus']};
    }}

    QPushButton#exploreBtn {{
        background-color: {T['accent']};
        color: {T['bg_app']};
        border: none;
        border-radius: {RADIUS_MD}px;
        padding: 10px 22px;
        font-size: 13px;
        font-weight: 600;
    }}

    QPushButton#exploreBtn:hover {{
        background-color: {T['accent_dim']};
    }}

    QPushButton#exploreBtn:disabled {{
        background-color: {T['bg_elevated']};
        color: {T['text_disabled']};
    }}

    QPushButton#secondaryBtn {{
        background-color: transparent;
        color: {T['text_secondary']};
        border: 1px solid {T['border']};
        border-radius: {RADIUS_MD}px;
        padding: 9px 16px;
        font-size: 12px;
    }}

    QPushButton#secondaryBtn:hover {{
        border: 1px solid {T['text_secondary']};
        color: {T['text_primary']};
    }}

    /* ---------- Status pill ---------- */
    QLabel#statusPending {{
        color: {T['text_muted']};
        font-size: 12px;
    }}
    QLabel#statusRunning {{
        color: {T['accent_blue']};
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#statusComplete {{
        color: {T['success']};
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#statusError {{
        color: {T['error']};
        font-size: 12px;
        font-weight: 600;
    }}

    /* ---------- Cards / panels ---------- */
    QFrame#card {{
        background-color: {T['bg_card']};
        border: 1px solid {T['border_subtle']};
        border-radius: {RADIUS_MD}px;
    }}

    QLabel#cardTitle {{
        color: {T['text_primary']};
        font-size: 13px;
        font-weight: 600;
    }}

    QLabel#cardMeta {{
        color: {T['text_muted']};
        font-size: 11px;
        font-family: '{FONT_MONO_FALLBACK}';
    }}

    QLabel#sectionLabel {{
        color: {T['text_muted']};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 1px;
    }}

    QLabel#placeholderText {{
        color: {T['text_muted']};
        font-size: 13px;
    }}

    /* ---------- Table (DNS records) ---------- */
    QTableWidget {{
        background-color: {T['bg_card']};
        alternate-background-color: {T['bg_elevated']};
        border: 1px solid {T['border_subtle']};
        border-radius: {RADIUS_MD}px;
        gridline-color: {T['border_subtle']};
        font-family: '{FONT_MONO_FALLBACK}';
        font-size: 12px;
        selection-background-color: {T['accent_bg']};
        selection-color: {T['accent']};
    }}

    QHeaderView::section {{
        background-color: {T['bg_panel']};
        color: {T['text_muted']};
        padding: 8px;
        border: none;
        border-bottom: 1px solid {T['border']};
        font-size: 11px;
        font-weight: 600;
        font-family: '{FONT_DISPLAY}';
    }}

    QTableWidget::item {{
        padding: 6px 8px;
        border: none;
    }}

    /* ---------- Scrollbars ---------- */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {T['border']};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {T['text_muted']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
    }}
    QScrollBar::handle:horizontal {{
        background: {T['border']};
        border-radius: 5px;
        min-width: 30px;
    }}

    /* ---------- Splitter ---------- */
    QSplitter::handle {{
        background-color: {T['border']};
    }}

    /* ---------- Tooltip ---------- */
    QToolTip {{
        background-color: {T['bg_elevated']};
        color: {T['text_primary']};
        border: 1px solid {T['border']};
        padding: 6px 8px;
        border-radius: {RADIUS_SM}px;
        font-size: 11px;
    }}
    """
