"""
UI Layer — Design tokens.

Design direction: an "instrument panel" aesthetic — closer to an oscilloscope
or Wireshark than a generic SaaS app, since the whole point of this tool is
making invisible signals visible. Monospace is used for anything that is
literally data off the wire (IPs, hex, headers); a clean sans is used for
explanatory UI chrome. A single signal-green accent marks "live/active" data,
echoing terminal and network-monitoring tools without going full Matrix.

Phase 1 ships dark mode only. Light mode (a UI requirement from the spec)
arrives in the polish phase (Phase 10) once there's enough surface area to
theme consistently — these tokens are structured as a dict precisely so a
LIGHT palette can be swapped in later without touching widget code.
"""
from __future__ import annotations

DARK = {
    # Backgrounds, darkest to lightest — gives real depth between the app
    # chrome, panels, and elevated cards instead of one flat slab of color.
    "bg_app": "#0B0E13",
    "bg_panel": "#11151C",
    "bg_card": "#161B24",
    "bg_elevated": "#1C232E",
    "bg_input": "#0E1218",

    # Borders
    "border": "#242B36",
    "border_subtle": "#1A2029",
    "border_focus": "#3DDC97",

    # Text
    "text_primary": "#E8EBF0",
    "text_secondary": "#9AA5B4",
    "text_muted": "#5C6675",
    "text_disabled": "#3A4150",

    # Signal accent — "live data" green, used sparingly so it stays meaningful
    "accent": "#3DDC97",
    "accent_dim": "#2A9D6F",
    "accent_bg": "#11251C",

    # Secondary accent — used for DNS / resolution-stage elements
    "accent_blue": "#5EA8FF",
    "accent_blue_bg": "#101A2C",

    # Status colors
    "success": "#3DDC97",
    "warning": "#F0B459",
    "error": "#F2607A",
    "error_bg": "#2A1019",

    # Record-type chip colors (DNS module) — distinct enough to scan quickly
    "chip_a": "#5EA8FF",
    "chip_aaaa": "#8C7CFF",
    "chip_cname": "#F0B459",
    "chip_mx": "#F2607A",
    "chip_ns": "#3DDC97",
    "chip_txt": "#9AA5B4",

    # Resource-type colors (waterfall + dependency graph) — kept visually
    # distinct from the DNS chips above since both can appear in screenshots
    # together, but consistent in style (one accent per category).
    "res_html": "#3DDC97",
    "res_css": "#5EA8FF",
    "res_javascript": "#F0B459",
    "res_image": "#C77DFF",
    "res_font": "#F2607A",
    "res_other": "#9AA5B4",

    # Packet-protocol colors (Packet Explorer)
    "proto_tcp": "#5EA8FF",
    "proto_udp": "#8C7CFF",
    "proto_tls": "#3DDC97",
    "proto_http": "#F0B459",
    "proto_dns": "#F2607A",
    "proto_icmp": "#C77DFF",
    "proto_arp": "#9AA5B4",
    "proto_other": "#9AA5B4",
}

FONT_DISPLAY = "Segoe UI"          # UI chrome, labels, headings (Windows-native)
FONT_MONO = "Cascadia Mono"        # data: IPs, hex, headers, raw protocol output
FONT_MONO_FALLBACK = "Consolas"    # guaranteed present on Windows if Cascadia isn't installed

RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 10

SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 20
SPACE_XL = 32


def chip_color(record_type: str) -> str:
    key = f"chip_{record_type.lower()}"
    return DARK.get(key, DARK["text_secondary"])


def resource_color(resource_type: str) -> str:
    key = f"res_{resource_type.lower()}"
    return DARK.get(key, DARK["res_other"])


def protocol_color(protocol: str) -> str:
    key = f"proto_{protocol.lower()}"
    return DARK.get(key, DARK["proto_other"])
