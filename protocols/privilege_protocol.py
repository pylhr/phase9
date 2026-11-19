"""
Protocol Layer — Privilege detection.

Checks, without performing any real capture, whether this process can
actually do raw ICMP traceroute and packet capture. Used to default the
Real/Simulation toggle sensibly and to give the user an accurate, specific
reason when real mode isn't available, rather than a generic failure.
"""
from __future__ import annotations

import platform
import socket

from data.models import PrivilegeStatus


def _check_raw_socket() -> tuple[bool, str]:
    """
    Attempt to open a raw ICMP socket. This is the same privilege traceroute
    needs. On Windows this requires running as Administrator; on Linux/Mac
    it requires root or the CAP_NET_RAW capability.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        sock.close()
        return True, "Raw ICMP socket opened successfully."
    except PermissionError:
        if platform.system() == "Windows":
            return False, "Raw sockets need Administrator privileges on Windows. " \
                           "Right-click the app (or your terminal) and choose " \
                           "'Run as administrator', then restart it."
        return False, "Raw sockets need root/sudo privileges on this OS."
    except OSError as exc:
        return False, f"Raw socket unavailable: {exc}"


def _check_packet_capture() -> tuple[bool, str]:
    """
    Checks whether scapy is importable AND whether it can actually list
    capture-capable interfaces — scapy imports fine without Npcap on
    Windows, but interface listing/sniffing will fail without it.
    """
    try:
        from scapy.all import conf  # noqa: F401
    except ImportError:
        return False, "The 'scapy' package isn't installed. Run: pip install scapy"
    except Exception as exc:  # noqa: BLE001 - scapy can raise odd errors on broken installs
        return False, f"scapy failed to initialize: {exc}"

    try:
        from scapy.all import get_if_list
        interfaces = get_if_list()
        if not interfaces:
            return False, "scapy found no network interfaces to capture from."
    except Exception as exc:  # noqa: BLE001
        system = platform.system()
        if system == "Windows":
            return False, (
                "Packet capture needs Npcap installed (https://npcap.com/) and the app "
                "run as Administrator. " + str(exc)
            )
        return False, f"Packet capture unavailable: {exc}"

    # Interface listing succeeding doesn't guarantee sniff() will work
    # (permissions are checked again at sniff time), but it's the strongest
    # signal we can get without actually starting a capture.
    return True, f"scapy is ready with {len(interfaces)} interface(s) available."


def detect_privileges() -> PrivilegeStatus:
    """
    Run all checks once. Cheap enough to call at startup and again each time
    the user opens Packet Explorer / Internet Route Explorer, in case they
    relaunched the app with different privileges since the last check.
    """
    raw_ok, raw_detail = _check_raw_socket()
    capture_ok, capture_detail = _check_packet_capture()

    detail_parts = [f"Traceroute: {raw_detail}", f"Packet capture: {capture_detail}"]

    return PrivilegeStatus(
        can_capture_packets=capture_ok,
        can_raw_traceroute=raw_ok,
        platform=platform.system(),
        detail="  ".join(detail_parts),
    )
