"""
Protocol Layer — Real TCP handshake capture (TCP Handshake Visualizer, real mode).

Captures the genuine SYN / SYN-ACK / ACK exchange for a real TCP connection:
a background sniff (scapy) is started just before a real socket.connect()
is performed, so the actual three-way handshake packets are observed with
their real sequence numbers, ACK numbers, and timing — not reconstructed or
guessed.

Needs the same privileges as Packet Explorer — Npcap on Windows (plus
Administrator), or root on Linux/Mac. Use
protocols.privilege_protocol.detect_privileges() to check first.
"""
from __future__ import annotations

import socket
import threading
import time

from data.models import DataSource, TCPHandshakeResult, TCPHandshakeStep

CONNECT_TIMEOUT = 5.0
SNIFF_TIMEOUT = 6.0
# Give the sniffer a moment to actually start listening before we connect —
# without this, the real SYN can be sent before the capture is live and
# missed entirely (this is the same race condition discovered and handled
# in Phase 5's packet capture).
SNIFF_WARMUP_SECONDS = 0.4


def _flags_to_list(flags) -> list[str]:
    flag_map = {"S": "SYN", "A": "ACK", "F": "FIN", "R": "RST", "P": "PSH", "U": "URG"}
    return [name for letter, name in flag_map.items() if letter in str(flags)]


def capture_tcp_handshake(target: str, port: int = 443) -> TCPHandshakeResult:
    """
    Open a real TCP connection to target:port and capture the genuine
    three-way handshake via a concurrent scapy sniff.
    """
    try:
        from scapy.all import IP, TCP, sniff
    except ImportError:
        return TCPHandshakeResult(
            target=target, port=port, source=DataSource.REAL,
            error="The 'scapy' package isn't installed. Run: pip install scapy",
        )

    try:
        target_ip = socket.gethostbyname(target)
    except socket.gaierror as exc:
        return TCPHandshakeResult(
            target=target, port=port, source=DataSource.REAL,
            error=f"Could not resolve {target}: {exc}",
        )

    captured: list = []
    sniff_started = threading.Event()
    handshake_complete = threading.Event()

    def _is_handshake_ack(pkt) -> bool:
        """Stop condition: we've seen a pure ACK (no PSH) from the client side, the 3rd handshake step."""
        if not (pkt.haslayer(IP) and pkt.haslayer(TCP)):
            return False
        flags = _flags_to_list(pkt[TCP].flags)
        is_client_to_server = pkt[IP].dst == target_ip
        if flags == ["ACK"] and is_client_to_server:
            handshake_complete.set()
            return True
        return False

    def do_sniff():
        sniff_started.set()
        pkts = sniff(
            filter=f"host {target_ip} and tcp port {port}",
            timeout=SNIFF_TIMEOUT,
            stop_filter=_is_handshake_ack,
        )
        captured.extend(pkts)

    sniff_thread = threading.Thread(target=do_sniff, daemon=True)

    start = time.perf_counter()

    try:
        sniff_thread.start()
        sniff_started.wait(timeout=2.0)
        time.sleep(SNIFF_WARMUP_SECONDS)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        try:
            sock.connect((target_ip, port))
        except (socket.timeout, OSError) as exc:
            return TCPHandshakeResult(
                target=target, port=port, source=DataSource.REAL,
                error=f"Could not connect to {target}:{port}: {exc}",
            )
        finally:
            sock.close()

        # The stop_filter above ends the sniff as soon as the handshake's
        # 3rd packet is seen, so this join only blocks for the (short)
        # remaining handshake time — not the full SNIFF_TIMEOUT — except in
        # the unusual case where the handshake never completes, where the
        # timeout is the correct bound anyway.
        sniff_thread.join(timeout=SNIFF_TIMEOUT + 1.0)

    except PermissionError:
        return TCPHandshakeResult(
            target=target, port=port, source=DataSource.REAL,
            error="Packet capture requires elevated privileges (Administrator on Windows, "
                  "root on Linux/Mac).",
        )
    except Exception as exc:  # noqa: BLE001 - scapy/capture-backend errors vary by platform
        return TCPHandshakeResult(
            target=target, port=port, source=DataSource.REAL,
            error=f"Capture failed: {exc}. On Windows, make sure Npcap "
                  f"(https://npcap.com/) is installed and the app is run as Administrator.",
        )

    # Identify our own connection's handshake among whatever was captured —
    # filter to pure SYN/SYN-ACK/ACK packets (no payload) involving our
    # target, in the order they were seen, and take the first 3 (the
    # handshake itself; later packets are the request/response data).
    steps: list[TCPHandshakeStep] = []
    last_time: float | None = None
    first_packet_time: float | None = None
    last_packet_time: float | None = None

    for pkt in captured:
        if not (pkt.haslayer(IP) and pkt.haslayer(TCP)):
            continue
        tcp = pkt[TCP]
        flags = _flags_to_list(tcp.flags)
        if not flags:
            continue
        if "PSH" in flags:
            # Application data riding on the ACK — past the handshake.
            break

        is_client_to_server = pkt[IP].dst == target_ip
        pkt_time = float(pkt.time)
        rtt_ms = (pkt_time - last_time) * 1000 if last_time is not None else None
        last_time = pkt_time
        if first_packet_time is None:
            first_packet_time = pkt_time
        last_packet_time = pkt_time

        steps.append(TCPHandshakeStep(
            step_number=len(steps) + 1,
            direction="client_to_server" if is_client_to_server else "server_to_client",
            flags=flags,
            sequence_number=int(tcp.seq),
            ack_number=int(tcp.ack),
            window_size=int(tcp.window) if hasattr(tcp, "window") else None,
            rtt_ms=rtt_ms,
        ))

        if len(steps) >= 3:
            break

    # The handshake's own duration (first SYN to final ACK), measured from
    # real packet timestamps — not wall-clock time for this whole function,
    # which would also include the sniff-warmup delay and connect() setup.
    if first_packet_time is not None and last_packet_time is not None:
        total_time_ms = (last_packet_time - first_packet_time) * 1000
    else:
        total_time_ms = (time.perf_counter() - start) * 1000

    if len(steps) < 3:
        return TCPHandshakeResult(
            target=target, port=port, source=DataSource.REAL,
            steps=steps,
            total_time_ms=total_time_ms,
            error=(
                f"Only captured {len(steps)} of 3 handshake packets — the capture window "
                f"may have started just after the handshake completed. Try again, or "
                f"switch to Simulation mode."
            ),
        )

    return TCPHandshakeResult(
        target=target,
        port=port,
        steps=steps,
        source=DataSource.REAL,
        total_time_ms=total_time_ms,
    )
