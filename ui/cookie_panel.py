"""
UI Layer — Cookie Explorer panel (Module 12).

Shows real cookies parsed from the response's Set-Cookie headers: name,
value, expiration, domain, path, Secure/HttpOnly flags, SameSite, plus a
plain-language explanation of what each cookie's attributes mean.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from data.models import CookieRecord, HTTPExchangeResult
from protocols.cookie_protocol import parse_cookies
from ui.theme import DARK
from ui.widgets import Card, EmptyState


def _flag_pill(label: str, active: bool) -> QLabel:
    color = DARK["success"] if active else DARK["text_muted"]
    bg = DARK["accent_bg"] if active else DARK["bg_elevated"]
    pill = QLabel(label)
    pill.setStyleSheet(f"""
        color: {color};
        background-color: {bg};
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 10px;
        font-weight: 600;
    """)
    return pill


def _explain_cookie(cookie: CookieRecord) -> str:
    """A plain-language summary of what this cookie's attributes mean in practice."""
    parts = []

    if cookie.is_session_cookie:
        parts.append("This is a session cookie — it has no Expires or Max-Age, so it's "
                      "deleted automatically when the browser closes.")
    else:
        parts.append("This is a persistent cookie — it stays on disk until it expires "
                      "or the user/site clears it.")

    if cookie.secure and cookie.http_only:
        parts.append("Secure + HttpOnly means it's only sent over HTTPS and is invisible "
                      "to page JavaScript, which protects it from network eavesdropping "
                      "and most XSS-based theft.")
    elif cookie.secure:
        parts.append("Secure means it's only sent over HTTPS, but it lacks HttpOnly, so "
                      "page JavaScript can still read it — a risk if the site has an XSS bug.")
    elif cookie.http_only:
        parts.append("HttpOnly protects it from JavaScript access, but without Secure it "
                      "could still be sent over an unencrypted HTTP connection.")
    else:
        parts.append("Without Secure or HttpOnly, this cookie can be read by page "
                      "JavaScript and sent over unencrypted connections — typically only "
                      "appropriate for non-sensitive values.")

    if cookie.same_site:
        same_site_lower = cookie.same_site.lower()
        if same_site_lower == "strict":
            parts.append("SameSite=Strict blocks it from being sent on any cross-site "
                          "request, the strongest CSRF protection.")
        elif same_site_lower == "lax":
            parts.append("SameSite=Lax allows it on top-level navigations from other sites "
                          "(like clicking a link) but blocks it on cross-site subrequests.")
        elif same_site_lower == "none":
            parts.append("SameSite=None allows it on all cross-site requests — intentional "
                          "for things like embedded widgets, but it requires Secure.")

    return " ".join(parts)


class CookieRow(Card):
    def __init__(self, cookie: CookieRecord, parent: QWidget | None = None):
        super().__init__("", parent)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        name_label = QLabel(cookie.name)
        name_label.setStyleSheet(f"color: {DARK['text_primary']}; font-size: 13px; font-weight: 700;")
        header_layout.addWidget(name_label)

        header_layout.addWidget(_flag_pill("SECURE", cookie.secure))
        header_layout.addWidget(_flag_pill("HTTPONLY", cookie.http_only))
        if cookie.same_site:
            header_layout.addWidget(_flag_pill(f"SAMESITE={cookie.same_site.upper()}", True))
        header_layout.addStretch()

        self.add_widget(header)

        value_display = cookie.value if len(cookie.value) <= 60 else cookie.value[:57] + "…"
        value_label = QLabel(f"Value: <code>{value_display}</code>")
        value_label.setObjectName("cardMeta")
        value_label.setWordWrap(True)
        self.add_widget(value_label)

        meta_parts = []
        if cookie.domain:
            meta_parts.append(f"Domain: {cookie.domain}")
        if cookie.path:
            meta_parts.append(f"Path: {cookie.path}")
        if cookie.expires:
            meta_parts.append(f"Expires: {cookie.expires.strftime('%Y-%m-%d %H:%M UTC')}")
        elif cookie.max_age is not None:
            days = cookie.max_age // 86400
            meta_parts.append(f"Max-Age: {cookie.max_age}s (~{days}d)")
        else:
            meta_parts.append("Expires: when browser closes (session cookie)")

        meta_label = QLabel("  •  ".join(meta_parts))
        meta_label.setObjectName("cardMeta")
        meta_label.setWordWrap(True)
        self.add_widget(meta_label)

        explanation = QLabel(_explain_cookie(cookie))
        explanation.setWordWrap(True)
        explanation.setStyleSheet(f"color: {DARK['text_secondary']}; font-size: 12px; margin-top: 4px;")
        self.add_widget(explanation)


class CookieExplorerPanel(QWidget):
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
        self._layout.setSpacing(12)

        self._empty_state = EmptyState(
            "Enter a URL above and click Explore to see real cookies this site sets.\n"
            "Each cookie's Secure, HttpOnly, and SameSite attributes are explained in plain language."
        )
        self._layout.addWidget(self._empty_state)

        self._widgets: list[QWidget] = []

    def clear(self) -> None:
        self._teardown()
        self._empty_state.setVisible(True)

    def show_loading(self, url: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)
        loading = EmptyState(f"Waiting for the response from {url} to inspect its cookies…")
        self._layout.insertWidget(0, loading)
        self._widgets.append(loading)

    def show_exchange(self, exchange: HTTPExchangeResult) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        if exchange.error or exchange.response is None:
            self.show_error(exchange.error or "No response was received.")
            return

        cookies = parse_cookies(exchange.response.raw_set_cookie_headers)

        if not cookies:
            empty = Card("No Cookies")
            empty.add_widget(QLabel(
                "This response didn't set any cookies (no Set-Cookie headers). "
                "Some sites only set cookies after login or other interactions, which "
                "this app doesn't simulate."
            ))
            self._layout.insertWidget(0, empty)
            self._widgets.append(empty)
            return

        summary = QLabel(
            f"<b>{len(cookies)}</b> cookie{'s' if len(cookies) != 1 else ''} set by this response."
        )
        summary.setObjectName("cardMeta")
        self._layout.insertWidget(0, summary)
        self._widgets.append(summary)

        for i, cookie in enumerate(cookies):
            row = CookieRow(cookie)
            self._layout.insertWidget(1 + i, row)
            self._widgets.append(row)

    def show_error(self, message: str) -> None:
        self._teardown()
        self._empty_state.setVisible(False)

        card = Card("Could Not Inspect Cookies")
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
