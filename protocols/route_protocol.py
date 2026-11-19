"""
Protocol Layer — Real traceroute (Internet Route Explorer, real mode).

Implements the classic traceroute algorithm directly with raw ICMP sockets:
send an Echo Request with an incrementing TTL, and read whichever router
along the path drops the packet (it replies "Time Exceeded"), until the
real destination replies with an actual Echo Reply.

Needs raw-socket privileges — Administrator on Windows, root on Linux/Mac.
Use protocols.privilege_protocol.detect_privileges() to check first; this
module raises PermissionError on its own if it can't open the socket, which
the service layer surfaces as a normal error rather than a crash.
"""
from __future__ import annotations

import platform
import socket
import struct
import time
from typing import Optional

from data.models import DataSource, RouteHop, RouteResult

MAX_HOPS = 30
PROBE_TIMEOUT = 1.0
# If this many hops in a row produce no reply, the path is very likely
# blocked beyond that point (a common real-world case: a firewall drops
# ICMP for everything past a certain point). Real traceroute tools use this
# same heuristic to avoid burning through all MAX_HOPS at full timeout —
# without it, a single blocked path costs MAX_HOPS * PROBE_TIMEOUT seconds
# with zero new information for the back half of that wait.
MAX_CONSECUTIVE_TIMEOUTS = 5
# Hard ceiling on total wall-clock time, regardless of the above — a safety
# net so the UI can never appear to hang indefinitely on an unusual network.
MAX_TOTAL_SECONDS = 20.0
ICMP_ECHO_REQUEST = 8
ICMP_TIME_EXCEEDED = 11
ICMP_ECHO_REPLY = 0


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return ~total & 0xFFFF


def _build_icmp_echo(packet_id: int, sequence: int) -> bytes:
    header = struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, 0, packet_id, sequence)
    payload = b"TheInternetExplorer-traceroute-probe"
    chksum = _checksum(header + payload)
    header = struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, chksum, packet_id, sequence)
    return header + payload


def _reverse_dns(ip: str, timeout: float = 1.0) -> Optional[str]:
    # gethostbyaddr has no timeout parameter of its own and uses whatever
    # the system resolver does, which can occasionally hang far longer than
    # is reasonable for a per-hop lookup during an interactive traceroute.
    # socket.setdefaulttimeout affects the whole process for the duration
    # of this call, so we save/restore it rather than touching global state
    # permanently.
    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return None
    finally:
        socket.setdefaulttimeout(previous_timeout)


def trace_route(destination: str, max_hops: int = MAX_HOPS) -> RouteResult:
    """
    Perform a real traceroute to `destination` (hostname or IP).

    Raises PermissionError if raw sockets aren't available — callers should
    check protocols.privilege_protocol.detect_privileges() first and only
    call this when can_raw_traceroute is True, but this is also a safe
    fallback guard on its own.
    """
    start = time.perf_counter()

    try:
        destination_ip = socket.gethostbyname(destination)
    except socket.gaierror as exc:
        return RouteResult(
            destination=destination,
            destination_ip=None,
            source=DataSource.REAL,
            error=f"Could not resolve {destination}: {exc}",
        )

    # Windows requires IPPROTO_ICMP with SOCK_RAW; the TTL is set via
    # IP_TTL socket option rather than building our own IP header, which
    # works identically on Windows and Linux/Mac.
    try:
        recv_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        recv_socket.settimeout(PROBE_TIMEOUT)
    except PermissionError:
        system = platform.system()
        hint = ("Run as Administrator on Windows." if system == "Windows"
                else "Run with sudo/root privileges.")
        return RouteResult(
            destination=destination,
            destination_ip=destination_ip,
            source=DataSource.REAL,
            error=f"Raw sockets require elevated privileges. {hint}",
        )

    hops: list[RouteHop] = []
    packet_id = (id(destination) ^ int(time.time())) & 0xFFFF
    consecutive_timeouts = 0

    try:
        for ttl in range(1, max_hops + 1):
            if time.perf_counter() - start > MAX_TOTAL_SECONDS:
                break

            send_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            send_socket.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
            send_socket.settimeout(PROBE_TIMEOUT)

            probe = _build_icmp_echo(packet_id, ttl)
            hop_start = time.perf_counter()

            try:
                send_socket.sendto(probe, (destination_ip, 0))
                reply_data, addr = recv_socket.recvfrom(1024)
                rtt_ms = (time.perf_counter() - hop_start) * 1000
                hop_ip = addr[0]
                consecutive_timeouts = 0

                icmp_type = reply_data[20]  # IP header is 20 bytes, ICMP starts after

                hops.append(RouteHop(
                    hop_number=ttl,
                    ip_address=hop_ip,
                    hostname=_reverse_dns(hop_ip),
                    rtt_ms=rtt_ms,
                    is_destination=(hop_ip == destination_ip or icmp_type == ICMP_ECHO_REPLY),
                ))

                if hop_ip == destination_ip or icmp_type == ICMP_ECHO_REPLY:
                    break

            except socket.timeout:
                consecutive_timeouts += 1
                hops.append(RouteHop(
                    hop_number=ttl,
                    ip_address=None,
                    rtt_ms=None,
                    timed_out=True,
                ))
                if consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                    # The path is very likely blocked beyond this point —
                    # stop early rather than burning the remaining hop
                    # budget at full timeout for no new information.
                    break
            finally:
                send_socket.close()
    finally:
        recv_socket.close()

    total_time_ms = (time.perf_counter() - start) * 1000

    return RouteResult(
        destination=destination,
        destination_ip=destination_ip,
        hops=hops,
        source=DataSource.REAL,
        total_time_ms=total_time_ms,
    )
