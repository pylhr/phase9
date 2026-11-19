"""
Protocol Layer — JavaScript Execution Analyzer (Module 16, illustrative simulation).

No real mode — same rationale as the rendering pipeline: no Python process
can instrument a real browser's JS engine. What's grounded in real data:
  - The real list of script resources discovered on the page (from
    PageLoadResult.resources) with their real sizes.
  - The real inline script count from DOMMetrics.
  - Blocking vs. non-blocking classification: external scripts with 'async'
    or 'defer' hints in their URL pattern are treated as non-blocking;
    everything else (especially inline scripts) is treated as blocking.

Stage durations (download, parse, execution) are modeled as proportional to
each script's real measured byte size, using broadly accepted real-world
JS engine performance characteristics as the proportionality constants:
  - Download: the real resource's actual transfer timing (if available)
  - Parse: ~1ms per 10KB (Chrome's V8 parse throughput is typically
    ~5-10 MB/s for large bundles; 10KB/ms is a conservative mid-range)
  - Execution: variable but modeled as ~1.5x parse time, reflecting that
    most modern bundled JS spends roughly comparable time parsing vs
    executing on a cold page load

All these constants are illustrative anchors, not measurements of the
actual page's runtime — but they are grounded in publicly documented JS
engine behavior, not made up.
"""
from __future__ import annotations

from data.models import JSExecutionResult, PageLoadResult, ScriptExecutionEntry

_PARSE_THROUGHPUT_KB_PER_MS = 10.0
_EXEC_FACTOR_RELATIVE_TO_PARSE = 1.5


def _is_likely_blocking(url: str) -> bool:
    """
    Heuristic: URLs containing well-known async/deferred loader patterns
    are treated as non-blocking; everything else (including inline scripts)
    is treated as potentially parser-blocking, which is the safe/conservative
    assumption for any <script> without an observed async/defer attribute.
    """
    url_lower = url.lower()
    non_blocking_hints = ("async", "defer", "lazy", "worker", "sw.js", "service-worker")
    return not any(hint in url_lower for hint in non_blocking_hints)


def simulate_js_execution(page_load: PageLoadResult) -> JSExecutionResult:
    if page_load.error:
        return JSExecutionResult(
            url=page_load.page_url,
            error=page_load.error,
        )

    js_resources = page_load.resources_of_type("javascript")
    metrics = page_load.dom_metrics

    # Apply same "undersampled CSS" fix as rendering pipeline — when few
    # scripts were successfully fetched, the total bytes underrepresent the
    # real page's JS weight.
    js_success_count = sum(1 for r in js_resources if r.succeeded and r.size_bytes > 500)
    total_script_count = len(js_resources)

    scripts: list[ScriptExecutionEntry] = []
    total_blocking_ms = 0.0

    for resource in js_resources:
        # If this resource errored, estimate using the average of successful
        # resources (or a reasonable default if none succeeded).
        if resource.size_bytes < 500 and js_success_count > 0:
            avg_size = sum(r.size_bytes for r in js_resources if r.succeeded) / js_success_count
            size_bytes = int(avg_size)
        else:
            size_bytes = max(resource.size_bytes, 1_000)

        size_kb = size_bytes / 1024
        download_ms = resource.timing.total_ms if resource.timing.total_ms > 0 else size_kb * 0.5
        parse_ms = size_kb / _PARSE_THROUGHPUT_KB_PER_MS
        exec_ms = parse_ms * _EXEC_FACTOR_RELATIVE_TO_PARSE
        is_blocking = _is_likely_blocking(resource.url)

        entry = ScriptExecutionEntry(
            url=resource.url,
            size_bytes=size_bytes,
            download_ms=round(download_ms, 2),
            parse_ms=round(parse_ms, 2),
            execution_ms=round(exec_ms, 2),
            is_blocking=is_blocking,
            is_inline=False,
        )
        scripts.append(entry)
        if is_blocking:
            total_blocking_ms += parse_ms + exec_ms

    # Model inline scripts from the real DOMMetrics count.
    if metrics and metrics.inline_script_count > 0:
        inline_size = 800  # typical small inline snippet
        for i in range(metrics.inline_script_count):
            size_kb = inline_size / 1024
            parse_ms = size_kb / _PARSE_THROUGHPUT_KB_PER_MS
            exec_ms = parse_ms * _EXEC_FACTOR_RELATIVE_TO_PARSE
            scripts.append(ScriptExecutionEntry(
                url=f"(inline script {i + 1} of {metrics.inline_script_count})",
                size_bytes=inline_size,
                download_ms=0.0,
                parse_ms=round(parse_ms, 2),
                execution_ms=round(exec_ms, 2),
                is_blocking=True,
                is_inline=True,
            ))
            total_blocking_ms += parse_ms + exec_ms

    total_time_ms = sum(s.download_ms + s.parse_ms + s.execution_ms for s in scripts)

    return JSExecutionResult(
        url=page_load.page_url,
        scripts=scripts,
        total_blocking_time_ms=round(total_blocking_ms, 2),
        total_time_ms=round(total_time_ms, 2),
    )
