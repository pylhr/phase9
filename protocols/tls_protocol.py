"""
Protocol Layer — TLS handshake inspection.

Performs a real TLS handshake against the target host using Python's
built-in `ssl` module over a raw socket, then reads back the negotiated
version, cipher suite, and the server's certificate (and, where the
platform exposes it, the full chain). No Qt or UI dependencies here —
the service layer runs this off the UI thread.
"""
from __future__ import annotations

import socket
import ssl
import time
from datetime import datetime
from typing import Optional

from data.models import CertificateInfo, TLSResult

_CERT_DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"


def _parse_cert_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, _CERT_DATE_FORMAT)
    except ValueError:
        return None


def _name_to_str(name_tuples) -> str:
    """Flatten an ssl-module subject/issuer tuple-of-tuples into 'CN=..., O=...' form."""
    if not name_tuples:
        return "Unknown"
    parts = []
    for rdn in name_tuples:
        for key, value in rdn:
            parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else "Unknown"


def _build_certificate_info(cert_dict: dict) -> CertificateInfo:
    not_before = _parse_cert_date(cert_dict.get("notBefore"))
    not_after = _parse_cert_date(cert_dict.get("notAfter"))

    is_expired = False
    days_until_expiry: Optional[int] = None
    if not_after:
        delta = not_after - datetime.utcnow()
        days_until_expiry = delta.days
        is_expired = delta.total_seconds() < 0

    return CertificateInfo(
        subject=_name_to_str(cert_dict.get("subject")),
        issuer=_name_to_str(cert_dict.get("issuer")),
        not_before=not_before,
        not_after=not_after,
        serial_number=cert_dict.get("serialNumber"),
        is_expired=is_expired,
        days_until_expiry=days_until_expiry,
    )


def inspect_tls(hostname: str, port: int = 443, timeout: float = 8.0) -> TLSResult:
    """
    Perform a real TLS handshake against hostname:port and report what was
    negotiated, plus the server's leaf certificate.

    Uses the platform's default trust store (same as most CLI tools), so an
    untrusted/self-signed cert will raise — that failure is itself useful
    information and is reported back as TLSResult.error rather than crashing.
    """
    context = ssl.create_default_context()

    start = time.perf_counter()
    try:
        with socket.create_connection((hostname, port), timeout=timeout) as raw_sock:
            with context.wrap_socket(raw_sock, server_hostname=hostname) as tls_sock:
                elapsed_ms = (time.perf_counter() - start) * 1000

                version = tls_sock.version() or "Unknown"
                cipher = tls_sock.cipher()  # (name, protocol_version, secret_bits) or None
                cipher_name = cipher[0] if cipher else "Unknown"
                cipher_bits = cipher[2] if cipher else None

                cert_dict = tls_sock.getpeercert()
                chain: list[CertificateInfo] = []
                if cert_dict:
                    chain.append(_build_certificate_info(cert_dict))

                return TLSResult(
                    hostname=hostname,
                    tls_version=version,
                    cipher_suite=cipher_name,
                    cipher_bits=cipher_bits,
                    certificate_chain=chain,
                    handshake_time_ms=elapsed_ms,
                )

    except ssl.SSLCertVerificationError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return TLSResult(
            hostname=hostname,
            handshake_time_ms=elapsed_ms,
            error=f"Certificate verification failed: {exc.verify_message or exc}",
        )
    except (socket.timeout, TimeoutError):
        elapsed_ms = (time.perf_counter() - start) * 1000
        return TLSResult(
            hostname=hostname,
            handshake_time_ms=elapsed_ms,
            error=f"Connection timed out after {timeout}s",
        )
    except (ssl.SSLError, OSError) as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return TLSResult(
            hostname=hostname,
            handshake_time_ms=elapsed_ms,
            error=str(exc),
        )
