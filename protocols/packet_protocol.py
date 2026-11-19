"""
Protocol Layer — Real packet capture (Packet Explorer, real mode).

Captures real packets using scapy's sniff(), filtered to traffic involving
the resolved IP of the target host so the capture stays relevant to what
the user is exploring rather than dumping all machine traffic.

Needs Npcap installed on Windows (https://npcap.com/) plus Administrator
privileges; needs root on Linux/Mac. Use
protocols.privilege_protocol.detect_privileges() to check first.
"""
from __future__ import annotations

import socket
import time

from data.models import CapturedPacket, DataSource, PacketCaptureResult

DEFAULT_CAPTURE_DURATION = 8.0
MAX_PACKETS = 200


def _describe_tcp_flags(flags) -> list[str]:
    flag_map = {"S": "SYN", "A": "ACK", "F": "FIN", "R": "RST", "P": "PSH", "U": "URG"}
    return [name for letter, name in flag_map.items() if letter in str(flags)]


def _classify_packet(pkt) -> tuple[str, str, list[str]]:
    """Returns (protocol_label, one_line_summary, flags)."""
    from scapy.all import DNS, TCP, UDP, IP

    if pkt.haslayer(DNS):
        dns_layer = pkt[DNS]
        qr = "response" if dns_layer.qr == 1 else "query"
        qname = ""
        try:
            if dns_layer.qd is not None:
                qname = dns_layer.qd.qname.decode(errors="replace")
        except Exception:  # noqa: BLE001
            pass
        return "DNS", f"DNS {qr}{' for ' + qname if qname else ''}", []

    if pkt.haslayer(TCP):
        tcp = pkt[TCP]
        flags = _describe_tcp_flags(tcp.flags)
        dport = tcp.dport
        sport = tcp.sport
        if dport == 443 or sport == 443:
            label = "TLS"
        elif dport == 80 or sport == 80:
            label = "HTTP"
        else:
            label = "TCP"
        flag_str = "/".join(flags) if flags else "no flags"
        summary = f"{label} {flag_str} seq={tcp.seq} ack={tcp.ack}"
        return label, summary, flags

    if pkt.haslayer(UDP):
        udp = pkt[UDP]
        return "UDP", f"UDP {udp.sport} -> {udp.dport}, len={len(pkt)}", []

    if pkt.haslayer(IP):
        return "IP", f"IP protocol {pkt[IP].proto}", []

    return pkt.lastlayer().name.upper(), pkt.summary(), []


def capture_packets(
    target: str,
    duration: float = DEFAULT_CAPTURE_DURATION,
    max_packets: int = MAX_PACKETS,
) -> PacketCaptureResult:
    """
    Capture real packets to/from `target` for `duration` seconds.

    Raises no exceptions to the caller for expected failure modes (missing
    Npcap, no permission, unresolvable host) — all are returned as
    PacketCaptureResult.error so the service layer can surface them plainly.
    """
    try:
        from scapy.all import sniff
    except ImportError:
        return PacketCaptureResult(
            target=target,
            source=DataSource.REAL,
            error="The 'scapy' package isn't installed. Run: pip install scapy",
        )

    try:
        target_ip = socket.gethostbyname(target)
    except socket.gaierror as exc:
        return PacketCaptureResult(
            target=target,
            source=DataSource.REAL,
            error=f"Could not resolve {target}: {exc}",
        )

    start = time.perf_counter()
    capture_start_wall = time.time()

    bpf_filter = f"host {target_ip}"

    try:
        raw_packets = sniff(filter=bpf_filter, timeout=duration, count=max_packets)
    except PermissionError:
        return PacketCaptureResult(
            target=target,
            source=DataSource.REAL,
            error="Packet capture requires elevated privileges (Administrator on Windows, "
                  "root on Linux/Mac).",
        )
    except Exception as exc:  # noqa: BLE001 - scapy raises its own exception types
        # (Scapy_Exception, ImportError-wrapped-in-OSError, etc.) for "no
        # Npcap/libpcap", "no interface", and similar capture-backend
        # failures. We can't enumerate every one scapy might raise across
        # platforms, so this is a deliberately broad catch — any failure
        # here means "real capture isn't usable right now", which the user
        # can act on via the Npcap install hint either way.
        return PacketCaptureResult(
            target=target,
            source=DataSource.REAL,
            error=f"Packet capture failed: {exc}. On Windows, make sure Npcap "
                  f"(https://npcap.com/) is installed and the app is run as Administrator.",
        )

    captured: list[CapturedPacket] = []
    for i, pkt in enumerate(raw_packets, start=1):
        try:
            from scapy.all import IP as IPLayer
            if pkt.haslayer(IPLayer):
                src = pkt[IPLayer].src
                dst = pkt[IPLayer].dst
            else:
                src = pkt.src if hasattr(pkt, "src") else "?"
                dst = pkt.dst if hasattr(pkt, "dst") else "?"

            protocol, summary, flags = _classify_packet(pkt)
            offset_ms = (float(pkt.time) - capture_start_wall) * 1000

            captured.append(CapturedPacket(
                packet_number=i,
                protocol=protocol,
                source=src,
                destination=dst,
                length_bytes=len(pkt),
                timestamp_offset_ms=max(offset_ms, 0.0),
                summary=summary,
                flags=flags,
                detail=pkt.show(dump=True) if hasattr(pkt, "show") else str(pkt),
            ))
        except Exception:  # noqa: BLE001 - one malformed packet shouldn't drop the whole capture
            continue

    capture_duration_ms = (time.perf_counter() - start) * 1000

    return PacketCaptureResult(
        target=target,
        packets=captured,
        source=DataSource.REAL,
        capture_duration_ms=capture_duration_ms,
    )
