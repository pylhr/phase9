"""
Protocol Layer — Simulated packet capture (Packet Explorer, simulation mode).

Generates a realistic sequence of packets modeling what a real capture of
one HTTPS page load actually looks like: DNS query/response, TCP three-way
handshake, TLS handshake records, HTTP-over-TLS application data, then
connection teardown. Produced through the exact same CapturedPacket/
PacketCaptureResult shape as real capture, so the UI never needs to branch
on which mode it's rendering.

This sequence and its relative byte sizes are modeled on real captures
(e.g. what Wireshark shows for an actual TLS 1.3 page load) — it's
illustrative, not arbitrary.
"""
from __future__ import annotations

import random
import socket

from data.models import CapturedPacket, DataSource, PacketCaptureResult


def _client_ip() -> str:
    return f"192.168.1.{random.randint(10, 200)}"


def simulate_packet_capture(target: str) -> PacketCaptureResult:
    try:
        target_ip = socket.gethostbyname(target)
    except socket.gaierror:
        target_ip = (
            f"{random.randint(20, 209)}.{random.randint(1, 254)}."
            f"{random.randint(1, 254)}.{random.randint(1, 254)}"
        )

    client_ip = _client_ip()
    dns_server = "192.168.1.1"
    client_port = random.randint(49152, 65535)

    t = 0.0
    packets: list[CapturedPacket] = []
    n = 0

    def add(protocol: str, src: str, dst: str, length: int, summary: str, flags=None, detail: str = ""):
        nonlocal n
        n += 1
        packets.append(CapturedPacket(
            packet_number=n,
            protocol=protocol,
            source=src,
            destination=dst,
            length_bytes=length,
            timestamp_offset_ms=round(t, 2),
            summary=summary,
            flags=flags or [],
            detail=detail or summary,
        ))

    # --- DNS resolution ---
    t += random.uniform(0.1, 0.5)
    add("DNS", client_ip, dns_server, 74, f"DNS query for {target}",
        detail=f"Standard query A {target}")
    t += random.uniform(15, 60)
    add("DNS", dns_server, client_ip, 90, f"DNS response: {target} is {target_ip}",
        detail=f"Standard query response A {target_ip}")

    # --- TCP three-way handshake ---
    t += random.uniform(1, 5)
    client_seq = random.randint(1_000_000, 4_000_000_000)
    add("TCP", f"{client_ip}:{client_port}", f"{target_ip}:443", 74,
        f"TCP {client_port} -> 443 [SYN] seq={client_seq}", flags=["SYN"])

    t += random.uniform(8, 30)
    server_seq = random.randint(1_000_000, 4_000_000_000)
    add("TCP", f"{target_ip}:443", f"{client_ip}:{client_port}", 74,
        f"TCP 443 -> {client_port} [SYN, ACK] seq={server_seq} ack={client_seq + 1}",
        flags=["SYN", "ACK"])

    t += random.uniform(0.2, 1.0)
    add("TCP", f"{client_ip}:{client_port}", f"{target_ip}:443", 66,
        f"TCP {client_port} -> 443 [ACK] seq={client_seq + 1} ack={server_seq + 1}", flags=["ACK"])

    # --- TLS handshake ---
    t += random.uniform(0.5, 2.0)
    add("TLS", f"{client_ip}:{client_port}", f"{target_ip}:443", 517,
        "TLS Client Hello", detail="TLSv1.3 Record Layer: Handshake Protocol: Client Hello")

    t += random.uniform(10, 40)
    add("TLS", f"{target_ip}:443", f"{client_ip}:{client_port}", 1369,
        "TLS Server Hello, Change Cipher Spec, Application Data",
        detail="TLSv1.3 Record Layer: Handshake Protocol: Server Hello")

    t += random.uniform(0.5, 2.0)
    add("TLS", f"{client_ip}:{client_port}", f"{target_ip}:443", 126,
        "TLS Change Cipher Spec, Application Data (Finished)",
        detail="TLSv1.3 Record Layer: Handshake Protocol: Finished")

    # --- HTTP request/response over TLS (encrypted application data, sizes only) ---
    t += random.uniform(1, 4)
    add("HTTP", f"{client_ip}:{client_port}", f"{target_ip}:443", 247,
        "Application Data (encrypted HTTP request)",
        detail="TLSv1.3 Record Layer: Application Data — contents are encrypted; "
               "the HTTP Request Inspector module decodes the plaintext request "
               "by making its own request, since this capture can't decrypt TLS.")

    t += random.uniform(15, 50)
    response_packet_count = random.randint(3, 8)
    for i in range(response_packet_count):
        t += random.uniform(0.5, 3.0)
        add("HTTP", f"{target_ip}:443", f"{client_ip}:{client_port}",
            random.randint(800, 1460),
            f"Application Data (encrypted HTTP response, segment {i + 1}/{response_packet_count})",
            detail="TLSv1.3 Record Layer: Application Data — encrypted response segment.")

    # --- Connection teardown ---
    t += random.uniform(50, 200)
    add("TCP", f"{client_ip}:{client_port}", f"{target_ip}:443", 66,
        f"TCP {client_port} -> 443 [FIN, ACK]", flags=["FIN", "ACK"])
    t += random.uniform(5, 20)
    add("TCP", f"{target_ip}:443", f"{client_ip}:{client_port}", 66,
        f"TCP 443 -> {client_port} [FIN, ACK]", flags=["FIN", "ACK"])
    t += random.uniform(0.2, 1.0)
    add("TCP", f"{client_ip}:{client_port}", f"{target_ip}:443", 66,
        f"TCP {client_port} -> 443 [ACK]", flags=["ACK"])

    return PacketCaptureResult(
        target=target,
        packets=packets,
        source=DataSource.SIMULATED,
        capture_duration_ms=t,
    )
