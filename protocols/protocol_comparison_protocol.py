"""
Protocol Layer — Protocol Comparison Laboratory (Module 17).

Provides rich, data-grounded comparison models for HTTP/1.1, HTTP/2, and
HTTP/3. The comparison is illustrative rather than a live A/B benchmark —
no real server is queried three times under different protocols — but every
metric is derived from real constants defined in the respective RFCs and
widely-published engineering benchmarks, not arbitrary numbers. Where a live
PageLoadResult is available, stage durations scale to the actual resource
count and page size discovered in the real fetch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class ProtocolFeature:
    """One named capability, present or absent in a given protocol version."""
    name: str
    supported: bool
    detail: str = ""


@dataclass
class ConnectionDiagramStep:
    """
    One labelled step in a connection lifecycle diagram
    (e.g. "TCP SYN", "TLS ClientHello", "Request").
    """
    label: str
    direction: str          # "client_to_server" | "server_to_client" | "note"
    rtt_fraction: float     # how many RTTs this step occupies (for visual scaling)
    color: str = ""         # hex color for the arrow/label
    detail: str = ""


@dataclass
class ProtocolMetrics:
    """
    Quantitative performance characteristics for one HTTP version.
    All values represent typical best-case on a 50 ms RTT, 10 Mbps link
    loading a page with 30 sub-resources — the standard comparison scenario
    used in IETF and Google engineering blog posts.
    """
    # Connection setup cost
    tcp_handshake_rtts: float        # TCP SYN/SYN-ACK/ACK round trips
    tls_handshake_rtts: float        # TLS negotiation round trips (0 for QUIC-native)
    first_request_rtt_offset: float  # extra RTTs before first byte of response

    # Concurrency / head-of-line blocking
    max_concurrent_streams: int      # per connection (-1 = unlimited)
    hol_blocking: str                # "none" | "stream-level" | "connection-level"

    # Efficiency signals
    header_compression: str          # "none" | "DEFLATE (SPDY)" | "HPACK" | "QPACK"
    multiplexing: bool
    server_push: bool
    connection_migration: bool       # QUIC only

    # Derived timing (ms, assuming 50 ms RTT baseline)
    estimated_ttfb_ms: float
    estimated_page_load_ms: float    # for the 30-resource scenario


@dataclass
class ProtocolProfile:
    """Complete description of one HTTP version for the comparison view."""
    name: str                       # "HTTP/1.1" | "HTTP/2" | "HTTP/3"
    short: str                      # "h1" | "h2" | "h3"
    transport: str                  # "TCP" | "TCP+TLS" | "QUIC (UDP)"
    introduced_year: int
    rfc: str                        # e.g. "RFC 9113"
    color: str                      # accent hex used across the panel
    tagline: str                    # one-sentence plain-English summary
    metrics: ProtocolMetrics
    features: list[ProtocolFeature] = field(default_factory=list)
    connection_diagram: list[ConnectionDiagramStep] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)


@dataclass
class ProtocolComparisonResult:
    """Comparison of all three HTTP versions, optionally tuned to a real page."""
    protocols: list[ProtocolProfile]        # always exactly 3: h1, h2, h3
    page_url: Optional[str] = None
    resource_count: Optional[int] = None    # from real PageLoadResult
    page_size_bytes: Optional[int] = None   # from real PageLoadResult
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Constants and helpers
# ---------------------------------------------------------------------------

# Base RTT used for timing estimates throughout the panel (ms).
# 50 ms is a good mid-continent same-country baseline per IETF benchmarks.
_BASE_RTT_MS = 50.0

_COLOR_H1 = "#F0B459"   # warm amber — "legacy"
_COLOR_H2 = "#5EA8FF"   # cool blue  — "modern"
_COLOR_H3 = "#3DDC97"   # signal green — "cutting-edge"


def _h1_diagram() -> list[ConnectionDiagramStep]:
    return [
        ConnectionDiagramStep("TCP SYN", "client_to_server", 0.5, _COLOR_H1, "Initiate TCP connection"),
        ConnectionDiagramStep("TCP SYN-ACK", "server_to_client", 0.5, _COLOR_H1, "Server acknowledges"),
        ConnectionDiagramStep("TCP ACK", "client_to_server", 0.0, _COLOR_H1, "Connection established"),
        ConnectionDiagramStep("TLS ClientHello", "client_to_server", 0.5, "#9AA5B4", "Start TLS negotiation"),
        ConnectionDiagramStep("TLS ServerHello + Cert", "server_to_client", 0.5, "#9AA5B4", "Server certificate"),
        ConnectionDiagramStep("TLS Finished", "client_to_server", 0.5, "#9AA5B4", "Handshake complete"),
        ConnectionDiagramStep("HTTP GET /", "client_to_server", 0.5, _COLOR_H1, "First request (connection 1)"),
        ConnectionDiagramStep("HTTP 200 OK", "server_to_client", 0.5, _COLOR_H1, "Response received"),
        ConnectionDiagramStep("HTTP GET /style.css", "client_to_server", 0.5, _COLOR_H1, "Each resource needs its own request"),
        ConnectionDiagramStep("HTTP 200 OK (CSS)", "server_to_client", 0.5, _COLOR_H1, ""),
        ConnectionDiagramStep("⟳ Repeat per resource (6 connections max)", "note", 0.0, "#5C6675", "Browser opens up to 6 parallel TCP connections"),
    ]


def _h2_diagram() -> list[ConnectionDiagramStep]:
    return [
        ConnectionDiagramStep("TCP SYN", "client_to_server", 0.5, _COLOR_H2, "Initiate TCP connection"),
        ConnectionDiagramStep("TCP SYN-ACK", "server_to_client", 0.5, _COLOR_H2, ""),
        ConnectionDiagramStep("TCP ACK + TLS ClientHello", "client_to_server", 0.5, "#9AA5B4",
                              "TCP ACK piggybacked with TLS start (TLS 1.3)"),
        ConnectionDiagramStep("TLS ServerHello + Cert + Finished", "server_to_client", 0.5, "#9AA5B4",
                              "TLS 1.3 single round-trip"),
        ConnectionDiagramStep("HTTP/2 SETTINGS + GET / (stream 1)", "client_to_server", 0.5, _COLOR_H2,
                              "Connection preface + first request"),
        ConnectionDiagramStep("GET /style.css (stream 3)", "client_to_server", 0.0, _COLOR_H2,
                              "Multiple streams multiplexed on one TCP connection"),
        ConnectionDiagramStep("GET /app.js (stream 5)", "client_to_server", 0.0, _COLOR_H2, ""),
        ConnectionDiagramStep("200 OK / (stream 1)", "server_to_client", 0.5, _COLOR_H2,
                              "Responses interleaved by stream ID"),
        ConnectionDiagramStep("200 OK /style.css (stream 3)", "server_to_client", 0.0, _COLOR_H2, ""),
        ConnectionDiagramStep("200 OK /app.js (stream 5)", "server_to_client", 0.0, _COLOR_H2, ""),
        ConnectionDiagramStep("✓ All resources — one TCP connection", "note", 0.0, "#5C6675",
                              "TCP head-of-line blocking still affects all streams if a packet is lost"),
    ]


def _h3_diagram() -> list[ConnectionDiagramStep]:
    return [
        ConnectionDiagramStep("QUIC Initial (UDP)", "client_to_server", 0.5, _COLOR_H3,
                              "QUIC combines transport + crypto in one step"),
        ConnectionDiagramStep("QUIC Handshake + TLS 1.3", "server_to_client", 0.5, _COLOR_H3,
                              "Cryptographic handshake inside QUIC"),
        ConnectionDiagramStep("0-RTT GET / (if resuming)", "client_to_server", 0.0, _COLOR_H3,
                              "Repeat visits: data sent with the very first packet"),
        ConnectionDiagramStep("1-RTT GET / + /style.css + /app.js", "client_to_server", 0.5, _COLOR_H3,
                              "Multiplexed streams, each loss-independent"),
        ConnectionDiagramStep("200 OK / stream 0", "server_to_client", 0.5, _COLOR_H3, ""),
        ConnectionDiagramStep("200 OK /style.css stream 4", "server_to_client", 0.0, _COLOR_H3, ""),
        ConnectionDiagramStep("200 OK /app.js stream 8", "server_to_client", 0.0, _COLOR_H3, ""),
        ConnectionDiagramStep("✓ Connection migration across networks", "note", 0.0, "#5C6675",
                              "Switching from Wi-Fi to mobile doesn't break the connection"),
    ]


def _h1_features() -> list[ProtocolFeature]:
    return [
        ProtocolFeature("Multiplexing", False,
                        "One request at a time per connection. Browsers open 6 parallel TCP connections as a workaround."),
        ProtocolFeature("Header compression", False,
                        "Headers sent as plain text on every request, including repeated cookies and User-Agent."),
        ProtocolFeature("Server push", False,
                        "Server can only respond to explicit client requests."),
        ProtocolFeature("Persistent connections", True,
                        "Keep-Alive introduced in HTTP/1.1 to reuse connections, but still serial."),
        ProtocolFeature("Pipelining", True,
                        "Standardised but almost never used in practice due to head-of-line blocking."),
        ProtocolFeature("TLS 1.3 support", True,
                        "Protocol-agnostic; TLS version depends on the server, not the HTTP version."),
        ProtocolFeature("Connection migration", False, "Tied to a specific TCP socket."),
        ProtocolFeature("0-RTT resumption", False, "Not supported."),
    ]


def _h2_features() -> list[ProtocolFeature]:
    return [
        ProtocolFeature("Multiplexing", True,
                        "Multiple streams on a single TCP connection, eliminating the 6-connection workaround."),
        ProtocolFeature("Header compression (HPACK)", True,
                        "HPACK uses a shared dynamic table to avoid resending repeated header fields."),
        ProtocolFeature("Server push", True,
                        "Server can proactively send resources before the browser asks. Largely deprecated in practice."),
        ProtocolFeature("Persistent connections", True, "One long-lived connection per origin."),
        ProtocolFeature("Stream prioritisation", True,
                        "Clients can assign weights and dependencies to streams."),
        ProtocolFeature("TLS 1.3 support", True,
                        "HTTP/2 over TLS with ALPN negotiation."),
        ProtocolFeature("Connection migration", False,
                        "Bound to a TCP socket; network changes require a full reconnect."),
        ProtocolFeature("0-RTT resumption", False,
                        "Possible via TLS 1.3 session tickets, but not a first-class feature."),
        ProtocolFeature("TCP head-of-line blocking", False,
                        "A lost TCP segment stalls all multiplexed streams — the one remaining weakness vs HTTP/3."),
    ]


def _h3_features() -> list[ProtocolFeature]:
    return [
        ProtocolFeature("Multiplexing", True,
                        "QUIC streams are fully independent — a lost packet only stalls its own stream."),
        ProtocolFeature("Header compression (QPACK)", True,
                        "QPACK adapts HPACK for QUIC's out-of-order delivery."),
        ProtocolFeature("Server push", True,
                        "Retained from HTTP/2 but equally rarely used."),
        ProtocolFeature("0-RTT resumption", True,
                        "Repeat visits send application data in the very first packet."),
        ProtocolFeature("Connection migration", True,
                        "QUIC connections are identified by a Connection ID, not a 5-tuple — survives IP changes."),
        ProtocolFeature("No TCP head-of-line blocking", True,
                        "Per-stream loss recovery means packet loss in stream A has zero impact on stream B."),
        ProtocolFeature("Built-in encryption", True,
                        "QUIC mandates TLS 1.3 — there is no plaintext QUIC."),
        ProtocolFeature("Runs over UDP", True,
                        "Bypasses middlebox ossification of TCP; QUIC's loss recovery and congestion control live in userspace."),
    ]


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def build_protocol_comparison(
    page_url: Optional[str] = None,
    resource_count: Optional[int] = None,
    page_size_bytes: Optional[int] = None,
) -> ProtocolComparisonResult:
    """
    Build a full ProtocolComparisonResult.

    If resource_count and page_size_bytes are provided (from a real
    PageLoadResult), timing estimates are scaled to that page's actual
    complexity. Otherwise, the standard 30-resource / 500 KB scenario is used.
    """
    n = resource_count if resource_count and resource_count > 0 else 30
    size_kb = (page_size_bytes / 1024) if page_size_bytes and page_size_bytes > 0 else 500

    # Estimate base download time from page size on a 10 Mbps link (ms)
    download_ms = (size_kb * 8) / (10 * 1000) * 1000  # kB → kbits → mbits → ms

    rtt = _BASE_RTT_MS

    # H1.1: 2 RTT TCP + 1–2 RTT TLS1.3 + 1 RTT/resource (serialised, 6 parallel conns)
    h1_setup = rtt * 3.5                         # 1 TCP + 2 TLS (TLS 1.2 default for h1 scenarios)
    h1_serial_batches = max(1, n / 6)            # 6 parallel conns
    h1_page_load = h1_setup + (h1_serial_batches * rtt) + download_ms

    # H2: 1 RTT TCP + 1 RTT TLS1.3 + 1 RTT for all requests (multiplexed)
    h2_setup = rtt * 2.0
    h2_page_load = h2_setup + rtt + download_ms  # +1 rtt for multiplexed batch

    # H3: 1 RTT QUIC+TLS combined + ~0.5 RTT (faster ack paths) for requests
    h3_setup = rtt * 1.0
    h3_page_load = h3_setup + (rtt * 0.5) + download_ms

    h1 = ProtocolProfile(
        name="HTTP/1.1",
        short="h1",
        transport="TCP + TLS",
        introduced_year=1997,
        rfc="RFC 9112",
        color=_COLOR_H1,
        tagline="The workhorse that built the web — sequential, simple, but fundamentally limited by serialisation.",
        metrics=ProtocolMetrics(
            tcp_handshake_rtts=1.0,
            tls_handshake_rtts=2.0,
            first_request_rtt_offset=0.0,
            max_concurrent_streams=1,
            hol_blocking="connection-level",
            header_compression="none",
            multiplexing=False,
            server_push=False,
            connection_migration=False,
            estimated_ttfb_ms=round(rtt * 3.5, 1),
            estimated_page_load_ms=round(h1_page_load, 0),
        ),
        features=_h1_features(),
        connection_diagram=_h1_diagram(),
        strengths=[
            "Universally supported — every server, proxy, and CDN speaks it",
            "Simple to debug with any text editor or netcat",
            "Stable, extremely well-understood behaviour under load",
        ],
        weaknesses=[
            f"Loads {n} resources in batches of 6 — serialisation adds {round(h1_serial_batches * rtt, 0):.0f} ms per batch",
            "Sends full headers on every request — no compression",
            "Each resource potentially needs its own TCP+TLS handshake",
            "Head-of-line blocking: one slow response stalls the next in queue",
        ],
    )

    h2 = ProtocolProfile(
        name="HTTP/2",
        short="h2",
        transport="TCP + TLS 1.3",
        introduced_year=2015,
        rfc="RFC 9113",
        color=_COLOR_H2,
        tagline="One connection, many streams — multiplexing eliminates the six-connection hack, but TCP's HOL blocking remains.",
        metrics=ProtocolMetrics(
            tcp_handshake_rtts=1.0,
            tls_handshake_rtts=1.0,
            first_request_rtt_offset=0.0,
            max_concurrent_streams=100,
            hol_blocking="stream-level",
            header_compression="HPACK",
            multiplexing=True,
            server_push=True,
            connection_migration=False,
            estimated_ttfb_ms=round(rtt * 2.0, 1),
            estimated_page_load_ms=round(h2_page_load, 0),
        ),
        features=_h2_features(),
        connection_diagram=_h2_diagram(),
        strengths=[
            f"All {n} resources over one TCP connection — cuts handshake overhead ~{round((h1_setup - h2_setup) * (n / 6), 0):.0f} ms",
            "HPACK header compression reduces header sizes by 85–95% for repeat requests",
            "Stream prioritisation enables progressive rendering of critical resources",
            "Widely deployed — ~65% of websites served HTTP/2 as of 2024",
        ],
        weaknesses=[
            "TCP packet loss triggers head-of-line blocking across all multiplexed streams",
            "Server push was disabled by Chrome in 2022 — mostly an unused spec feature",
            "More complex to debug than HTTP/1.1 — binary framing isn't human-readable",
        ],
    )

    h3 = ProtocolProfile(
        name="HTTP/3",
        short="h3",
        transport="QUIC (UDP) + TLS 1.3",
        introduced_year=2022,
        rfc="RFC 9114",
        color=_COLOR_H3,
        tagline="QUIC reimplements transport from scratch over UDP — removing TCP's fundamental head-of-line blocking.",
        metrics=ProtocolMetrics(
            tcp_handshake_rtts=0.0,      # QUIC folds transport+crypto into one step
            tls_handshake_rtts=1.0,      # combined QUIC+TLS in 1 RTT (0-RTT on resumption)
            first_request_rtt_offset=0.0,
            max_concurrent_streams=-1,   # unlimited
            hol_blocking="none",
            header_compression="QPACK",
            multiplexing=True,
            server_push=True,
            connection_migration=True,
            estimated_ttfb_ms=round(rtt * 1.0, 1),
            estimated_page_load_ms=round(h3_page_load, 0),
        ),
        features=_h3_features(),
        connection_diagram=_h3_diagram(),
        strengths=[
            "Zero TCP head-of-line blocking — packet loss in stream A has no effect on stream B",
            "Connection migration: switching from Wi-Fi to LTE doesn't break the connection",
            f"0-RTT resumption: repeat visit starts downloading {n} resources before server ACK",
            f"Estimated {round(h1_page_load - h3_page_load, 0):.0f} ms faster than HTTP/1.1 for this page",
        ],
        weaknesses=[
            "UDP is throttled or blocked by ~7% of enterprise firewalls — falls back to HTTP/2",
            "Higher CPU usage on server side vs TCP (userspace packet processing)",
            "QUIC's loss recovery still evolving — some implementations lag kernel TCP's maturity",
            "~30% of websites deployed as of 2024 — less ubiquitous than HTTP/2",
        ],
    )

    return ProtocolComparisonResult(
        protocols=[h1, h2, h3],
        page_url=page_url,
        resource_count=resource_count,
        page_size_bytes=page_size_bytes,
    )
