"""
Service Layer — URL parsing/validation helper.

Keeps URL normalization logic out of the UI widgets so later modules
(HTTP, TLS, etc.) can reuse the exact same parsing rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class ParsedURL:
    original: str
    scheme: str
    hostname: str
    port: int
    path: str

    @property
    def is_https(self) -> bool:
        return self.scheme == "https"


class InvalidURLError(ValueError):
    pass


def parse_url(raw: str) -> ParsedURL:
    """
    Normalize user input into a ParsedURL.

    Accepts input with or without a scheme ("github.com" or "https://github.com")
    and defaults to https when no scheme is given, since that's the overwhelmingly
    common case for the sites this tool is meant to explore.
    """
    raw = raw.strip()
    if not raw:
        raise InvalidURLError("Please enter a URL.")

    if "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlparse(raw)

    if not parsed.hostname:
        raise InvalidURLError(f"Couldn't parse a hostname from '{raw}'.")

    if parsed.scheme not in ("http", "https"):
        raise InvalidURLError(f"Unsupported scheme '{parsed.scheme}'. Use http or https.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    return ParsedURL(
        original=raw,
        scheme=parsed.scheme,
        hostname=parsed.hostname,
        port=port,
        path=parsed.path or "/",
    )
