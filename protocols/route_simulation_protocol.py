"""
Protocol Layer — Simulated traceroute (Internet Route Explorer, simulation mode).

Produces synthetic but realistic RouteResult data through the exact same
shape as the real traceroute, so the UI layer never needs to know which mode
it's rendering. This isn't a "lesser" fallback — per the project's plan, it's
a legitimate teaching/demo mode in its own right: it lets the route
visualization, hop table, and geo display all be exercised and demonstrated
without needing Administrator privileges or a live network path, and can
model interesting topologies (long paths, a dead hop) that might not occur
on a real trace at demo time.

Results are randomized per-call (not hardcoded) so repeated demos don't look
identical, but kept within realistic bounds: hop counts, RTT growth, and ISP
naming patterns are modeled after how real internet paths typically look.
"""
from __future__ import annotations

import random
import socket
import time

from data.models import DataSource, RouteHop, RouteResult

# Recognizable, real backbone/transit provider name fragments, used to build
# plausible-looking simulated hostnames (e.g. "ae-3.r21.asbnva02.us.bb.gin.ntt.net"
# style real-world traceroute hostnames follow this rough shape).
_ISP_FRAGMENTS = ["level3", "cogent", "ntt", "telia", "hurricane", "zayo", "gtt"]
_REGION_CODES = ["nyc", "chi", "dal", "sea", "lax", "ash", "fra", "lon", "ams"]


def _fake_hostname(hop_index: int, near_destination: bool) -> str:
    if near_destination:
        return f"edge-{hop_index}.target-network.net"
    isp = random.choice(_ISP_FRAGMENTS)
    region = random.choice(_REGION_CODES)
    return f"ae-{hop_index}.r{hop_index}.{region}.{isp}.net"


def _fake_ip(hop_index: int) -> str:
    # Stays within documentation/example ranges conceptually but varies
    # enough to look like a real path's mix of private and public-looking hops.
    if hop_index == 1:
        return f"192.168.1.{random.randint(1, 254)}"
    return f"{random.randint(20, 209)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"


def simulate_traceroute(destination: str, min_hops: int = 8, max_hops: int = 16) -> RouteResult:
    """
    Generate a realistic synthetic traceroute to `destination`. Resolves the
    destination's real IP via DNS if possible (so the displayed destination
    is at least accurate), but every hop in between is synthetic.
    """
    start = time.perf_counter()

    try:
        destination_ip = socket.gethostbyname(destination)
    except socket.gaierror:
        destination_ip = (
            f"{random.randint(20, 209)}.{random.randint(1, 254)}."
            f"{random.randint(1, 254)}.{random.randint(1, 254)}"
        )

    hop_count = random.randint(min_hops, max_hops)
    hops: list[RouteHop] = []

    # RTT generally trends upward with hop count (more distance/links to
    # traverse) but with realistic per-hop jitter, occasionally even
    # decreasing slightly (a faster backbone link) — straight-line-increasing
    # RTT would look obviously fake to anyone who's seen a real traceroute.
    base_rtt = random.uniform(1.0, 8.0)

    # Occasionally model one "dark" hop that doesn't reply — common on real
    # networks where a router is configured not to send ICMP Time Exceeded,
    # which is realistic and also exercises the UI's timeout rendering.
    dark_hop_index = random.choice([None, None, random.randint(2, hop_count - 1)])

    for i in range(1, hop_count + 1):
        near_destination = i >= hop_count - 1

        if i == dark_hop_index:
            hops.append(RouteHop(hop_number=i, ip_address=None, rtt_ms=None, timed_out=True))
            continue

        base_rtt += random.uniform(-1.5, 6.0)
        base_rtt = max(base_rtt, 0.5)
        rtt = base_rtt + random.uniform(0, 3.0)

        is_last = (i == hop_count)
        hops.append(RouteHop(
            hop_number=i,
            ip_address=destination_ip if is_last else _fake_ip(i),
            hostname=destination if is_last else _fake_hostname(i, near_destination),
            rtt_ms=round(rtt, 2),
            is_destination=is_last,
        ))

    total_time_ms = (time.perf_counter() - start) * 1000 + hop_count * random.uniform(8, 25)

    return RouteResult(
        destination=destination,
        destination_ip=destination_ip,
        hops=hops,
        source=DataSource.SIMULATED,
        total_time_ms=total_time_ms,
    )
