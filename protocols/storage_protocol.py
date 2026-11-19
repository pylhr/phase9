"""
Protocol Layer — Session serialization and storage.

Saves and loads complete ExplorationSession objects as JSON files so any
exploration can be replayed from disk without re-fetching anything.

Design choices:
  - Pure stdlib (json, dataclasses, datetime) — no new dependencies.
  - Schema version in every file so future changes can detect/migrate old
    sessions rather than silently corrupting them.
  - Recursive dataclass->dict encoder that handles datetime (ISO 8601),
    str-valued Enums (SessionStatus, DataSource), None, list, and all
    nested dataclasses. The decoder mirrors this exactly.
  - Sessions are stored in a per-user directory:
      Windows: %APPDATA%/TheInternetExplorer/sessions/
      macOS/Linux: ~/.local/share/TheInternetExplorer/sessions/
"""
from __future__ import annotations

import dataclasses
import json
import os
import platform
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from data.models import (
    CapturedPacket,
    CDNResult,
    CDNSignal,
    CertificateInfo,
    CookieRecord,
    DataSource,
    DNSRecord,
    DNSResult,
    DOMMetrics,
    ExplorationSession,
    GeoLocation,
    HTTPExchangeResult,
    HTTPRequestRecord,
    HTTPResponseRecord,
    JSExecutionResult,
    PacketCaptureResult,
    PageLoadResult,
    PageResource,
    PrivilegeStatus,
    RenderingPipelineResult,
    RenderStage,
    ResourceTiming,
    RouteHop,
    RouteResult,
    ScriptExecutionEntry,
    SecurityCheck,
    SecurityReport,
    SessionStatus,
    TCPHandshakeResult,
    TCPHandshakeStep,
    TLSResult,
)

SCHEMA_VERSION = 7  # increment when the session schema changes incompatibly

# Type registry for deserialization — maps the stored __type__ tag back to
# the Python dataclass so from_dict() knows which class to reconstruct.
_TYPE_REGISTRY: dict[str, type] = {
    "ExplorationSession": ExplorationSession,
    "DNSResult": DNSResult,
    "DNSRecord": DNSRecord,
    "TLSResult": TLSResult,
    "CertificateInfo": CertificateInfo,
    "HTTPExchangeResult": HTTPExchangeResult,
    "HTTPRequestRecord": HTTPRequestRecord,
    "HTTPResponseRecord": HTTPResponseRecord,
    "PageLoadResult": PageLoadResult,
    "PageResource": PageResource,
    "ResourceTiming": ResourceTiming,
    "DOMMetrics": DOMMetrics,
    "RouteResult": RouteResult,
    "RouteHop": RouteHop,
    "PacketCaptureResult": PacketCaptureResult,
    "CapturedPacket": CapturedPacket,
    "TCPHandshakeResult": TCPHandshakeResult,
    "TCPHandshakeStep": TCPHandshakeStep,
    "CDNResult": CDNResult,
    "CDNSignal": CDNSignal,
    "GeoLocation": GeoLocation,
    "RenderingPipelineResult": RenderingPipelineResult,
    "RenderStage": RenderStage,
    "JSExecutionResult": JSExecutionResult,
    "ScriptExecutionEntry": ScriptExecutionEntry,
    "SecurityCheck": SecurityCheck,
    "SecurityReport": SecurityReport,
    "CookieRecord": CookieRecord,
}

# Fields that hold typed lists — needed by from_dict() to know what class
# to use when deserializing list elements.
_LIST_FIELD_TYPES: dict[str, type] = {
    "records": DNSRecord,
    "hops": RouteHop,
    "packets": CapturedPacket,
    "steps": TCPHandshakeStep,
    "signals": CDNSignal,
    "stages": RenderStage,
    "scripts": ScriptExecutionEntry,
    "resources": PageResource,
    "checks": SecurityCheck,
    "cert_chain": CertificateInfo,
    "flags": str,
    "raw_set_cookie_headers": str,
}


# ── Encoding ────────────────────────────────────────────────────────────────

def _to_dict(obj: Any) -> Any:
    """Recursively convert a dataclass (or primitive) to a JSON-serializable dict."""
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float, str)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if dataclasses.is_dataclass(obj):
        result: dict[str, Any] = {"__type__": type(obj).__name__}
        for field in dataclasses.fields(obj):
            result[field.name] = _to_dict(getattr(obj, field.name))
        return result
    # Fallback for anything unexpected — store as string
    return str(obj)


def _from_dict(data: Any, hint_type: type | None = None) -> Any:
    """Reconstruct a dataclass from a dict produced by _to_dict()."""
    if data is None:
        return None
    if isinstance(data, (bool, int, float)):
        return data
    if isinstance(data, str):
        if hint_type is not None:
            # Reconstruct an Enum from its stored string value
            if hint_type is DataSource:
                return DataSource(data)
            if hint_type is SessionStatus:
                return SessionStatus(data)
            if hint_type is datetime:
                return datetime.fromisoformat(data)
        return data
    if isinstance(data, list):
        elem_type = _LIST_FIELD_TYPES.get(
            "_current_field", None
        ) if hint_type is None else hint_type
        return [_from_dict(item, elem_type) for item in data]
    if isinstance(data, dict):
        type_tag = data.get("__type__")
        if type_tag and type_tag in _TYPE_REGISTRY:
            return _reconstruct(data, _TYPE_REGISTRY[type_tag])
        # Plain dict (e.g. headers)
        return {k: _from_dict(v) for k, v in data.items() if k != "__type__"}
    return data


def _reconstruct(data: dict, cls: type) -> Any:
    """Build a dataclass instance from its dict representation."""
    field_map = {f.name: f for f in dataclasses.fields(cls)}
    kwargs: dict[str, Any] = {}

    for key, value in data.items():
        if key == "__type__":
            continue
        field = field_map.get(key)
        if field is None:
            continue

        type_str = str(field.type)

        # Resolve special scalar types
        if "datetime" in type_str:
            kwargs[key] = datetime.fromisoformat(value) if isinstance(value, str) else value
        elif "DataSource" in type_str:
            kwargs[key] = DataSource(value) if isinstance(value, str) else value
        elif "SessionStatus" in type_str:
            kwargs[key] = SessionStatus(value) if isinstance(value, str) else value
        elif isinstance(value, list):
            # Use the field-name registry to reconstruct typed list elements
            elem_cls = _LIST_FIELD_TYPES.get(key, str)
            if elem_cls is str:
                kwargs[key] = value
            else:
                kwargs[key] = [
                    _reconstruct(item, elem_cls) if isinstance(item, dict) and "__type__" not in item
                    else _from_dict(item)
                    for item in value
                ]
        elif isinstance(value, dict) and "__type__" in value:
            kwargs[key] = _from_dict(value)
        elif isinstance(value, dict):
            # Could be a nested dataclass without a __type__ tag — check by
            # matching field type against the registry (e.g. DOMMetrics, ResourceTiming)
            matched = None
            for name, reg_cls in _TYPE_REGISTRY.items():
                if name in type_str:
                    matched = reg_cls
                    break
            if matched:
                kwargs[key] = _reconstruct(value, matched)
            else:
                kwargs[key] = value  # plain dict (e.g. headers)
        else:
            kwargs[key] = value

    # Fill in missing fields with their defaults to handle old/partial sessions
    for fname, field in field_map.items():
        if fname not in kwargs:
            if field.default is not dataclasses.MISSING:
                kwargs[fname] = field.default
            elif field.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                kwargs[fname] = field.default_factory()

    return cls(**kwargs)


# ── Storage paths ────────────────────────────────────────────────────────────

def sessions_dir() -> Path:
    """Platform-appropriate directory for saved sessions."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    directory = base / "TheInternetExplorer" / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _session_filename(session: ExplorationSession) -> str:
    """A readable filename that encodes the URL and timestamp."""
    # Sanitize the URL into a filesystem-safe slug
    safe_url = re.sub(r"[^\w\-.]", "_", session.url)[:60]
    ts = session.started_at.strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{safe_url}.json"


# ── Public API ────────────────────────────────────────────────────────────────

def save_session(session: ExplorationSession) -> Path:
    """
    Serialize `session` to a JSON file in the sessions directory.
    Returns the path of the saved file.
    """
    payload = {
        "schema_version": SCHEMA_VERSION,
        "session": _to_dict(session),
    }
    path = sessions_dir() / _session_filename(session)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def load_session(path: Path | str) -> ExplorationSession:
    """
    Load a previously saved session from `path`.
    Raises ValueError for incompatible schema versions; OSError for missing files.
    """
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    version = payload.get("schema_version", 0)
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"This session was saved with a newer version of The Internet Explorer "
            f"(schema v{version}, this app supports up to v{SCHEMA_VERSION}). "
            f"Please update the app to open it."
        )

    session_data = payload.get("session")
    if not session_data:
        raise ValueError("Invalid session file: missing 'session' key.")

    return _reconstruct(session_data, ExplorationSession)


def list_sessions() -> list[tuple[Path, str, datetime]]:
    """
    Return (path, url, started_at) for every valid session file in the
    sessions directory, sorted newest-first.
    """
    results = []
    for path in sessions_dir().glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            sess = payload.get("session", {})
            url = sess.get("url", "?")
            started_raw = sess.get("started_at", "")
            started_at = datetime.fromisoformat(started_raw) if started_raw else datetime.min
            results.append((path, url, started_at))
        except Exception:  # noqa: BLE001 - skip corrupt/unreadable files
            continue
    return sorted(results, key=lambda t: t[2], reverse=True)


def delete_session(path: Path | str) -> None:
    """Delete a saved session file."""
    Path(path).unlink(missing_ok=True)
