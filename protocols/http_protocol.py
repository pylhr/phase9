"""
Protocol Layer — HTTP request/response inspection.

Performs a real HTTP request using httpx and converts the result into our
data-layer records. No Qt dependencies — the service layer runs this off
the UI thread.
"""
from __future__ import annotations

import time

import httpx

from data.models import HTTPExchangeResult, HTTPRequestRecord, HTTPResponseRecord

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "TheInternetExplorer/1.0 (Educational Network Inspector)"
)

# How much of the response body to keep as a readable preview. Full bodies
# can be megabytes; the inspector only needs enough to show shape/content,
# not to replace viewing the page itself.
BODY_PREVIEW_LIMIT = 4000


def fetch_http_exchange(url: str, timeout: float = 15.0) -> HTTPExchangeResult:
    """
    Perform a real GET request against `url` and return the full
    request/response exchange, including timing.

    Redirects are NOT followed automatically — Module 6/7 in the spec is
    about inspecting *the* request and response for the entered URL, and
    silently following redirects would hide that a redirect happened.
    A future phase (waterfall/resource graph) is the right place to chain
    multiple requests together.
    """
    request_record = HTTPRequestRecord(
        method="GET",
        url=url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, br",
            "Connection": "keep-alive",
        },
    )

    start = time.perf_counter()
    try:
        with httpx.Client(follow_redirects=False, timeout=timeout) as client:
            response = client.get(url, headers=request_record.headers)
    except httpx.ConnectTimeout:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return HTTPExchangeResult(
            request=request_record,
            error=f"Connection timed out after {timeout}s",
            total_time_ms=elapsed_ms,
        )
    except httpx.ConnectError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return HTTPExchangeResult(
            request=request_record,
            error=f"Could not connect: {exc}",
            total_time_ms=elapsed_ms,
        )
    except httpx.RequestError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return HTTPExchangeResult(
            request=request_record,
            error=str(exc),
            total_time_ms=elapsed_ms,
        )

    elapsed_ms = (time.perf_counter() - start) * 1000

    response_record = _build_response_record(response, elapsed_ms)

    return HTTPExchangeResult(
        request=request_record,
        response=response_record,
        total_time_ms=elapsed_ms,
    )


def _build_response_record(response: httpx.Response, elapsed_ms: float) -> HTTPResponseRecord:
    # dict(response.headers) comma-joins repeated headers into one string,
    # which silently corrupts Set-Cookie values (commas can legitimately
    # appear inside an Expires date). Pull Set-Cookie out via get_list()
    # first, then build the flattened dict from everything else.
    raw_set_cookie_headers = response.headers.get_list("set-cookie")
    headers = {
        key: value
        for key, value in dict(response.headers).items()
        if key.lower() != "set-cookie"
    }

    content_type = headers.get("content-type", "")
    compression = headers.get("content-encoding")

    is_binary = not content_type.startswith(("text/", "application/json", "application/xml",
                                              "application/xhtml+xml", "application/javascript"))

    body_size = len(response.content)

    # httpx auto-decompresses response.content, so body_size above is the
    # DEcompressed size. num_bytes_downloaded reflects what was actually
    # read off the wire (it matches the real Content-Length when present),
    # so it's the honest source for a real compression ratio rather than
    # something inferred or estimated.
    compressed_size = response.num_bytes_downloaded if compression else None

    if is_binary:
        preview = f"[binary content, {body_size:,} bytes, type: {content_type or 'unknown'}]"
    else:
        try:
            text = response.text
        except Exception:  # noqa: BLE001 - decoding can fail for mislabeled charsets
            preview = "[could not decode response body as text]"
        else:
            preview = text[:BODY_PREVIEW_LIMIT]
            if len(text) > BODY_PREVIEW_LIMIT:
                preview += f"\n\n… truncated ({len(text):,} characters total)"

    return HTTPResponseRecord(
        status_code=response.status_code,
        reason=response.reason_phrase,
        headers=headers,
        body_preview=preview,
        body_size_bytes=body_size,
        compressed_size_bytes=compressed_size,
        content_type=content_type,
        compression=compression,
        response_time_ms=elapsed_ms,
        http_version=response.http_version,
        is_binary=is_binary,
        raw_set_cookie_headers=raw_set_cookie_headers,
    )
