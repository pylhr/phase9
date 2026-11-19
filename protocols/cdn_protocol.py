"""
Protocol Layer — CDN detection.

Determines whether a CDN is in front of a site using real, verifiable
signals:
  1. Response headers with well-known CDN signatures (Cloudflare's cf-ray,
     Fastly's x-served-by cache-node naming, CloudFront's x-amz-cf-id, etc.)
     — these are genuinely documented behaviors of each provider, not
     guesses.
  2. The resolved IP's membership in a CDN's publicly published IP ranges
     (a small, well-known subset is embedded below; providers publish much
     larger official lists, e.g. Cloudflare at
     https://www.cloudflare.com/ips/ and Fastly at
     https://api.fastly.com/public-ip-list).
  3. Reverse DNS, when available (many CDN edge nodes don't have PTR
     records, so this is a supporting signal at best, not a primary one).

No new network call beyond what HTTP/DNS jobs already made — this is pure
analysis of response headers plus one IP-range check and an optional
reverse-DNS lookup.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Optional

from data.models import CDNResult, CDNSignal, HTTPResponseRecord

# A small, well-known sample of each major CDN's publicly documented IP
# ranges. Real providers publish much larger official lists (linked above);
# this subset covers commonly-seen ranges for a fast, dependency-free check
# without fetching a live list over the network on every exploration.
_KNOWN_CDN_RANGES: dict[str, list[str]] = {
    "Cloudflare": [
        "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13",
        "131.0.72.0/22", "188.114.96.0/20",
    ],
    "Fastly": [
        "151.101.0.0/16", "199.232.0.0/16", "23.235.32.0/20",
    ],
    "Amazon CloudFront": [
        "13.32.0.0/15", "13.224.0.0/14", "143.204.0.0/16", "204.246.164.0/22",
    ],
    "Akamai": [
        "23.32.0.0/11", "23.192.0.0/11", "104.64.0.0/10",
    ],
    "Google Cloud CDN": [
        "34.96.0.0/12", "34.104.0.0/13",
    ],
    "Microsoft Azure CDN": [
        "13.107.0.0/16", "152.199.0.0/16",
    ],
}

# Header-name -> (provider or None for "definitely a CDN/proxy but unknown which"),
# matched case-insensitively.
_HEADER_SIGNALS: list[tuple[str, Optional[str]]] = [
    ("cf-ray", "Cloudflare"),
    ("cf-cache-status", "Cloudflare"),
    ("x-amz-cf-id", "Amazon CloudFront"),
    ("x-amz-cf-pop", "Amazon CloudFront"),
    ("x-akamai-transformed", "Akamai"),
    ("akamai-grn", "Akamai"),
    ("x-served-by", "Fastly"),  # Fastly's cache-node naming is distinctive; confirmed further below
    ("x-fastly-request-id", "Fastly"),
    ("x-azure-ref", "Microsoft Azure CDN"),
    ("x-cdn", None),
    ("x-cache", None),
    ("x-cache-hits", None),
]


def _check_ip_ranges(ip: str) -> Optional[str]:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    for provider, ranges in _KNOWN_CDN_RANGES.items():
        for cidr in ranges:
            if addr in ipaddress.ip_network(cidr):
                return provider
    return None


def _reverse_dns(ip: str, timeout: float = 1.5) -> Optional[str]:
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return None
    finally:
        socket.setdefaulttimeout(previous)


def detect_cdn(url: str, hostname: str, resolved_ip: Optional[str],
                response: Optional[HTTPResponseRecord]) -> CDNResult:
    """
    Evaluate real signals already available from the DNS/HTTP jobs (resolved
    IP, response headers) to determine whether a CDN fronts this site.
    """
    signals: list[CDNSignal] = []
    provider_votes: dict[str, int] = {}

    if response is not None:
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        for header_name, provider in _HEADER_SIGNALS:
            if header_name in headers_lower:
                value = headers_lower[header_name]
                # Fastly's x-served-by specifically uses "cache-<pop>-<id>"
                # naming; a generic x-cache/x-cdn header alone is weaker
                # evidence, so only attribute Fastly when the value matches
                # their actual documented format.
                if header_name == "x-served-by" and "cache-" not in value.lower():
                    provider = None
                signals.append(CDNSignal(
                    header_name=header_name,
                    header_value=value[:120],
                    indicates_provider=provider,
                ))
                if provider:
                    provider_votes[provider] = provider_votes.get(provider, 0) + 2

        server_header = headers_lower.get("server", "")
        for keyword, provider in [("cloudflare", "Cloudflare"), ("akamaighost", "Akamai"),
                                    ("varnish", None), ("fastly", "Fastly")]:
            if keyword in server_header.lower():
                signals.append(CDNSignal(
                    header_name="server", header_value=server_header, indicates_provider=provider,
                ))
                if provider:
                    provider_votes[provider] = provider_votes.get(provider, 0) + 2

    ip_provider = None
    if resolved_ip:
        ip_provider = _check_ip_ranges(resolved_ip)
        if ip_provider:
            signals.append(CDNSignal(
                header_name="(resolved IP range)",
                header_value=resolved_ip,
                indicates_provider=ip_provider,
            ))
            provider_votes[ip_provider] = provider_votes.get(ip_provider, 0) + 3

    if resolved_ip:
        rdns = _reverse_dns(resolved_ip)
        if rdns:
            rdns_lower = rdns.lower()
            for keyword, provider in [("cloudflare", "Cloudflare"), ("fastly", "Fastly"),
                                        ("akamai", "Akamai"), ("cloudfront", "Amazon CloudFront")]:
                if keyword in rdns_lower:
                    signals.append(CDNSignal(
                        header_name="(reverse DNS)", header_value=rdns, indicates_provider=provider,
                    ))
                    provider_votes[provider] = provider_votes.get(provider, 0) + 1

    is_cdn_detected = bool(provider_votes) or any(s.indicates_provider is None for s in signals)
    detected_provider = max(provider_votes, key=provider_votes.get) if provider_votes else None

    if detected_provider and provider_votes[detected_provider] >= 4:
        confidence = "high"
    elif detected_provider or signals:
        confidence = "medium" if detected_provider else "low"
    else:
        confidence = "none"

    return CDNResult(
        url=url,
        hostname=hostname,
        resolved_ip=resolved_ip,
        is_cdn_detected=is_cdn_detected,
        detected_provider=detected_provider,
        confidence=confidence,
        signals=signals,
    )
