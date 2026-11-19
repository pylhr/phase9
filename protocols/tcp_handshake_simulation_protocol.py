"""
Protocol Layer — Simulated TCP handshake (TCP Handshake Visualizer, simulation mode).

Generates a realistic synthetic three-way handshake through the exact same
TCPHandshakeResult/TCPHandshakeStep shape as real capture, with plausible
sequence numbers, window sizes, and RTT timing.
"""
from __future__ import annotations

import random
import socket

from data.models import DataSource, TCPHandshakeResult, TCPHandshakeStep


def simulate_tcp_handshake(target: str, port: int = 443) -> TCPHandshakeResult:
    try:
        socket.gethostbyname(target)  # resolved only to make the simulation feel grounded; unused otherwise
    except socket.gaierror:
        pass

    client_seq = random.randint(1, 4_000_000_000)
    server_seq = random.randint(1, 4_000_000_000)
    client_window = random.choice([64240, 65280, 65535])
    server_window = random.choice([28960, 43440, 65160])

    # Plausible RTT: simulation models a realistic geographically-distant
    # connection rather than the near-zero RTT typical of a real capture
    # made from this sandbox's own short network path.
    network_rtt = random.uniform(15, 90)

    steps = [
        TCPHandshakeStep(
            step_number=1,
            direction="client_to_server",
            flags=["SYN"],
            sequence_number=client_seq,
            ack_number=0,
            window_size=client_window,
            rtt_ms=None,
        ),
        TCPHandshakeStep(
            step_number=2,
            direction="server_to_client",
            flags=["SYN", "ACK"],
            sequence_number=server_seq,
            ack_number=client_seq + 1,
            window_size=server_window,
            rtt_ms=network_rtt,
        ),
        TCPHandshakeStep(
            step_number=3,
            direction="client_to_server",
            flags=["ACK"],
            sequence_number=client_seq + 1,
            ack_number=server_seq + 1,
            window_size=client_window,
            rtt_ms=network_rtt * random.uniform(0.05, 0.3),
        ),
    ]

    total_time_ms = sum(s.rtt_ms for s in steps if s.rtt_ms is not None)

    return TCPHandshakeResult(
        target=target,
        port=port,
        steps=steps,
        source=DataSource.SIMULATED,
        total_time_ms=total_time_ms,
    )
