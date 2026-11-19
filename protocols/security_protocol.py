"""
Protocol Layer — Security analysis.

Evaluates real response headers and the real TLS result already captured by
the HTTP and TLS jobs against well-known security best practices (OWASP
Secure Headers Project / MDN security header guidance). Pure derivation —
no new network call.
"""
from __future__ import annotations

from data.models import HTTPResponseRecord, SecurityCheck, SecurityReport, TLSResult


def _check_hsts(headers: dict[str, str]) -> SecurityCheck:
    value = headers.get("strict-transport-security")
    if not value:
        return SecurityCheck(
            name="HTTP Strict Transport Security (HSTS)",
            passed=False,
            severity="warning",
            detail="No Strict-Transport-Security header. Without it, a user's first visit "
                   "(or any visit after clearing cookies) could be downgraded to plain HTTP "
                   "by a network attacker before TLS even starts.",
        )

    max_age = 0
    for part in value.split(";"):
        part = part.strip()
        if part.startswith("max-age="):
            try:
                max_age = int(part.split("=", 1)[1])
            except ValueError:
                max_age = 0

    if max_age < 15768000:  # ~6 months, a common minimum recommendation
        return SecurityCheck(
            name="HTTP Strict Transport Security (HSTS)",
            passed=False,
            severity="warning",
            detail=f"HSTS is present but max-age is short ({max_age}s ≈ {max_age // 86400} days). "
                   f"A longer max-age (commonly 1+ year) gives stronger long-term protection.",
            header_value=value,
        )

    return SecurityCheck(
        name="HTTP Strict Transport Security (HSTS)",
        passed=True,
        severity="good",
        detail=f"Present with a strong max-age ({max_age // 86400} days)"
               + (", includeSubDomains" if "includesubdomains" in value.lower() else "")
               + (", preload" if "preload" in value.lower() else "") + ".",
        header_value=value,
    )


def _check_csp(headers: dict[str, str]) -> SecurityCheck:
    value = headers.get("content-security-policy")
    if not value:
        return SecurityCheck(
            name="Content Security Policy (CSP)",
            passed=False,
            severity="warning",
            detail="No Content-Security-Policy header. CSP is one of the strongest defenses "
                   "against cross-site scripting (XSS) by restricting which sources scripts, "
                   "styles, and other resources can load from.",
        )

    has_unsafe_inline = "'unsafe-inline'" in value
    has_unsafe_eval = "'unsafe-eval'" in value

    if has_unsafe_inline or has_unsafe_eval:
        weak_parts = [p for p, present in [("'unsafe-inline'", has_unsafe_inline),
                                            ("'unsafe-eval'", has_unsafe_eval)] if present]
        return SecurityCheck(
            name="Content Security Policy (CSP)",
            passed=False,
            severity="warning",
            detail=f"Present, but allows {' and '.join(weak_parts)}, which significantly "
                   f"weakens CSP's protection against XSS.",
            header_value=value,
        )

    return SecurityCheck(
        name="Content Security Policy (CSP)",
        passed=True,
        severity="good",
        detail="Present and doesn't allow 'unsafe-inline' or 'unsafe-eval'.",
        header_value=value,
    )


def _check_x_frame_options(headers: dict[str, str]) -> SecurityCheck:
    value = headers.get("x-frame-options")
    csp = headers.get("content-security-policy", "")
    has_frame_ancestors = "frame-ancestors" in csp

    if not value and not has_frame_ancestors:
        return SecurityCheck(
            name="Clickjacking Protection",
            passed=False,
            severity="warning",
            detail="No X-Frame-Options header and no frame-ancestors CSP directive — this "
                   "page could potentially be embedded in an invisible iframe on another "
                   "site for clickjacking attacks.",
        )

    # A site can use X-Frame-Options, CSP frame-ancestors, or both — report
    # accurately rather than picking one name to display while showing the
    # other mechanism's value, which would make the evidence not match the
    # claim.
    if value and has_frame_ancestors:
        detail = "Protected via both X-Frame-Options and CSP frame-ancestors."
        header_value = f"X-Frame-Options: {value}"
    elif has_frame_ancestors:
        detail = "Protected via CSP frame-ancestors."
        header_value = "(set via Content-Security-Policy, see CSP check above)"
    else:
        detail = "Protected via X-Frame-Options."
        header_value = value

    return SecurityCheck(
        name="Clickjacking Protection",
        passed=True,
        severity="good",
        detail=detail,
        header_value=header_value,
    )


def _check_content_type_options(headers: dict[str, str]) -> SecurityCheck:
    value = headers.get("x-content-type-options")
    if value and value.lower() == "nosniff":
        return SecurityCheck(
            name="MIME Sniffing Protection",
            passed=True,
            severity="good",
            detail="X-Content-Type-Options: nosniff is set, preventing browsers from "
                   "guessing content types in ways that could be exploited.",
            header_value=value,
        )
    return SecurityCheck(
        name="MIME Sniffing Protection",
        passed=False,
        severity="warning",
        detail="No X-Content-Type-Options: nosniff header — browsers may try to guess "
               "content types, which has historically enabled some content-spoofing attacks.",
    )


def _check_referrer_policy(headers: dict[str, str]) -> SecurityCheck:
    value = headers.get("referrer-policy")
    if value:
        return SecurityCheck(
            name="Referrer Policy",
            passed=True,
            severity="good",
            detail=f"Set to '{value}', controlling how much referrer information is sent "
                   f"to other sites when users navigate away.",
            header_value=value,
        )
    return SecurityCheck(
        name="Referrer Policy",
        passed=False,
        severity="warning",
        detail="No Referrer-Policy header — browsers fall back to their own default, which "
               "can leak full URLs (including any sensitive query parameters) to third "
               "parties linked from this page.",
    )


def _check_tls(tls: TLSResult | None) -> list[SecurityCheck]:
    if tls is None or tls.error:
        return [SecurityCheck(
            name="TLS Connection",
            passed=False,
            severity="critical",
            detail=tls.error if tls and tls.error else "No TLS connection was established (site may be plain HTTP).",
        )]

    checks = []

    old_versions = ("TLSv1", "TLSv1.1", "SSLv2", "SSLv3")
    if tls.tls_version in old_versions:
        checks.append(SecurityCheck(
            name="TLS Version",
            passed=False,
            severity="critical",
            detail=f"Using {tls.tls_version}, which is deprecated and has known weaknesses. "
                   f"Modern browsers are phasing out support for it.",
            header_value=tls.tls_version,
        ))
    else:
        checks.append(SecurityCheck(
            name="TLS Version",
            passed=True,
            severity="good",
            detail=f"Using {tls.tls_version}, a modern, secure protocol version.",
            header_value=tls.tls_version,
        ))

    cert = tls.leaf_certificate
    if cert:
        if cert.is_expired:
            checks.append(SecurityCheck(
                name="Certificate Validity",
                passed=False,
                severity="critical",
                detail="The server's TLS certificate has expired. Browsers will show users "
                       "a hard security warning.",
            ))
        elif cert.days_until_expiry is not None and cert.days_until_expiry <= 14:
            checks.append(SecurityCheck(
                name="Certificate Validity",
                passed=False,
                severity="warning",
                detail=f"Certificate expires in {cert.days_until_expiry} days — renewal is "
                       f"due soon to avoid an outage.",
            ))
        else:
            checks.append(SecurityCheck(
                name="Certificate Validity",
                passed=True,
                severity="good",
                detail=f"Valid certificate"
                       + (f", expires in {cert.days_until_expiry} days" if cert.days_until_expiry is not None else "")
                       + ".",
            ))

    return checks


def analyze_security(url: str, response: HTTPResponseRecord | None, tls: TLSResult | None) -> SecurityReport:
    """
    Evaluate the real headers from `response` and the real TLS state from
    `tls` against common security best practices. Pure analysis — assumes
    response/tls were already fetched by the HTTP/TLS jobs.
    """
    checks: list[SecurityCheck] = []

    checks.extend(_check_tls(tls))

    if response is not None:
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        checks.append(_check_hsts(headers_lower))
        checks.append(_check_csp(headers_lower))
        checks.append(_check_x_frame_options(headers_lower))
        checks.append(_check_content_type_options(headers_lower))
        checks.append(_check_referrer_policy(headers_lower))

    return SecurityReport(url=url, checks=checks)
