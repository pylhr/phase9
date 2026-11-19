"""
Protocol Layer — Failure Simulation Laboratory (Module 18).

Defines the set of network failure scenarios the lab can simulate, and the
logic for computing what each scenario's timeline would look like, derived
from real networking behaviour (RFC-defined timeouts, TCP retransmit backoff,
DNS SERVFAIL semantics, etc.).

No actual network calls are made — every result is computed from the
well-known characteristics of the failure type. Where a real PageLoadResult
is available, baseline timings are taken from it so the degraded scenarios
feel grounded rather than arbitrary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

class FailureType(str, Enum):
    HIGH_LATENCY        = "high_latency"
    PACKET_LOSS         = "packet_loss"
    DNS_FAILURE         = "dns_failure"
    TLS_FAILURE         = "tls_failure"
    SLOW_CONNECTION     = "slow_connection"
    CONNECTION_TIMEOUT  = "connection_timeout"
    SERVER_ERROR        = "server_error"
    CERTIFICATE_EXPIRED = "certificate_expired"


@dataclass
class FailureScenario:
    """Static description of one failure type shown in the left-hand scenario list."""
    failure_type: FailureType
    name: str
    short_description: str
    icon: str               # Unicode emoji / symbol for the scenario button
    color: str              # Accent hex used for this scenario's visuals


# The ordered list of scenarios available in the lab.
ALL_SCENARIOS: list[FailureScenario] = [
    FailureScenario(
        FailureType.HIGH_LATENCY,
        "High Latency",
        "Simulate a high-latency link (250 ms RTT) — the kind seen on intercontinental "
        "connections, satellite links, or congested mobile networks.",
        "🌐",
        "#F0B459",
    ),
    FailureScenario(
        FailureType.PACKET_LOSS,
        "Packet Loss",
        "Simulate 5% random packet loss — common on Wi-Fi and mobile networks — "
        "and see how TCP retransmission backoff and HTTP/2 HOL blocking amplify the impact.",
        "📦",
        "#C77DFF",
    ),
    FailureScenario(
        FailureType.DNS_FAILURE,
        "DNS Failure",
        "Simulate what happens when DNS resolution fails: NXDOMAIN, SERVFAIL, or a "
        "resolver timeout. The browser never gets an IP, so no connection is attempted.",
        "🔍",
        "#F2607A",
    ),
    FailureScenario(
        FailureType.TLS_FAILURE,
        "TLS Handshake Failure",
        "Simulate a TLS negotiation failure — mismatched cipher suites, a rejected "
        "certificate, or a protocol version mismatch — and see how the browser reports it.",
        "🔒",
        "#8C7CFF",
    ),
    FailureScenario(
        FailureType.SLOW_CONNECTION,
        "Slow Connection (2G)",
        "Simulate a 50 kbps / 300 ms RTT 2G connection — still the baseline for "
        "~15% of web users worldwide — and see how connection time dominates over bandwidth.",
        "📶",
        "#5EA8FF",
    ),
    FailureScenario(
        FailureType.CONNECTION_TIMEOUT,
        "Connection Timeout",
        "Simulate a destination host that accepts TCP SYN packets but never responds — "
        "a common firewall misconfiguration — triggering the OS's 75-second retransmit timeout.",
        "⏱",
        "#F0B459",
    ),
    FailureScenario(
        FailureType.SERVER_ERROR,
        "Server Error (503)",
        "Simulate a destination that is reachable but returns HTTP 503 Service Unavailable "
        "with a Retry-After header — the browser's full loading pipeline runs, then fails at the last step.",
        "🚫",
        "#F2607A",
    ),
    FailureScenario(
        FailureType.CERTIFICATE_EXPIRED,
        "Expired Certificate",
        "Simulate a server whose TLS certificate has expired — "
        "everything up to the TLS handshake works, but the browser halts and shows a warning.",
        "📜",
        "#F0B459",
    ),
]


# ---------------------------------------------------------------------------
# Simulation result models
# ---------------------------------------------------------------------------

@dataclass
class SimulatedStageResult:
    """
    One stage of a simulated page-load under a failure condition.
    duration_ms is the simulated wall-clock time for this stage.
    status is "ok", "slow", "failed", or "skipped".
    """
    stage_name: str
    duration_ms: float
    status: str                 # "ok" | "slow" | "failed" | "skipped"
    detail: str = ""
    color: str = ""             # per-status color — set by the simulation engine


@dataclass
class FailureSimulationResult:
    """Full result of running one failure scenario."""
    scenario: FailureScenario
    stages: list[SimulatedStageResult] = field(default_factory=list)
    total_ms: float = 0.0
    outcome: str = ""           # plain-English summary of what the user would see
    outcome_color: str = ""
    what_happened: str = ""     # technical explanation
    mitigation: str = ""        # how this would be handled / avoided in practice
    baseline_ms: Optional[float] = None   # normal total time for contrast
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Stage colours
# ---------------------------------------------------------------------------

_OK     = "#3DDC97"
_SLOW   = "#F0B459"
_FAILED = "#F2607A"
_SKIP   = "#5C6675"


def _stage(name: str, ms: float, status: str, detail: str = "") -> SimulatedStageResult:
    color = {
        "ok":      _OK,
        "slow":    _SLOW,
        "failed":  _FAILED,
        "skipped": _SKIP,
    }.get(status, _SKIP)
    return SimulatedStageResult(name, ms, status, detail, color)


# ---------------------------------------------------------------------------
# Simulation functions — one per FailureType
# ---------------------------------------------------------------------------

def _simulate_high_latency(baseline_ms: float) -> FailureSimulationResult:
    rtt = 250.0  # ms, representative of satellite or poor intercontinental path
    sc = ALL_SCENARIOS[0]

    # TCP + TLS each take rtt*1.5 on a long-latency link (handshake + overhead)
    stages = [
        _stage("DNS Resolution",       rtt * 2,     "slow",
               f"2 DNS round trips × {rtt:.0f} ms RTT = {rtt*2:.0f} ms"),
        _stage("TCP Handshake",        rtt * 1.0,   "slow",
               f"SYN + SYN-ACK over {rtt:.0f} ms RTT"),
        _stage("TLS Negotiation",      rtt * 2.0,   "slow",
               f"TLS 1.3 requires 1 RTT for new sessions; older servers need 2"),
        _stage("HTTP Request",         rtt * 0.5,   "slow",
               "Request + TTFB overhead on high-latency path"),
        _stage("HTML Download",        rtt * 1.0,   "slow",
               "Bandwidth is fine; it's the round-trip overhead that dominates"),
        _stage("Sub-resources (CSS/JS/img)", rtt * 8.0, "slow",
               f"30 resources × even 1 extra RTT = {30 * rtt:.0f} ms extra wait"),
    ]
    total = sum(s.duration_ms for s in stages)

    return FailureSimulationResult(
        scenario=sc,
        stages=stages,
        total_ms=total,
        outcome="Page loads — but slowly. Every round trip takes 250 ms, stacking up across DNS, TCP, TLS, and each resource.",
        outcome_color=_SLOW,
        what_happened=(
            "High latency multiplies across every protocol handshake. TCP needs 1 RTT, TLS needs 1–2 RTTs, "
            "and each uncached resource needs at least 1 RTT. With HTTP/1.1's 6-connection limit, resources "
            f"serialise into batches — each batch adds {rtt:.0f} ms. Total estimated load time: {total/1000:.1f}s "
            f"vs a typical {baseline_ms/1000:.1f}s."
        ),
        mitigation=(
            "CDN edge servers reduce client-to-server RTT to 10–30 ms. HTTP/2 multiplexing cuts resource RTTs. "
            "HTTP/3's 0-RTT resumption skips the handshake entirely on repeat visits. "
            "Reducing resource count (bundling, sprites) directly reduces RTT multiplication."
        ),
        baseline_ms=baseline_ms,
    )


def _simulate_packet_loss(baseline_ms: float) -> FailureSimulationResult:
    loss_pct = 5.0
    rtt = 50.0
    sc = ALL_SCENARIOS[1]

    # TCP retransmit after packet loss: initial RTO = 200ms, doubles each time (RFC 6298)
    rto_ms = 200.0

    stages = [
        _stage("DNS Resolution",    rtt * 2,   "ok",   "UDP DNS rarely affected by low packet loss"),
        _stage("TCP Handshake",     rtt * 1.5, "slow",
               f"{loss_pct}% chance SYN is dropped; if so, retransmit waits {rto_ms:.0f} ms"),
        _stage("TLS Negotiation",   rtt * 1.5, "slow",
               f"TLS records fragmented across TCP segments — one drop stalls the handshake"),
        _stage("HTTP Request",      rtt * 0.5, "ok"),
        _stage("HTML Download",     rtt * 1.0, "ok"),
        _stage("Sub-resources",     rtt * 4.0 + rto_ms * 2.0, "slow",
               f"At 5% loss, a 30-resource page statistically drops ~1-2 segments — each waits {rto_ms:.0f}–{rto_ms*2:.0f} ms"),
        _stage("TCP Retransmit ×2 (HOL)", rto_ms * 2.0, "slow",
               "HTTP/2: a dropped segment stalls ALL multiplexed streams until it's retransmitted"),
    ]
    total = sum(s.duration_ms for s in stages)

    return FailureSimulationResult(
        scenario=sc,
        stages=stages,
        total_ms=total,
        outcome="Page loads but with noticeable stutters. A 5% loss rate makes TCP's exponential backoff kick in — each retransmit stalls for at least 200 ms.",
        outcome_color=_SLOW,
        what_happened=(
            "TCP's RTO (Retransmission Timeout) starts at 200 ms and doubles on each consecutive loss (RFC 6298). "
            "A page with 30 resources statistically drops at least one segment. With HTTP/2 multiplexing, "
            "that one dropped TCP segment stalls all concurrent streams — the infamous TCP head-of-line blocking. "
            f"HTTP/3's QUIC would isolate the loss to only the affected stream, saving ~{rto_ms*1.5:.0f} ms."
        ),
        mitigation=(
            "HTTP/3 / QUIC eliminates TCP HOL blocking — packet loss affects only the individual QUIC stream. "
            "TLS record size tuning (smaller records = less data lost per packet). "
            "BBR congestion control recovers faster than CUBIC on lossy links."
        ),
        baseline_ms=baseline_ms,
    )


def _simulate_dns_failure(baseline_ms: float) -> FailureSimulationResult:
    sc = ALL_SCENARIOS[2]

    stages = [
        _stage("DNS Query sent",        2.0,   "ok",   "OS sends query to configured resolver"),
        _stage("DNS SERVFAIL received", 5.0,   "failed",
               "Resolver returns SERVFAIL — it couldn't reach the authoritative nameserver"),
        _stage("DNS retry (5s timeout)", 5000.0, "failed",
               "Stub resolver retries up to 3 times before giving up — each attempt waits up to 5 s"),
        _stage("TCP Handshake",         0.0,   "skipped",
               "No IP address — connection cannot be attempted"),
        _stage("TLS Negotiation",       0.0,   "skipped"),
        _stage("HTTP Request",          0.0,   "skipped"),
        _stage("Page Load",             0.0,   "skipped"),
    ]
    total = sum(s.duration_ms for s in stages)

    return FailureSimulationResult(
        scenario=sc,
        stages=stages,
        total_ms=total,
        outcome='Browser shows "DNS_PROBE_FINISHED_NXDOMAIN" (Chrome) or "Server not found" (Firefox) — immediately, with no page content.',
        outcome_color=_FAILED,
        what_happened=(
            "DNS is the first step in every connection. A SERVFAIL means the resolver couldn't reach the "
            "authoritative nameserver for this domain, or it returned an error. NXDOMAIN means the domain "
            "simply doesn't exist. Either way, the browser has no IP address to connect to — all subsequent "
            f"stages are skipped entirely. The OS stub resolver retried 3 times (up to {5000*3/1000:.0f}s wait) "
            "before surfacing the error."
        ),
        mitigation=(
            "Use a reliable public resolver (8.8.8.8, 1.1.1.1) with DNS-over-HTTPS to prevent tampering. "
            "DNS TTLs > 300 s let browsers cache resolutions and survive short resolver outages. "
            "Multiple A records with different IPs enable Happy Eyeballs — browser tries the next IP if the first fails."
        ),
        baseline_ms=baseline_ms,
    )


def _simulate_tls_failure(baseline_ms: float) -> FailureSimulationResult:
    rtt = 50.0
    sc = ALL_SCENARIOS[3]

    stages = [
        _stage("DNS Resolution",       rtt * 2,   "ok"),
        _stage("TCP Handshake",        rtt,       "ok"),
        _stage("TLS ClientHello",      rtt * 0.5, "ok",   "Client advertises supported cipher suites and TLS versions"),
        _stage("TLS ServerHello",      rtt * 0.5, "ok",   "Server selects cipher suite"),
        _stage("Certificate validation", rtt * 0.5, "failed",
               "Certificate chain validation fails — e.g. self-signed, expired, or wrong hostname"),
        _stage("TLS Alert: handshake_failure", 5.0, "failed",
               "Server or client sends a fatal TLS alert; connection is torn down"),
        _stage("HTTP Request",         0.0,       "skipped"),
        _stage("Page Load",            0.0,       "skipped"),
    ]
    total = sum(s.duration_ms for s in stages)

    return FailureSimulationResult(
        scenario=sc,
        stages=stages,
        total_ms=total,
        outcome='Browser shows an interstitial warning page ("Your connection is not private" in Chrome). No page content is shown until the user explicitly overrides.',
        outcome_color=_FAILED,
        what_happened=(
            "TCP connects successfully, and the TLS handshake begins — but the server's certificate fails one or "
            "more of the browser's validation checks: the certificate may be self-signed, expired, issued for a "
            "different hostname, or use a deprecated signature algorithm (e.g. SHA-1). The browser sends a fatal "
            "TLS alert (handshake_failure or certificate_unknown) and closes the connection. No HTTP request "
            "is ever sent — the page has zero bytes loaded."
        ),
        mitigation=(
            "Use a certificate from a trusted CA (Let's Encrypt is free). Ensure the certificate covers "
            "www.example.com AND example.com (or use a wildcard). Automate renewal to avoid expiry. "
            "HSTS preloading prevents users from bypassing the warning on subsequent visits."
        ),
        baseline_ms=baseline_ms,
    )


def _simulate_slow_connection(baseline_ms: float) -> FailureSimulationResult:
    bw_kbps  = 50.0          # 2G: ~50 kbps downstream
    rtt      = 300.0          # 2G: 300 ms RTT
    size_kb  = 500.0          # assume 500 KB page (median)
    sc = ALL_SCENARIOS[4]

    download_ms = (size_kb * 8) / bw_kbps * 1000  # kB → kbits / kbps → seconds → ms

    stages = [
        _stage("DNS Resolution",         rtt * 2,     "slow",
               f"{rtt:.0f} ms RTT — even DNS takes {rtt*2:.0f} ms"),
        _stage("TCP Handshake",          rtt,         "slow",
               f"1 RTT = {rtt:.0f} ms"),
        _stage("TLS Negotiation",        rtt * 2,     "slow",
               f"TLS 1.3 = 1 RTT = {rtt:.0f} ms; TLS 1.2 = 2 RTTs = {rtt*2:.0f} ms"),
        _stage("HTML Download",          rtt + (30 * 8 / bw_kbps * 1000), "slow",
               "30 KB HTML at 50 kbps = 4.8 s"),
        _stage("Critical CSS/JS",        rtt + (80 * 8 / bw_kbps * 1000), "slow",
               "80 KB critical CSS+JS at 50 kbps = 12.8 s"),
        _stage("Images + remaining resources", download_ms * 0.75, "slow",
               f"~375 KB images at 50 kbps = {download_ms*0.75/1000:.1f}s"),
    ]
    total = sum(s.duration_ms for s in stages)

    return FailureSimulationResult(
        scenario=sc,
        stages=stages,
        total_ms=total,
        outcome=f"Page eventually loads after ~{total/1000:.0f}s — nearly unusable. Users on 2G face this on every page load.",
        outcome_color=_SLOW,
        what_happened=(
            f"A 2G link provides ~50 kbps with 300 ms RTT. The 500 KB page takes {total/1000:.0f}s to fully load. "
            "Even before downloading a single byte, the TCP + TLS handshake already consumes 3 RTTs = "
            f"{rtt*3:.0f} ms. At 50 kbps, every 1 KB = 160 ms of transfer time. This is the daily reality "
            "for ~15% of web users globally (GSMA Mobile Internet Report 2023)."
        ),
        mitigation=(
            "Serve a minimal critical-path CSS < 14 KB (one TCP window). Defer non-critical JS. "
            "Use WebP/AVIF images (50–70% smaller than JPEG). Serve a Service Worker pre-cache. "
            "HTTP/2 server push critical resources speculatively. "
            "Consider AMP or a dedicated lite page for low-bandwidth users."
        ),
        baseline_ms=baseline_ms,
    )


def _simulate_connection_timeout(baseline_ms: float) -> FailureSimulationResult:
    # TCP SYN timeout: initial RTO 1s, then 2s, 4s, 8s, 16s, 32s (RFC 6298 §2.4)
    # Most OSes give up after 6 retries = 63s total (Linux default)
    tcp_timeout_ms = 75_000.0
    sc = ALL_SCENARIOS[5]

    stages = [
        _stage("DNS Resolution",   100.0,           "ok",
               "DNS resolves successfully — the domain exists"),
        _stage("TCP SYN sent",     1.0,             "ok",
               "SYN packet sent; no response received"),
        _stage("TCP SYN retry ×1 (1s RTO)", 1_000.0, "slow",
               "RTO = 1 s, no response — retry"),
        _stage("TCP SYN retry ×2 (2s RTO)", 2_000.0, "slow",
               "RTO doubles to 2 s"),
        _stage("TCP SYN retry ×3 (4s RTO)", 4_000.0, "slow",
               "RTO doubles to 4 s"),
        _stage("TCP SYN retry ×4 (8s RTO)", 8_000.0, "slow",
               ""),
        _stage("TCP SYN retry ×5 (16s RTO)", 16_000.0, "slow",
               ""),
        _stage("TCP SYN retry ×6 (32s RTO)", 32_000.0, "failed",
               "Final retry; OS gives up and returns ETIMEDOUT"),
        _stage("TLS / HTTP",        0.0,   "skipped"),
    ]
    total = sum(s.duration_ms for s in stages)

    return FailureSimulationResult(
        scenario=sc,
        stages=stages,
        total_ms=total,
        outcome=f'Browser spins for ~{total/1000:.0f}s then shows "ERR_CONNECTION_TIMED_OUT". No bytes are transferred.',
        outcome_color=_FAILED,
        what_happened=(
            "The server (or a firewall) silently drops TCP SYN packets rather than responding with RST. "
            "The OS TCP stack implements exponential backoff per RFC 6298: it retries the SYN after 1 s, "
            "then 2 s, 4 s, 8 s, 16 s, 32 s — waiting a total of 63+ seconds before giving up. "
            "This is distinct from a refused connection (instant RST → ERR_CONNECTION_REFUSED) or a "
            "reachability error (ICMP unreachable → faster failure)."
        ),
        mitigation=(
            "Firewalls should return TCP RST instead of silently dropping — enables fast failure (< 1 ms). "
            "Browsers implement parallel connection racing (Happy Eyeballs v2, RFC 8305) to fail over to "
            "an alternative IP sooner. Service workers can serve a cached offline page during the timeout."
        ),
        baseline_ms=baseline_ms,
    )


def _simulate_server_error(baseline_ms: float) -> FailureSimulationResult:
    rtt = 50.0
    sc = ALL_SCENARIOS[6]

    stages = [
        _stage("DNS Resolution",    rtt * 2,   "ok"),
        _stage("TCP Handshake",     rtt,       "ok"),
        _stage("TLS Negotiation",   rtt,       "ok"),
        _stage("HTTP GET /",        rtt * 0.5, "ok",   "Request sent successfully"),
        _stage("HTTP 503 received", rtt * 0.5, "failed",
               "Server returns 503 Service Unavailable with Retry-After: 30"),
        _stage("Page render",       0.0,       "skipped",
               "No HTML body to parse; browser shows error page"),
    ]
    total = sum(s.duration_ms for s in stages)

    return FailureSimulationResult(
        scenario=sc,
        stages=stages,
        total_ms=total,
        outcome='Browser shows the server\'s error page (or its own "Service Unavailable" page). The full connection pipeline ran successfully — the failure is at the application layer.',
        outcome_color=_FAILED,
        what_happened=(
            "503 Service Unavailable means the server is temporarily unable to handle the request — "
            "typically because all application workers are busy, a backend database is down, or the service "
            "is in a rolling deployment. The Retry-After header tells the client to try again after 30 seconds. "
            "Crucially, every network layer worked: DNS, TCP, TLS, and HTTP all succeeded. "
            "The failure is above the transport — purely in application logic."
        ),
        mitigation=(
            "CDN edge nodes can serve stale cached content during origin outages (stale-while-revalidate). "
            "Load balancers should remove unhealthy backends from rotation within one health-check interval. "
            "Application-level circuit breakers prevent cascading failures. "
            "Exponential backoff in retry logic prevents thundering-herd re-requests."
        ),
        baseline_ms=baseline_ms,
    )


def _simulate_certificate_expired(baseline_ms: float) -> FailureSimulationResult:
    rtt = 50.0
    sc = ALL_SCENARIOS[7]

    stages = [
        _stage("DNS Resolution",           rtt * 2,   "ok"),
        _stage("TCP Handshake",            rtt,       "ok"),
        _stage("TLS ClientHello",          rtt * 0.5, "ok"),
        _stage("TLS ServerHello",          rtt * 0.5, "ok"),
        _stage("Certificate chain received", rtt * 0.5, "ok",
               "Certificate chain delivered from server"),
        _stage("Certificate expiry check", 1.0, "failed",
               "notAfter field is in the past — browser rejects the certificate"),
        _stage("TLS Alert: certificate_expired", 5.0, "failed",
               "Fatal TLS alert sent; handshake aborted"),
        _stage("HTTP / Page Load",         0.0,       "skipped"),
    ]
    total = sum(s.duration_ms for s in stages)

    return FailureSimulationResult(
        scenario=sc,
        stages=stages,
        total_ms=total,
        outcome='"Your connection is not private" (Chrome) / "Warning: Potential Security Risk Ahead" (Firefox). The page is blocked until the user explicitly accepts the risk.',
        outcome_color=_FAILED,
        what_happened=(
            "TLS certificates have a validity period (notBefore / notAfter). Once the notAfter date passes, "
            "every browser in the world will refuse to trust the certificate and block the connection — "
            "regardless of whether the certificate was legitimately issued. The TCP connection succeeded, "
            "the certificate was delivered, but the local clock check fails. "
            "This is the single most common cause of unexpected HTTPS outages in production."
        ),
        mitigation=(
            "Automate certificate renewal with Let's Encrypt + Certbot or ACME clients — certificates renew "
            "at 60 days, expire at 90. Monitor expiry via certificate transparency logs or tools like "
            "certspotter. Set a calendar alert at 30 days before expiry. "
            "HSTS preloading prevents users from bypassing the warning."
        ),
        baseline_ms=baseline_ms,
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_SIMULATORS = {
    FailureType.HIGH_LATENCY:        _simulate_high_latency,
    FailureType.PACKET_LOSS:         _simulate_packet_loss,
    FailureType.DNS_FAILURE:         _simulate_dns_failure,
    FailureType.TLS_FAILURE:         _simulate_tls_failure,
    FailureType.SLOW_CONNECTION:     _simulate_slow_connection,
    FailureType.CONNECTION_TIMEOUT:  _simulate_connection_timeout,
    FailureType.SERVER_ERROR:        _simulate_server_error,
    FailureType.CERTIFICATE_EXPIRED: _simulate_certificate_expired,
}


def simulate_failure(
    failure_type: FailureType,
    baseline_ms: float = 800.0,
) -> FailureSimulationResult:
    """
    Run the failure simulation for *failure_type*.

    *baseline_ms* is the normal total load time (from a real PageLoadResult
    if available, or 800 ms as a reasonable default). It is used to
    contextualise the degraded timings in the result's what_happened text.
    """
    fn = _SIMULATORS.get(failure_type)
    if fn is None:
        sc = next((s for s in ALL_SCENARIOS if s.failure_type == failure_type), ALL_SCENARIOS[0])
        return FailureSimulationResult(
            scenario=sc,
            error=f"No simulator implemented for {failure_type}",
        )
    return fn(baseline_ms)
