import asyncio
import hashlib
import logging
import re
import time
from typing import Optional

import httpx

from .schema import FetchResult
from .extractor import extract_content, detect_content_type
from .sanitizer import sanitize

logger = logging.getLogger("agentfetch.router")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

JS_FRAMEWORK_MARKERS = [
    "__NEXT_DATA__",
    "__NUXT__",
    "ng-version",
    "data-reactroot",
    "window.__INITIAL_STATE__",
    "ember-application",
    "_app-root",
]

STATIC_EXTENSIONS = {".txt", ".md", ".xml", ".json", ".csv"}


def _needs_browser(html: str, extracted_text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if not extracted_text:
        reasons.append("extraction returned empty")

    if len(extracted_text) < 150:
        reasons.append(f"extracted text too short ({len(extracted_text)} chars)")

    for marker in JS_FRAMEWORK_MARKERS:
        if marker in html:
            reasons.append(f"JS framework marker found: {marker}")
            break

    noscript_match = re.search(r"<noscript>(.*?)</noscript>", html, re.DOTALL)
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL)
    if noscript_match and body_match:
        noscript_len = len(noscript_match.group(1))
        body_len = len(body_match.group(1))
        if body_len > 0 and noscript_len > body_len * 0.5:
            reasons.append("noscript content > 50% of body")

    return len(reasons) > 0, reasons


async def _static_fetch(url: str) -> FetchResult:
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=15.0) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        return FetchResult(
            url=url,
            content="",
            confidence=0.0,
            error=str(e),
            latency_ms=int((time.monotonic() - start) * 1000),
            render_mode="static",
        )

    text, extractor = extract_content(html, url)
    text, injection_detected = sanitize(text, url)
    content_type = detect_content_type(html, url)
    title = _extract_title(html)
    latency = int((time.monotonic() - start) * 1000)
    wc = len(text.split())
    links = _extract_links(html)

    return FetchResult(
        url=url,
        content=text,
        title=title,
        confidence=1.0,
        content_type=content_type,
        word_count=wc,
        render_mode="static",
        latency_ms=latency,
        injection_detected=injection_detected,
        links=links,
    )


async def _browser_fetch(url: str) -> FetchResult:
    start = time.monotonic()
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle")
            html = await page.content()
            await browser.close()
    except Exception as e:
        return FetchResult(
            url=url,
            content="",
            confidence=0.0,
            error=str(e),
            latency_ms=int((time.monotonic() - start) * 1000),
            render_mode="browser",
        )

    text, extractor = extract_content(html, url)
    text, injection_detected = sanitize(text, url)
    content_type = detect_content_type(html, url)
    title = _extract_title(html)
    latency = int((time.monotonic() - start) * 1000)
    wc = len(text.split())
    links = _extract_links(html)

    confidence = 1.0
    confidence -= 0.2
    if extractor not in ("trafilatura", ""):
        confidence -= 0.3
    confidence = max(0.1, confidence)

    return FetchResult(
        url=url,
        content=text,
        title=title,
        confidence=confidence,
        content_type=content_type,
        word_count=wc,
        render_mode="browser",
        latency_ms=latency,
        injection_detected=injection_detected,
        links=links,
    )


def _extract_title(html: str) -> Optional[str]:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


def _extract_links(html: str) -> list[str]:
    return re.findall(r'href=["\'](https?://[^"\']+)["\']', html)


def _is_static_url(url: str) -> bool:
    path = url.split("?")[0].split("#")[0]
    return any(path.endswith(ext) for ext in STATIC_EXTENSIONS)


async def smart_fetch(
    url: str,
    engine: str = "auto",
    use_cache: bool = True,
    cache_ttl: int = 3600,
) -> FetchResult:
    if _is_static_url(url):
        result = await _static_fetch(url)
        result.render_mode = "static"
        return result

    result = await _static_fetch(url)
    if result.error:
        return result

    html = ""
    try:
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=15.0) as client:
            resp = await client.get(url, follow_redirects=True)
            html = resp.text
    except Exception:
        html = ""

    if not html:
        return result

    text, _ = extract_content(html, url)
    needs_browser, reasons = _needs_browser(html, text)

    if engine == "browser" or needs_browser:
        return await _browser_fetch(url)

    return result


async def batch_fetch(urls: list[str], concurrency: int = 5) -> list[FetchResult]:
    sem = asyncio.Semaphore(concurrency)

    async def _fetch_one(url: str) -> FetchResult:
        async with sem:
            return await smart_fetch(url)

    tasks = [_fetch_one(url) for url in urls]
    return await asyncio.gather(*tasks)
