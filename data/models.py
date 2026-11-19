"""
Data Layer — core domain models shared across the application.

These are plain dataclasses with no Qt or networking dependencies, so they can
be reused by the service layer, the UI layer, and (later) the SQLite
persistence layer without creating import cycles.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class SessionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class DNSRecord:
    """A single DNS resource record returned for a query."""
    record_type: str          # A, AAAA, CNAME, MX, NS, TXT, ...
    value: str                # the record's data (IP, hostname, etc.)
    ttl: Optional[int] = None
    priority: Optional[int] = None  # used for MX records


@dataclass
class DNSResult:
    """Full result of resolving one domain, across all queried record types."""
    domain: str
    resolver_used: str
    query_time_ms: float
    records: list[DNSRecord] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # record_type -> error message
    queried_at: datetime = field(default_factory=datetime.now)

    def records_of_type(self, record_type: str) -> list[DNSRecord]:
        return [r for r in self.records if r.record_type == record_type]


@dataclass
class HTTPRequestRecord:
    """One outgoing HTTP request captured during a page load."""
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    sent_at: datetime = field(default_factory=datetime.now)

    def raw_format(self) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(self.url)
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        lines = [f"{self.method} {path} HTTP/1.1"]
        for key, value in self.headers.items():
            lines.append(f"{key}: {value}")
        if self.body:
            lines.append("")
            lines.append(self.body)
        return "\n".join(lines)


@dataclass
class HTTPResponseRecord:
    """The response received for one HTTPRequestRecord."""
    status_code: int
    reason: str
    headers: dict[str, str] = field(default_factory=dict)
    body_preview: str = ""           # truncated, decoded text preview
    body_size_bytes: int = 0         # decompressed body size
    compressed_size_bytes: Optional[int] = None  # real bytes transferred over the wire
    content_type: str = ""
    compression: Optional[str] = None  # e.g. "gzip", "br", or None
    response_time_ms: float = 0.0
    http_version: str = ""
    is_binary: bool = False
    # A server can send multiple Set-Cookie headers, one per cookie. Most
    # HTTP libraries (including ours, via dict(headers)) incorrectly
    # comma-join repeated header values into one string for any header that
    # appears more than once — fine for headers like Vary, but wrong for
    # Set-Cookie, where commas can appear inside legitimate values (e.g.
    # Expires dates) and joining breaks parsing. We keep each raw
    # Set-Cookie header separately here instead.
    raw_set_cookie_headers: list[str] = field(default_factory=list)

    def raw_format(self) -> str:
        version = self.http_version or "HTTP/1.1"
        # httpx's http_version is already e.g. "HTTP/1.1", not just "1.1" —
        # avoid double-prefixing if a future caller passes either form.
        if not version.upper().startswith("HTTP/"):
            version = f"HTTP/{version}"
        lines = [f"{version} {self.status_code} {self.reason}"]
        for key, value in self.headers.items():
            lines.append(f"{key}: {value}")
        for cookie_header in self.raw_set_cookie_headers:
            lines.append(f"set-cookie: {cookie_header}")
        return "\n".join(lines)


@dataclass
class CertificateInfo:
    """A single certificate in the chain."""
    subject: str
    issuer: str
    not_before: Optional[datetime] = None
    not_after: Optional[datetime] = None
    serial_number: Optional[str] = None
    is_expired: bool = False
    days_until_expiry: Optional[int] = None


@dataclass
class TLSResult:
    """Result of inspecting the TLS handshake for one host."""
    hostname: str
    tls_version: str = ""
    cipher_suite: str = ""
    cipher_bits: Optional[int] = None
    certificate_chain: list[CertificateInfo] = field(default_factory=list)
    handshake_time_ms: float = 0.0
    error: Optional[str] = None

    @property
    def leaf_certificate(self) -> Optional[CertificateInfo]:
        return self.certificate_chain[0] if self.certificate_chain else None


@dataclass
class HTTPExchangeResult:
    """Pairs a request with its response, plus TLS info, for one URL fetch."""
    request: HTTPRequestRecord
    response: Optional[HTTPResponseRecord] = None
    tls: Optional[TLSResult] = None
    error: Optional[str] = None
    total_time_ms: float = 0.0


@dataclass
class ResourceTiming:
    """Real timing breakdown for fetching one page resource."""
    dns_ms: float = 0.0
    connect_ms: float = 0.0
    tls_ms: float = 0.0
    ttfb_ms: float = 0.0          # time to first byte after connection established
    download_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class DOMMetrics:
    """
    Real, measured structural complexity of the page's actual HTML — element
    count, nesting depth, script/style tag counts. Computed once during the
    real page fetch (BeautifulSoup already parses the document to find
    resource links; this captures structural facts from that same real
    parse) so later illustrative modules (rendering pipeline, JS execution)
    can scale their simulated stage durations to the real page's actual
    complexity instead of using arbitrary fixed numbers.
    """
    element_count: int = 0
    max_depth: int = 0
    script_tag_count: int = 0
    inline_script_count: int = 0
    style_tag_count: int = 0
    text_node_count: int = 0


@dataclass
class PageResource:
    """One resource discovered in the page (CSS, JS, image, font, etc.)."""
    url: str
    resource_type: str            # "html", "css", "javascript", "image", "font", "other"
    discovered_from: str = "html" # what referenced it: "html", "css", or a parent resource URL
    status_code: Optional[int] = None
    size_bytes: int = 0
    content_type: str = ""
    timing: ResourceTiming = field(default_factory=ResourceTiming)
    start_offset_ms: float = 0.0  # when this fetch started, relative to page load start
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.status_code is not None and self.status_code < 400


@dataclass
class PageLoadResult:
    """
    Full result of loading a page and its dependent resources — the shared
    data source for both the Waterfall Timeline and the Resource Dependency
    Graph, since they're two views onto the same real fetch.
    """
    page_url: str
    resources: list[PageResource] = field(default_factory=list)
    total_time_ms: float = 0.0
    error: Optional[str] = None
    dom_metrics: Optional[DOMMetrics] = None

    @property
    def total_bytes(self) -> int:
        return sum(r.size_bytes for r in self.resources)

    def resources_of_type(self, resource_type: str) -> list[PageResource]:
        return [r for r in self.resources if r.resource_type == resource_type]

    def type_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.resources:
            counts[r.resource_type] = counts.get(r.resource_type, 0) + 1
        return counts


@dataclass
class CookieRecord:
    """One real cookie parsed from a Set-Cookie response header."""
    name: str
    value: str
    domain: Optional[str] = None
    path: Optional[str] = None
    expires: Optional[datetime] = None
    max_age: Optional[int] = None
    secure: bool = False
    http_only: bool = False
    same_site: Optional[str] = None
    raw_header: str = ""

    @property
    def is_session_cookie(self) -> bool:
        """A cookie with no Expires/Max-Age dies when the browser closes."""
        return self.expires is None and self.max_age is None


@dataclass
class CompressionAnalysis:
    """Real compression comparison for one HTTP response body."""
    algorithm: Optional[str]          # "gzip", "br", "deflate", or None
    compressed_size_bytes: Optional[int]
    decompressed_size_bytes: int
    content_type: str = ""

    @property
    def is_compressed(self) -> bool:
        return self.algorithm is not None and self.compressed_size_bytes is not None

    @property
    def bytes_saved(self) -> int:
        if not self.is_compressed:
            return 0
        return self.decompressed_size_bytes - self.compressed_size_bytes

    @property
    def compression_ratio_pct(self) -> Optional[float]:
        """Percent of original size saved by compression. None if not compressed."""
        if not self.is_compressed or self.decompressed_size_bytes == 0:
            return None
        return (self.bytes_saved / self.decompressed_size_bytes) * 100


@dataclass
class SecurityCheck:
    """One real, evaluated security finding (a header present/absent/weak)."""
    name: str
    passed: bool
    severity: str            # "good", "warning", "critical"
    detail: str
    header_value: Optional[str] = None


@dataclass
class SecurityReport:
    """Full real security evaluation for one URL's response + TLS state."""
    url: str
    checks: list[SecurityCheck] = field(default_factory=list)

    @property
    def score(self) -> int:
        """0-100: percentage of checks that passed."""
        if not self.checks:
            return 0
        return round(100 * sum(1 for c in self.checks if c.passed) / len(self.checks))

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed and c.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed and c.severity == "warning")


class DataSource(str, Enum):
    """
    Marks whether a result came from a real OS-level capture/probe or from
    the simulation engine. Phase 5 is the first to need this distinction —
    earlier modules (DNS, HTTP, TLS) only ever produce real results, but
    Packet Explorer and Internet Route Explorer require elevated privileges
    (Npcap, raw sockets/admin) that may not be available, so the UI needs to
    always show plainly which kind of data is on screen.
    """
    REAL = "real"
    SIMULATED = "simulated"


@dataclass
class RouteHop:
    """One hop in a traceroute path."""
    hop_number: int
    ip_address: Optional[str]       # None if this hop timed out / didn't respond
    hostname: Optional[str] = None  # reverse-DNS, if resolved
    rtt_ms: Optional[float] = None  # None if timed out
    city: Optional[str] = None
    country: Optional[str] = None
    is_destination: bool = False
    timed_out: bool = False


@dataclass
class RouteResult:
    """Full real (or simulated) traceroute result to one destination."""
    destination: str
    destination_ip: Optional[str]
    hops: list[RouteHop] = field(default_factory=list)
    source: DataSource = DataSource.REAL
    error: Optional[str] = None
    total_time_ms: float = 0.0

    @property
    def reached_destination(self) -> bool:
        return any(h.is_destination for h in self.hops)


@dataclass
class CapturedPacket:
    """One real (or simulated) network packet captured during a session."""
    packet_number: int
    protocol: str             # "TCP", "UDP", "TLS", "HTTP", "DNS", "ICMP", "ARP", ...
    source: str                # "ip:port" or "ip"
    destination: str
    length_bytes: int
    timestamp_offset_ms: float  # relative to capture start
    summary: str = ""           # one-line human description, e.g. "SYN, seq=0"
    flags: list[str] = field(default_factory=list)  # e.g. ["SYN", "ACK"] for TCP
    detail: str = ""            # multi-line detail view (raw-ish breakdown)


@dataclass
class PacketCaptureResult:
    """Full real (or simulated) packet capture for one exploration session."""
    target: str
    packets: list[CapturedPacket] = field(default_factory=list)
    source: DataSource = DataSource.REAL
    error: Optional[str] = None
    capture_duration_ms: float = 0.0

    def protocol_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self.packets:
            counts[p.protocol] = counts.get(p.protocol, 0) + 1
        return counts


@dataclass
class PrivilegeStatus:
    """What this OS/process can actually do for raw capture and traceroute."""
    can_capture_packets: bool
    can_raw_traceroute: bool
    platform: str
    detail: str = ""


@dataclass
class TCPHandshakeStep:
    """One packet in a TCP three-way handshake."""
    step_number: int          # 1=SYN, 2=SYN-ACK, 3=ACK
    direction: str             # "client_to_server" or "server_to_client"
    flags: list[str] = field(default_factory=list)
    sequence_number: Optional[int] = None
    ack_number: Optional[int] = None
    window_size: Optional[int] = None
    rtt_ms: Optional[float] = None   # time since the previous step


@dataclass
class TCPHandshakeResult:
    """Full real (or simulated) TCP three-way handshake to one host:port."""
    target: str
    port: int
    steps: list[TCPHandshakeStep] = field(default_factory=list)
    source: DataSource = DataSource.REAL
    error: Optional[str] = None
    total_time_ms: float = 0.0

    @property
    def completed(self) -> bool:
        return len(self.steps) == 3


@dataclass
class CDNSignal:
    """One piece of real evidence pointing to (or against) CDN usage."""
    header_name: str
    header_value: str
    indicates_provider: Optional[str] = None


@dataclass
class GeoLocation:
    """Real (or unavailable) geolocation for an IP address."""
    ip: str
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    isp: Optional[str] = None
    asn: Optional[str] = None
    error: Optional[str] = None


@dataclass
class CDNResult:
    """Full real CDN detection result for one URL."""
    url: str
    hostname: str
    resolved_ip: Optional[str] = None
    is_cdn_detected: bool = False
    detected_provider: Optional[str] = None
    confidence: str = "none"          # "high", "medium", "low", "none"
    signals: list[CDNSignal] = field(default_factory=list)
    origin_location: Optional[GeoLocation] = None
    error: Optional[str] = None


@dataclass
class RenderStage:
    """
    One stage of the browser rendering pipeline (DOM construction, CSSOM
    construction, Render Tree, Layout, Paint, Composite). Durations are
    ALWAYS illustrative — no real browser engine is instrumented — but are
    scaled from the real page's actual measured complexity (DOM size, CSS
    size, resource counts) rather than being arbitrary fixed numbers.
    """
    name: str
    description: str
    duration_ms: float
    start_offset_ms: float


@dataclass
class RenderingPipelineResult:
    """
    Full illustrative rendering pipeline for one real page. Always
    source=DataSource.SIMULATED — there is no real mode for this module,
    since no Python process can instrument an actual browser engine's
    internals. Stage durations are derived from the real DOMMetrics and
    resource sizes already captured by the Page Load job, not arbitrary.
    """
    url: str
    stages: list[RenderStage] = field(default_factory=list)
    total_time_ms: float = 0.0
    dom_metrics: Optional[DOMMetrics] = None
    error: Optional[str] = None


@dataclass
class ScriptExecutionEntry:
    """Real-data-grounded illustrative timing for one JS resource on the page."""
    url: str
    size_bytes: int
    download_ms: float
    parse_ms: float
    execution_ms: float
    is_blocking: bool   # synchronous <script> in <head> with no async/defer
    is_inline: bool = False


@dataclass
class JSExecutionResult:
    """
    Full illustrative JS execution timeline for one real page's actual
    script resources. Always source=DataSource.SIMULATED for the same
    reason as RenderingPipelineResult — durations are scaled from each
    script's real, measured size (and the page's real inline-script count),
    not invented independent of the real page.
    """
    url: str
    scripts: list[ScriptExecutionEntry] = field(default_factory=list)
    total_blocking_time_ms: float = 0.0
    total_time_ms: float = 0.0
    error: Optional[str] = None

    @property
    def blocking_scripts(self) -> list[ScriptExecutionEntry]:
        return [s for s in self.scripts if s.is_blocking]


@dataclass
class ExplorationSession:
    """
    Top-level container for one "Explore" run against a URL.
    Each module attaches its results to the session as it completes.
    """
    url: str
    id: str = field(default_factory=new_id)
    status: SessionStatus = SessionStatus.PENDING
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None

    # Populated incrementally as each phase's module runs.
    dns_result: Optional[DNSResult] = None
    http_exchange: Optional[HTTPExchangeResult] = None
    page_load: Optional[PageLoadResult] = None
    route: Optional[RouteResult] = None
    packet_capture: Optional[PacketCaptureResult] = None
    tcp_handshake: Optional[TCPHandshakeResult] = None
    cdn_result: Optional[CDNResult] = None
    rendering_pipeline: Optional[RenderingPipelineResult] = None
    js_execution: Optional[JSExecutionResult] = None
    # Cookie, Compression, and Security analyses are derived from
    # http_exchange + tls_result rather than making new network calls, so
    # they don't get their own session fields — panels compute them
    # on-the-fly from the data already captured above.

    error_message: Optional[str] = None

    def duration_ms(self) -> Optional[float]:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds() * 1000
