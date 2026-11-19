"""
Protocol Layer — Browser Rendering Pipeline (Module 15, illustrative simulation).

There is no real mode for this module: no Python process can instrument an
actual browser engine's internal DOM construction, layout, or paint timing
from outside the browser. What this module CAN do honestly is model the
real pipeline stages in their real order, with real explanations of what
each stage does, and scale each stage's illustrative duration to the page's
*actual* measured complexity (real DOM element count/depth from
DOMMetrics, real CSS/JS byte sizes from PageLoadResult) rather than using
arbitrary fixed numbers untethered from the page being explored.

Every result from this module carries source=DataSource.SIMULATED — the UI
layer must never present this as a live trace.
"""
from __future__ import annotations

from data.models import DataSource, DOMMetrics, PageLoadResult, RenderingPipelineResult, RenderStage

_STAGE_DESCRIPTIONS = {
    "DOM Construction": (
        "The browser parses the raw HTML byte-by-byte into the Document Object "
        "Model — a tree of node objects representing every element and text node."
    ),
    "CSSOM Construction": (
        "All CSS (external stylesheets and inline <style> tags) is parsed into the "
        "CSS Object Model, a tree of style rules the browser can query efficiently."
    ),
    "Render Tree": (
        "The DOM and CSSOM are combined into the Render Tree — only nodes that will "
        "actually be visible (excluding e.g. <head>, display:none elements)."
    ),
    "Layout": (
        "Also called 'reflow': the browser computes the exact size and position of "
        "every node in the Render Tree, given the viewport size."
    ),
    "Paint": (
        "The browser fills in pixels for each node — text, colors, borders, shadows — "
        "onto one or more layers."
    ),
    "Composite": (
        "Layers are combined in the correct order (respecting z-index, transforms, "
        "and opacity) and sent to the GPU for final display."
    ),
}

# Roughly how each stage's cost scales with page complexity, used to weight
# the proportional split below. These weights reflect well-documented
# browser behavior (e.g. DOM parsing scales with byte size; layout scales
# closer to element count and especially nesting depth, since reflow can
# cascade through ancestors) — not arbitrary, but still illustrative since
# the actual constant-factor speed depends on the specific browser engine,
# CPU, and GPU, which this app cannot observe.
_BASE_STAGE_MS = {
    "DOM Construction": 8.0,
    "CSSOM Construction": 4.0,
    "Render Tree": 3.0,
    "Layout": 6.0,
    "Paint": 5.0,
    "Composite": 2.0,
}


def simulate_rendering_pipeline(page_load: PageLoadResult) -> RenderingPipelineResult:
    if page_load.error or page_load.dom_metrics is None:
        return RenderingPipelineResult(
            url=page_load.page_url,
            error=page_load.error or "No DOM data available to model a rendering pipeline from.",
        )

    metrics: DOMMetrics = page_load.dom_metrics
    html_resource = next((r for r in page_load.resources if r.resource_type == "html"), None)
    html_bytes = html_resource.size_bytes if html_resource else 0

    css_resources = page_load.resources_of_type("css")
    css_bytes_raw = sum(r.size_bytes for r in css_resources)
    # Only count resources that fetched successfully (status 2xx, no error),
    # since error responses also produce a small non-zero size_bytes (the
    # error body), which inflates the count while the byte total stays near 0.
    css_success_count = sum(1 for r in css_resources if r.succeeded and r.size_bytes > 500)
    css_discovered_count = len(css_resources)
    css_bytes = css_bytes_raw
    # The Resource Dependency job only downloads a bounded sample of each
    # resource type (see page_load_protocol.MAX_FETCHED_PER_TYPE) — on a
    # page with many stylesheets, most may show 0 bytes simply because they
    # weren't in the sample (or were blocked, e.g. anti-hotlinking), not
    # because the page has little CSS. When fewer than half of the discovered
    # CSS files were successfully measured, scale up the estimate based on
    # the real discovered count, so a page referencing many stylesheets
    # doesn't look artificially CSS-light.
    if css_discovered_count > 0 and css_success_count < css_discovered_count / 2:
        average_per_file = (css_bytes_raw / css_success_count) if css_success_count > 0 else 15_000
        css_bytes = max(css_bytes_raw, average_per_file * css_discovered_count)

    # Scale factors derived from real, measured values for this page —
    # normalized against typical real-world page sizes so the illustrative
    # timings land in a plausible range (single-digit to low-hundreds of ms)
    # rather than being either instant or absurdly slow.
    html_factor = max(html_bytes / 50_000, 0.2)        # ~50KB HTML is a typical baseline
    css_factor = max(css_bytes / 30_000, 0.15)          # ~30KB CSS is a typical baseline
    element_factor = max(metrics.element_count / 800, 0.2)
    depth_factor = max(metrics.max_depth / 12, 0.3)

    stage_factors = {
        "DOM Construction": html_factor,
        "CSSOM Construction": css_factor,
        "Render Tree": (element_factor + css_factor) / 2,
        "Layout": (element_factor + depth_factor) / 2,
        "Paint": element_factor,
        "Composite": max(depth_factor * 0.5, 0.2),
    }

    stages: list[RenderStage] = []
    offset = 0.0
    for name, base_ms in _BASE_STAGE_MS.items():
        duration = base_ms * stage_factors[name]
        stages.append(RenderStage(
            name=name,
            description=_STAGE_DESCRIPTIONS[name],
            duration_ms=duration,
            start_offset_ms=offset,
        ))
        offset += duration

    return RenderingPipelineResult(
        url=page_load.page_url,
        stages=stages,
        total_time_ms=offset,
        dom_metrics=metrics,
    )
