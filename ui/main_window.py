"""
UI Layer — Main Window.

Wires together the sidebar, the URL workspace top bar, and the module
content area (a QStackedWidget swapped by sidebar selection).

A single "Explore" action fans out to seven independent jobs — DNS, HTTP,
TLS, Page Load, Route (traceroute), Packet Capture, and TCP Handshake —
which all run concurrently on their own background threads. Each module
panel updates as soon as its own result arrives, and the top status pill
reflects the combined state of all jobs so the user always has one honest
read of "is everything done, and did it work". CDN detection isn't its own
job — it's derived from the DNS and HTTP results already fetched.

Route, Packet Capture, and TCP Handshake are the jobs with a Real/Simulation
mode choice, since they need OS-level privileges (raw sockets, Npcap) that
may not be available. A one-time privilege check runs at startup; its
result sets each panel's default mode and disables "Real" if it genuinely
isn't available, while always leaving Simulation mode usable as a
legitimate demo mode in its own right — never a silently degraded fallback.

Phase 9 adds two standalone interactive modules:
  - Protocol Comparison Lab (Module 17): always shows data, enriched by
    the real PageLoadResult when an exploration completes.
  - Failure Simulation Lab (Module 18): lets the user pick failure scenarios
    and see animated stage timelines, calibrated to the real page's baseline
    timing when available.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from data.models import (
    DNSResult,
    ExplorationSession,
    HTTPExchangeResult,
    PacketCaptureResult,
    PageLoadResult,
    PrivilegeStatus,
    RouteResult,
    SessionStatus,
    TCPHandshakeResult,
    TLSResult,
)
from protocols.cdn_protocol import detect_cdn
from protocols.js_execution_protocol import simulate_js_execution
from protocols.rendering_pipeline_protocol import simulate_rendering_pipeline
from protocols.storage_protocol import save_session
from services.dns_service import DNSService
from services.http_service import HTTPService
from services.packet_service import PacketService
from services.page_load_service import PageLoadService
from services.privilege_service import PrivilegeService
from services.route_service import RouteService
from services.tcp_handshake_service import TCPHandshakeService
from services.tls_service import TLSService
from services.url_service import InvalidURLError, parse_url
from ui.cdn_panel import CDNExplorerPanel
from ui.compression_panel import CompressionAnalyzerPanel
from ui.cookie_panel import CookieExplorerPanel
from ui.dns_panel import DNSExplorerPanel
from ui.http_request_panel import HTTPRequestPanel
from ui.http_response_panel import HTTPResponsePanel
from ui.js_execution_panel import JSExecutionPanel
from ui.packet_panel import PacketExplorerPanel
from ui.rendering_pipeline_panel import RenderingPipelinePanel
from ui.resource_dependency_panel import ResourceDependencyPanel
from ui.route_panel import RouteExplorerPanel
from ui.security_panel import SecurityInspectorPanel
from ui.failure_simulation_panel import FailureSimulationPanel
from ui.protocol_comparison_panel import ProtocolComparisonPanel
from ui.session_panel import SessionRecordingPanel
from ui.sidebar import Sidebar
from ui.tcp_handshake_panel import TCPHandshakePanel
from ui.tls_panel import TLSExplorerPanel
from ui.url_bar import URLBar
from ui.waterfall_panel import WaterfallPanel
from ui.widgets import EmptyState

# The independent jobs kicked off by one Explore click. Used to track
# combined completion/failure state for the top status pill. CDN detection
# is intentionally absent — it's derived from dns/http results, not its own job.
_JOBS = ("dns", "http", "tls", "page_load", "route", "packets", "tcp_handshake")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("The Internet Explorer")
        self.resize(1280, 820)
        self.setMinimumSize(1024, 640)

        self._dns_service = DNSService(self)
        self._dns_service.lookup_started.connect(self._on_dns_started)
        self._dns_service.result_ready.connect(self._on_dns_result)
        self._dns_service.error.connect(self._on_dns_error)

        self._http_service = HTTPService(self)
        self._http_service.fetch_started.connect(self._on_http_started)
        self._http_service.result_ready.connect(self._on_http_result)
        self._http_service.error.connect(self._on_http_error)

        self._tls_service = TLSService(self)
        self._tls_service.inspect_started.connect(self._on_tls_started)
        self._tls_service.result_ready.connect(self._on_tls_result)
        self._tls_service.error.connect(self._on_tls_error)

        self._page_load_service = PageLoadService(self)
        self._page_load_service.load_started.connect(self._on_page_load_started)
        self._page_load_service.result_ready.connect(self._on_page_load_result)
        self._page_load_service.error.connect(self._on_page_load_error)

        self._route_service = RouteService(self)
        self._route_service.trace_started.connect(self._on_route_started)
        self._route_service.result_ready.connect(self._on_route_result)
        self._route_service.error.connect(self._on_route_error)

        self._packet_service = PacketService(self)
        self._packet_service.capture_started.connect(self._on_packet_started)
        self._packet_service.result_ready.connect(self._on_packet_result)
        self._packet_service.error.connect(self._on_packet_error)

        self._tcp_handshake_service = TCPHandshakeService(self)
        self._tcp_handshake_service.capture_started.connect(self._on_tcp_handshake_started)
        self._tcp_handshake_service.result_ready.connect(self._on_tcp_handshake_result)
        self._tcp_handshake_service.error.connect(self._on_tcp_handshake_error)

        self._privilege_service = PrivilegeService(self)
        self._privilege_service.result_ready.connect(self._on_privilege_result)

        self._current_session: ExplorationSession | None = None
        # Tracks per-job completion for this exploration run, so the status
        # pill can report "all done" only once every job finishes,
        # regardless of which one happens to finish last.
        self._job_done: dict[str, bool] = {job: True for job in _JOBS}
        self._job_failed: dict[str, str | None] = {job: None for job in _JOBS}

        self._build_ui()

        # Kick off the one-time privilege check immediately so Route/Packet
        # panels know which mode to default to before the user ever opens
        # them or clicks Explore.
        self._privilege_service.check()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.module_selected.connect(self._on_module_selected)
        outer.addWidget(self.sidebar)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        outer.addWidget(right, stretch=1)

        self.url_bar = URLBar()
        self.url_bar.explore_requested.connect(self._on_explore_requested)
        right_layout.addWidget(self.url_bar)

        self.stack = QStackedWidget()
        right_layout.addWidget(self.stack, stretch=1)

        self._build_module_panels()

    def _build_module_panels(self) -> None:
        self._panel_index: dict[str, int] = {}

        # Landing / URL workspace view — shown before any exploration runs.
        self.landing_panel = EmptyState(
            "Welcome to The Internet Explorer.\n\n"
            "Enter a URL above and click Explore to watch DNS, HTTP, TLS, and the page's "
            "real resource loading happen at once.\n"
            "Each sidebar module lights up as its phase of development lands."
        )
        self._add_panel("url_workspace", self.landing_panel)

        self.dns_panel = DNSExplorerPanel()
        self._add_panel("dns", self.dns_panel)

        self.tls_panel = TLSExplorerPanel()
        self._add_panel("tls", self.tls_panel)

        self.http_request_panel = HTTPRequestPanel()
        self._add_panel("http_request", self.http_request_panel)

        self.http_response_panel = HTTPResponsePanel()
        self._add_panel("http_response", self.http_response_panel)

        self.resource_graph_panel = ResourceDependencyPanel()
        self._add_panel("resource_graph", self.resource_graph_panel)

        self.waterfall_panel = WaterfallPanel()
        self._add_panel("waterfall", self.waterfall_panel)

        self.cookie_panel = CookieExplorerPanel()
        self._add_panel("cookies", self.cookie_panel)

        self.compression_panel = CompressionAnalyzerPanel()
        self._add_panel("compression", self.compression_panel)

        self.security_panel = SecurityInspectorPanel()
        self._add_panel("security", self.security_panel)

        self.route_panel = RouteExplorerPanel()
        self._add_panel("route", self.route_panel)

        self.packet_panel = PacketExplorerPanel()
        self._add_panel("packets", self.packet_panel)

        self.tcp_handshake_panel = TCPHandshakePanel()
        self._add_panel("tcp", self.tcp_handshake_panel)

        self.cdn_panel = CDNExplorerPanel()
        self._add_panel("cdn", self.cdn_panel)

        self.rendering_pipeline_panel = RenderingPipelinePanel()
        self._add_panel("rendering", self.rendering_pipeline_panel)

        self.js_execution_panel = JSExecutionPanel()
        self._add_panel("js_execution", self.js_execution_panel)

        self.session_panel = SessionRecordingPanel()
        self.session_panel.replay_requested.connect(self._on_replay_session)
        self._add_panel("sessions", self.session_panel)

        # Phase 9: Protocol Comparison Lab (Module 17) — always shows data,
        # enriched by the real PageLoadResult after a successful exploration.
        self.protocol_comparison_panel = ProtocolComparisonPanel()
        self._add_panel("protocol_comparison", self.protocol_comparison_panel)

        # Phase 9: Failure Simulation Lab (Module 18) — interactive standalone;
        # uses real page baseline timing when a PageLoadResult is available.
        self.failure_simulation_panel = FailureSimulationPanel()
        self._add_panel("failure_sim", self.failure_simulation_panel)

        self.sidebar.select_module("url_workspace")

    def _add_panel(self, key: str, widget: QWidget) -> None:
        index = self.stack.addWidget(widget)
        self._panel_index[key] = index

    # ------------------------------------------------------------------
    # Explore orchestration
    # ------------------------------------------------------------------
    def _on_module_selected(self, key: str) -> None:
        index = self._panel_index.get(key)
        if index is not None:
            self.stack.setCurrentIndex(index)

    def _on_explore_requested(self, raw_url: str) -> None:
        try:
            parsed = parse_url(raw_url)
        except InvalidURLError as exc:
            self.url_bar.set_status(SessionStatus.FAILED, str(exc))
            return

        self._current_session = ExplorationSession(url=parsed.original)
        self._current_session.status = SessionStatus.RUNNING

        self._job_done = {job: False for job in _JOBS}
        self._job_failed = {job: None for job in _JOBS}

        self.url_bar.set_status(SessionStatus.RUNNING, "DNS, HTTP, TLS, resources")
        self.url_bar.set_busy(True)

        # Jump to the DNS module so the user immediately sees progress —
        # it's typically the fastest job, so it lands first.
        self.sidebar.select_module("dns")
        self.dns_panel.show_loading(parsed.hostname)
        self.tls_panel.show_loading(parsed.hostname)
        self.http_request_panel.show_loading(parsed.original)
        self.http_response_panel.show_loading(parsed.original)
        self.resource_graph_panel.show_loading(parsed.original)
        self.waterfall_panel.show_loading(parsed.original)
        self.cookie_panel.show_loading(parsed.original)
        self.compression_panel.show_loading(parsed.original)
        self.security_panel.show_loading(parsed.original)

        route_use_real = self.route_panel.mode_toggle._buttons["real"].isChecked()
        packets_use_real = self.packet_panel.mode_toggle._buttons["real"].isChecked()
        tcp_use_real = self.tcp_handshake_panel.mode_toggle._buttons["real"].isChecked()
        self.route_panel.show_loading(parsed.hostname, route_use_real)
        self.packet_panel.show_loading(parsed.hostname, packets_use_real)
        self.tcp_handshake_panel.show_loading(parsed.hostname, tcp_use_real)
        self.cdn_panel.show_loading(parsed.original)
        self.rendering_pipeline_panel.show_loading(parsed.original)
        self.js_execution_panel.show_loading(parsed.original)

        self._dns_service.lookup(parsed.hostname)
        self._http_service.fetch(parsed.original)
        self._page_load_service.load(parsed.original)
        self._route_service.trace(parsed.hostname, use_real=route_use_real)
        self._packet_service.capture(parsed.hostname, use_real=packets_use_real)
        self._tcp_handshake_service.capture(parsed.hostname, parsed.port, use_real=tcp_use_real)
        # Only inspect TLS for https URLs — there's no handshake to show for plain http.
        if parsed.is_https:
            self._tls_service.inspect(parsed.hostname, port=parsed.port)
        else:
            self._job_done["tls"] = True
            self.tls_panel.show_not_applicable(
                parsed.hostname,
                "This URL uses plain HTTP, so there's no TLS handshake to inspect. "
                "Try an https:// URL to see this module in action.",
            )
            self._check_all_done()

    def _check_all_done(self) -> None:
        if self._current_session is None:
            return
        if not all(self._job_done.values()):
            return

        self.url_bar.set_busy(False)

        failures = {job: msg for job, msg in self._job_failed.items() if msg}
        if failures:
            self._current_session.status = SessionStatus.FAILED
            # Surface the first failure in the pill; all are visible in their own panels.
            first_job, first_msg = next(iter(failures.items()))
            self._current_session.error_message = first_msg
            self.url_bar.set_status(SessionStatus.FAILED, f"{first_job.upper()}: {first_msg}")
        else:
            self._current_session.status = SessionStatus.COMPLETE
            self.url_bar.set_status(SessionStatus.COMPLETE, "All modules succeeded")

        # Let the session panel know a completed session is ready to save.
        self.session_panel.set_current_session(self._current_session)

    # ------------------------------------------------------------------
    # Session replay (load saved session and restore all panels)
    # ------------------------------------------------------------------
    def _on_replay_session(self, session: ExplorationSession) -> None:
        """
        Restore every module panel to the state it was in when the session
        was originally saved — no network calls, instant replay.
        """
        self._current_session = session

        # Update URL bar to reflect the replayed session
        self.url_bar.input.setText(session.url)
        self.url_bar.set_busy(False)
        self.url_bar.set_status(session.status, "Replayed from saved session")

        # DNS
        if session.dns_result:
            self.dns_panel.show_result(session.dns_result)

        # HTTP
        if session.http_exchange:
            self.http_request_panel.show_request(session.http_exchange.request)
            self.http_response_panel.show_exchange(session.http_exchange)
            self.cookie_panel.show_exchange(session.http_exchange)
            self.compression_panel.show_exchange(session.http_exchange)

        # TLS
        if session.dns_result:
            tls_result = getattr(session, 'tls_result', None)
            if tls_result:
                self.tls_panel.show_result(tls_result)
                self.security_panel.set_tls_result(tls_result)

        # HTTP drives security (may render without TLS too)
        if session.http_exchange:
            self.security_panel.set_http_exchange(session.http_exchange)

        # Page load
        if session.page_load:
            self.resource_graph_panel.show_result(session.page_load)
            self.waterfall_panel.show_result(session.page_load)
            if session.rendering_pipeline:
                self.rendering_pipeline_panel.show_result(session.rendering_pipeline)
            if session.js_execution:
                self.js_execution_panel.show_result(session.js_execution)

        # Route
        if session.route:
            self.route_panel.show_result(session.route)

        # Packets
        if session.packet_capture:
            self.packet_panel.show_result(session.packet_capture)

        # TCP Handshake
        if session.tcp_handshake:
            self.tcp_handshake_panel.show_result(session.tcp_handshake)

        # CDN
        if session.cdn_result:
            self.cdn_panel.show_result(session.cdn_result)

        # Navigate to DNS panel to show the replay is live
        self.sidebar.select_module("dns")
    def _on_dns_started(self, domain: str) -> None:
        self.dns_panel.show_loading(domain)

    def _on_dns_result(self, result: DNSResult) -> None:
        self.dns_panel.show_result(result)

        # A DNS lookup that returns zero records (e.g. NXDOMAIN) mechanically
        # "completed" without an exception, but it's not a success the user
        # should read as green — treat it as this job's failure.
        if not result.records and result.errors:
            first_error = next(iter(result.errors.values()))
            if self._current_session is not None:
                self._current_session.dns_result = result
            self._job_failed["dns"] = first_error
        else:
            if self._current_session is not None:
                self._current_session.dns_result = result

        self._job_done["dns"] = True
        self._maybe_run_cdn_detection()
        self._check_all_done()

    def _on_dns_error(self, message: str) -> None:
        self.dns_panel.show_error(message)
        self._job_done["dns"] = True
        self._job_failed["dns"] = message
        self._check_all_done()

    # ------------------------------------------------------------------
    # HTTP job
    # ------------------------------------------------------------------
    def _on_http_started(self, url: str) -> None:
        self.http_request_panel.show_loading(url)
        self.http_response_panel.show_loading(url)

    def _on_http_result(self, result: HTTPExchangeResult) -> None:
        self.http_request_panel.show_request(result.request)
        self.http_response_panel.show_exchange(result)
        self.cookie_panel.show_exchange(result)
        self.compression_panel.show_exchange(result)
        self.security_panel.set_http_exchange(result)

        if self._current_session is not None:
            self._current_session.http_exchange = result

        if result.error or result.response is None:
            self._job_failed["http"] = result.error or "No response received."

        self._job_done["http"] = True
        self._maybe_run_cdn_detection()
        self._check_all_done()

    def _on_http_error(self, message: str) -> None:
        self.http_request_panel.show_error(message)
        self.http_response_panel.show_error(message)
        self.cookie_panel.show_error(message)
        self.compression_panel.show_error(message)
        self.security_panel.show_error(message)
        self._job_done["http"] = True
        self._job_failed["http"] = message
        self._check_all_done()

    # ------------------------------------------------------------------
    # TLS job
    # ------------------------------------------------------------------
    def _on_tls_started(self, hostname: str) -> None:
        self.tls_panel.show_loading(hostname)

    def _on_tls_result(self, result: TLSResult) -> None:
        self.tls_panel.show_result(result)
        self.security_panel.set_tls_result(result)
        if result.error:
            self._job_failed["tls"] = result.error
        self._job_done["tls"] = True
        self._check_all_done()

    def _on_tls_error(self, message: str) -> None:
        hostname = ""
        if self._current_session is not None:
            try:
                hostname = parse_url(self._current_session.url).hostname
            except InvalidURLError:
                hostname = self._current_session.url
        self.tls_panel.show_error(hostname, message)
        self._job_done["tls"] = True
        self._job_failed["tls"] = message
        self._check_all_done()

    # ------------------------------------------------------------------
    # Page Load job (Waterfall + Resource Dependency Graph)
    # ------------------------------------------------------------------
    def _on_page_load_started(self, url: str) -> None:
        self.resource_graph_panel.show_loading(url)
        self.waterfall_panel.show_loading(url)

    def _on_page_load_result(self, result: PageLoadResult) -> None:
        self.resource_graph_panel.show_result(result)
        self.waterfall_panel.show_result(result)

        if self._current_session is not None:
            self._current_session.page_load = result

        if result.error:
            self._job_failed["page_load"] = result.error

        # Rendering pipeline and JS execution are derived from page_load.
        # They always produce results (even on error, they show an error
        # state), so they never block the job-done tracking.
        try:
            pipeline = simulate_rendering_pipeline(result)
            self.rendering_pipeline_panel.show_result(pipeline)
            if self._current_session is not None:
                self._current_session.rendering_pipeline = pipeline
        except Exception as exc:  # noqa: BLE001
            self.rendering_pipeline_panel.show_error(str(exc))

        try:
            js_exec = simulate_js_execution(result)
            self.js_execution_panel.show_result(js_exec)
            if self._current_session is not None:
                self._current_session.js_execution = js_exec
        except Exception as exc:  # noqa: BLE001
            self.js_execution_panel.show_error(str(exc))

        # Phase 9: Protocol Comparison Lab — refresh timing estimates using
        # the real page's resource count and total size. Never blocks job tracking.
        try:
            self.protocol_comparison_panel.show_result(result)
        except Exception:  # noqa: BLE001
            pass

        # Phase 9: Failure Simulation Lab — update baseline timing so the
        # degraded scenarios are calibrated against the real page's load time.
        try:
            self.failure_simulation_panel.set_baseline(result)
        except Exception:  # noqa: BLE001
            pass

        self._job_done["page_load"] = True
        self._check_all_done()

    def _on_page_load_error(self, message: str) -> None:
        self.resource_graph_panel.show_error(message)
        self.waterfall_panel.show_error(message)
        self.rendering_pipeline_panel.show_error(message)
        self.js_execution_panel.show_error(message)
        self._job_done["page_load"] = True
        self._job_failed["page_load"] = message
        self._check_all_done()

    # ------------------------------------------------------------------
    # Route job (Internet Route Explorer, real or simulated)
    # ------------------------------------------------------------------
    def _on_route_started(self, destination: str) -> None:
        pass  # show_loading was already called synchronously in _on_explore_requested

    def _on_route_result(self, result: RouteResult) -> None:
        self.route_panel.show_result(result)
        if self._current_session is not None:
            self._current_session.route = result
        # A traceroute that ran without error but never reached the
        # destination is still genuinely useful information (e.g. a
        # firewall silently drops the final hops) — not treated as a job
        # failure, since the panel already shows this honestly.
        if result.error:
            self._job_failed["route"] = result.error
        self._job_done["route"] = True
        self._check_all_done()

    def _on_route_error(self, message: str) -> None:
        self.route_panel.show_error(message)
        self._job_done["route"] = True
        self._job_failed["route"] = message
        self._check_all_done()

    # ------------------------------------------------------------------
    # Packet job (Packet Explorer, real or simulated)
    # ------------------------------------------------------------------
    def _on_packet_started(self, target: str) -> None:
        pass  # show_loading was already called synchronously in _on_explore_requested

    def _on_packet_result(self, result: PacketCaptureResult) -> None:
        self.packet_panel.show_result(result)
        if self._current_session is not None:
            self._current_session.packet_capture = result
        if result.error:
            self._job_failed["packets"] = result.error
        self._job_done["packets"] = True
        self._check_all_done()

    def _on_packet_error(self, message: str) -> None:
        self.packet_panel.show_error(message)
        self._job_done["packets"] = True
        self._job_failed["packets"] = message
        self._check_all_done()

    # ------------------------------------------------------------------
    # TCP Handshake job (real or simulated)
    # ------------------------------------------------------------------
    def _on_tcp_handshake_started(self, target: str) -> None:
        pass  # show_loading was already called synchronously in _on_explore_requested

    def _on_tcp_handshake_result(self, result: TCPHandshakeResult) -> None:
        self.tcp_handshake_panel.show_result(result)
        if self._current_session is not None:
            self._current_session.tcp_handshake = result
        # An incomplete handshake (fewer than 3 steps captured) is reported
        # honestly in the panel already via result.error, but still treated
        # as this job's failure for the top-level status pill, since a
        # partial handshake genuinely isn't a successful exploration of it.
        if result.error:
            self._job_failed["tcp_handshake"] = result.error
        self._job_done["tcp_handshake"] = True
        self._check_all_done()

    def _on_tcp_handshake_error(self, message: str) -> None:
        self.tcp_handshake_panel.show_error(message)
        self._job_done["tcp_handshake"] = True
        self._job_failed["tcp_handshake"] = message
        self._check_all_done()

    # ------------------------------------------------------------------
    # CDN detection (derived from DNS + HTTP results, not its own job)
    # ------------------------------------------------------------------
    def _maybe_run_cdn_detection(self) -> None:
        session = self._current_session
        if session is None:
            return
        # Wait until both jobs have actually finished (not just whether
        # they produced usable data) before deciding anything — runs once
        # both are in, regardless of which one happened to finish first.
        if not self._job_done["dns"] or not self._job_done["http"]:
            return

        a_records = session.dns_result.records_of_type("A") if session.dns_result else []
        resolved_ip = a_records[0].value if a_records else None
        response = session.http_exchange.response if session.http_exchange else None

        # If neither a resolved IP nor a real response made it through,
        # there's no real signal to evaluate — show this as "couldn't
        # check" rather than a confident-looking "No CDN Detected", which
        # would otherwise look identical to a genuine negative result.
        if resolved_ip is None and response is None:
            self.cdn_panel.show_error(
                "Couldn't check for a CDN because both DNS resolution and the HTTP request "
                "failed for this host — see the DNS Explorer and HTTP Response Inspector for details."
            )
            return

        try:
            hostname = parse_url(session.url).hostname
        except InvalidURLError:
            hostname = session.dns_result.domain if session.dns_result else session.url

        result = detect_cdn(session.url, hostname, resolved_ip, response)
        session.cdn_result = result
        self.cdn_panel.show_result(result)

    # ------------------------------------------------------------------
    # Privilege check (runs once at startup)
    # ------------------------------------------------------------------
    def _on_privilege_result(self, status: PrivilegeStatus) -> None:
        self.route_panel.set_privilege_status(status)
        self.packet_panel.set_privilege_status(status)
        self.tcp_handshake_panel.set_privilege_status(status)
