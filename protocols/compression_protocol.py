"""
Protocol Layer — Compression analysis.

Pure derivation from an already-fetched HTTPResponseRecord — no new network
call. Kept in the protocol layer (rather than inline in the UI) so the
calculation logic is testable on its own and consistent with how DNS/HTTP/
TLS results are produced.
"""
from __future__ import annotations

from data.models import CompressionAnalysis, HTTPResponseRecord


def analyze_compression(response: HTTPResponseRecord) -> CompressionAnalysis:
    return CompressionAnalysis(
        algorithm=response.compression,
        compressed_size_bytes=response.compressed_size_bytes,
        decompressed_size_bytes=response.body_size_bytes,
        content_type=response.content_type,
    )
