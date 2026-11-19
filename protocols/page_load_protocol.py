"""
Protocol Layer — Page Load (resources + waterfall timing).

Fetches the real page HTML, parses it with BeautifulSoup to find actual
CSS/JS/image/font/API resources referenced by the page (not guesses), then
fetches a bounded number of them concurrently using httpx's async client so
the resulting timeline has a real, not simulated, overlapping shape.

This is the shared data source for both the Resource Dependency Analyzer
(Module 8) and the Network Waterfall Timeline (Module 9).
"""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from data.models import DOMMetrics, PageLoadResult, PageResource, ResourceTiming
from protocols.http_protocol import DEFAULT_USER_AGENT

# Fetching every resource on a real page (sites can reference 100+ assets)
# would be slow and discourteous to the target server. We fetch a bounded,
# representative sample per type for real timing data, and still *report*
# every resource we discovered in the markup — so the dependency graph is
# complete even though the waterfall only times a sample.
MAX_FETCHED_PER_TYPE = 6
MAX_TOTAL_FETCHED = 24
REQUEST_TIMEOUT = 10.0

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".avif")
_FONT_EXTENSIONS = (".woff", ".woff2", ".ttf", ".otf", ".eot")


def _compute_dom_metrics(html: str) -> DOMMetrics:
    """
    Real structural facts about the page's actual HTML — used later by the
    (illustrative) rendering pipeline and JS execution modules to scale
    their simulated stage durations to this specific page's real
    complexity, rather than using arbitrary fixed numbers.
    """
    soup = BeautifulSoup(html, "html.parser")

    element_count = 0
    text_node_count = 0
    max_depth = 0
    script_tag_count = 0
    inline_script_count = 0
    style_tag_count = 0

    def walk(node, depth: int) -> None:
        nonlocal element_count, text_node_count, max_depth, script_tag_count, inline_script_count, style_tag_count
        for child in getattr(node, "children", []):
            name = getattr(child, "name", None)
            if name is None:
                # NavigableString — only count non-whitespace text as a real text node.
                if str(child).strip():
                    text_node_count += 1
                continue

            element_count += 1
            max_depth = max(max_depth, depth)

            if name == "script":
                script_tag_count += 1
                if not child.get("src"):
                    inline_script_count += 1
            elif name == "style":
                style_tag_count += 1

            walk(child, depth + 1)

    walk(soup, 0)

    return DOMMetrics(
        element_count=element_count,
        max_depth=max_depth,
        script_tag_count=script_tag_count,
        inline_script_count=inline_script_count,
        style_tag_count=style_tag_count,
        text_node_count=text_node_count,
    )


def _extract_resources(html: str, base_url: str) -> list[PageResource]:
    """Parse real <link>, <script>, <img>, and srcset references from the page."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, PageResource] = {}  # dedupe by absolute URL

    def add(raw_url: str | None, resource_type: str, discovered_from: str = "html") -> None:
        if not raw_url or raw_url.startswith(("data:", "blob:", "javascript:", "#")):
            return
        absolute = urljoin(base_url, raw_url)
        if absolute not in found:
            found[absolute] = PageResource(
                url=absolute,
                resource_type=resource_type,
                discovered_from=discovered_from,
            )

    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel", [])).lower()
        href = link.get("href")
        if "stylesheet" in rel:
            add(href, "css")
        elif "icon" in rel:
            add(href, "image")
        elif "font" in rel or (href and href.lower().endswith(_FONT_EXTENSIONS)):
            add(href, "font")
        elif "preload" in rel and link.get("as") == "font":
            add(href, "font")

    for script in soup.find_all("script"):
        src = script.get("src")
        if src:
            add(src, "javascript")

    for img in soup.find_all("img"):
        add(img.get("src"), "image")
        srcset = img.get("srcset")
        if srcset:
            # srcset is a comma-separated list of "url descriptor" pairs.
            for candidate in srcset.split(","):
                url_part = candidate.strip().split(" ")[0]
                add(url_part, "image")

    for source in soup.find_all("source"):
        add(source.get("srcset") or source.get("src"), "image")

    return list(found.values())


def _select_fetch_sample(resources: list[PageResource]) -> list[PageResource]:
    """Pick a bounded, representative sample to actually fetch and time."""
    by_type: dict[str, list[PageResource]] = {}
    for r in resources:
        by_type.setdefault(r.resource_type, []).append(r)

    sample: list[PageResource] = []
    for rtype, items in by_type.items():
        sample.extend(items[:MAX_FETCHED_PER_TYPE])
    return sample[:MAX_TOTAL_FETCHED]


async def _fetch_one(client: httpx.AsyncClient, resource: PageResource, load_start: float) -> None:
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    start = time.perf_counter()
    resource.start_offset_ms = (start - load_start) * 1000

    try:
        connect_start = time.perf_counter()
        response = await client.get(resource.url, headers=headers)
        total = (time.perf_counter() - connect_start) * 1000

        resource.status_code = response.status_code
        resource.size_bytes = len(response.content)
        resource.content_type = response.headers.get("content-type", "")
        # httpx's async client doesn't expose the same low-level connect/TLS
        # timing hooks we used for the dedicated TLS module, so for resource
        # fetches we report total time honestly as one measured span rather
        # than fabricating a DNS/connect/TLS split we didn't actually measure.
        resource.timing = ResourceTiming(
            download_ms=total,
            total_ms=total,
        )
        if response.status_code >= 400:
            resource.error = f"HTTP {response.status_code}"

    except httpx.TimeoutException:
        resource.error = f"Timed out after {REQUEST_TIMEOUT}s"
        resource.timing.total_ms = (time.perf_counter() - start) * 1000
    except httpx.RequestError as exc:
        resource.error = str(exc)
        resource.timing.total_ms = (time.perf_counter() - start) * 1000


async def _fetch_sample_async(sample: list[PageResource], load_start: float) -> None:
    limits = httpx.Limits(max_connections=8, max_keepalive_connections=8)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, limits=limits, follow_redirects=True) as client:
        await asyncio.gather(*[_fetch_one(client, r, load_start) for r in sample])


def load_page(url: str) -> PageLoadResult:
    """
    Fetch the real page at `url`, parse it for real resource references, and
    fetch a representative sample of those resources concurrently with real
    timing. Runs its own event loop — call this from a background thread,
    not the Qt UI thread.
    """
    load_start = time.perf_counter()
    headers = {"User-Agent": DEFAULT_USER_AGENT}

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            html_start = time.perf_counter()
            response = client.get(url, headers=headers)
            html_elapsed = (time.perf_counter() - html_start) * 1000
    except httpx.TimeoutException:
        return PageLoadResult(page_url=url, error=f"Timed out after {REQUEST_TIMEOUT}s")
    except httpx.RequestError as exc:
        return PageLoadResult(page_url=url, error=f"Could not connect: {exc}")

    if response.status_code >= 400:
        return PageLoadResult(
            page_url=url,
            error=f"Page request failed: HTTP {response.status_code}",
        )

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type:
        return PageLoadResult(
            page_url=url,
            error=f"Response was not HTML (Content-Type: {content_type or 'unknown'}), "
                  f"so there's no page structure to analyze.",
        )

    html_resource = PageResource(
        url=str(response.url),
        resource_type="html",
        status_code=response.status_code,
        size_bytes=len(response.content),
        content_type=content_type,
        timing=ResourceTiming(download_ms=html_elapsed, total_ms=html_elapsed),
        start_offset_ms=0.0,
    )

    discovered = _extract_resources(response.text, str(response.url))
    sample = _select_fetch_sample(discovered)
    dom_metrics = _compute_dom_metrics(response.text)

    if sample:
        asyncio.run(_fetch_sample_async(sample, load_start))

    all_resources = [html_resource] + discovered
    total_time_ms = (time.perf_counter() - load_start) * 1000

    return PageLoadResult(
        page_url=url,
        resources=all_resources,
        total_time_ms=total_time_ms,
        dom_metrics=dom_metrics,
    )
