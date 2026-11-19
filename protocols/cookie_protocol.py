"""
Protocol Layer — Cookie parsing.

Parses real Set-Cookie headers (already captured separately by the HTTP
protocol layer, one string per header, to avoid the comma-join corruption
that affects naive header-dict flattening) into structured CookieRecord
objects using Python's stdlib http.cookies parser.

This module makes no network calls of its own — it's pure parsing of data
the HTTP job already fetched, run synchronously on whichever thread calls it.
"""
from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie

from data.models import CookieRecord


def _parse_expires(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


def parse_cookies(raw_set_cookie_headers: list[str]) -> list[CookieRecord]:
    """
    Parse a list of raw Set-Cookie header strings (one per header, NOT
    comma-joined) into CookieRecord objects.
    """
    records: list[CookieRecord] = []

    for raw_header in raw_set_cookie_headers:
        parser = SimpleCookie()
        try:
            parser.load(raw_header)
        except Exception:  # noqa: BLE001 - a malformed cookie shouldn't crash the whole parse
            continue

        for name, morsel in parser.items():
            expires_raw = morsel["expires"]
            max_age_raw = morsel["max-age"]

            max_age: int | None = None
            if max_age_raw:
                try:
                    max_age = int(max_age_raw)
                except ValueError:
                    max_age = None

            records.append(CookieRecord(
                name=name,
                value=morsel.value,
                domain=morsel["domain"] or None,
                path=morsel["path"] or None,
                expires=_parse_expires(expires_raw),
                max_age=max_age,
                secure=bool(morsel["secure"]),
                http_only=bool(morsel["httponly"]),
                same_site=morsel["samesite"] or None,
                raw_header=raw_header,
            ))

    return records
