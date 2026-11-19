# Build Roadmap

Each phase ships a fully runnable app — not stubs. The sidebar in the app
always shows all 19 modules from the spec, with a "Phase N" tag on anything
not yet built, so the full scope stays visible throughout development.

| Phase | Status | Delivers |
|---|---|---|
| **1** | ✅ Done | App shell (sidebar, URL bar, theming) · **URL Exploration Workspace** · **DNS Explorer** (live A/AAAA/CNAME/MX/NS/TXT lookups, resolution flow diagram, query timing) |
| **2** | ✅ Done | **HTTP Request Inspector** & **HTTP Response Inspector** (real requests via `httpx`, headers/body/cookies, raw + parsed views) · **TLS Handshake Explorer** (real cert chain, cipher suite, TLS version via `ssl`) — all three now run concurrently from one Explore click |
| **3** | ✅ Done | **Network Waterfall Timeline** (real concurrent resource fetch timing, custom-painted Chrome-DevTools-style chart) · **Resource Dependency Analyzer** (real HTML parsed via BeautifulSoup for actual CSS/JS/image/font dependencies, radial dependency graph + per-type tables) |
| **4** | ✅ Done | **Cookie Explorer** (real Set-Cookie parsing with plain-language attribute explanations) · **Compression Analyzer** (real wire-vs-decompressed size comparison via httpx's num_bytes_downloaded) · **Security Inspector** (real TLS + header evaluation against OWASP/MDN best practices, with a 0–100 score) |
| **5** | ✅ Done | **Packet Explorer** (real capture via scapy/Npcap, or realistic simulation, with protocol filtering and per-packet detail) · **Internet Route Explorer** (real traceroute via raw ICMP, or realistic simulation) — both with a Real/Simulation toggle and automatic privilege detection |
| **6** | ✅ Done | **TCP Handshake Visualizer** (real SYN/SYN-ACK/ACK capture via `scapy` sniff + a genuine connection, with real sequence/ack/window numbers, or realistic simulation) · **CDN Explorer** (real provider detection via response headers + published CDN IP ranges, with full evidence shown) |
| **7** | ✅ Done | **Browser Rendering Pipeline** (6 real pipeline stages, durations scaled from the real DOM complexity and CSS volume, ILLUSTRATIVE SIMULATION) · **JavaScript Execution Analyzer** (per-script download/parse/exec from real sizes, blocking classification, inline count from DOMMetrics) |
| **8** | ✅ Done | **Session Recording & Replay** — store a full exploration session and replay any module result without re-fetching |
| **9** | Next | **Protocol Comparison Lab** (HTTP/1.1 vs 2 vs 3) · **Failure Simulation Lab** (latency/packet loss/DNS/TLS failure injection) |
| **10** | Planned | Polish: light mode, dockable panels, advanced/stretch features as time allows |

---

## Privileged features: real + simulated, delivered in Phase 5

Phase 5's Packet Explorer and Internet Route Explorer shipped with **two
real modes**, not a fallback-only simulation, exactly as planned:

1. **Real mode** — uses your actual OS permissions when available.
   - Traceroute (`protocols/route_protocol.py`) sends real ICMP Echo
     Requests with an incrementing TTL via raw sockets — needs
     Administrator on Windows, root on Linux/Mac. It stops early after 5
     consecutive non-responding hops (or a 20-second hard cap) rather than
     burning through all 30 possible hops at full timeout, so a blocked
     path doesn't leave the UI waiting for up to a minute.
   - Packet capture (`protocols/packet_protocol.py`) uses scapy's `sniff()`
     filtered to the resolved target IP — needs
     [Npcap](https://npcap.com/) installed and the app run as Administrator
     on Windows.
   - `protocols/privilege_protocol.py` checks both at startup (opening a
     real raw socket, and asking scapy to enumerate capture interfaces)
     without performing any actual capture, so the UI can default sensibly
     and explain precisely what's missing — see the README's "Enable real
     traceroute and packet capture" section for exact Windows steps.

2. **Simulation mode** — the same UI, tables, and detail views, driven by
   realistic synthetic data through the exact same data models as real
   mode (`RouteResult`/`RouteHop`, `PacketCaptureResult`/`CapturedPacket`).
   Traceroute simulation models realistic RTT growth, real-looking ISP
   hostnames, and occasional non-responding "dark" hops. Packet simulation
   models a complete, accurately-ordered DNS → TCP handshake → TLS
   handshake → HTTP application data → teardown sequence with realistic
   packet sizes. Every result is labeled with a prominent, unmistakable
   `DataSourceBadge` ("● LIVE CAPTURE" vs "◆ SIMULATED DATA") so it's never
   ambiguous which kind of data is on screen. A toggle at the top of each
   module switches modes any time, even after Real mode succeeds.

## Note on the rendering/JS modules (Phase 7)

The Browser Rendering Pipeline and JavaScript Execution Analyzer can't
literally instrument a real browser engine's internals from Python — Chrome,
Firefox, etc. don't expose DOM/CSSOM construction or paint/composite timing
to an external process in the way this spec implies. Phase 7 will build
these as accurate, well-researched **illustrative simulations**: real stage
names, real ordering, real explanations of what each stage does, timed
against plausible (not fabricated-as-fact) durations. This will be labeled
clearly in the UI so it's never confused with a live trace.
