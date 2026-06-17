import asyncio
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Optional

import httpx

from .schema import FetchResult
from .extractor import extract_content, detect_content_type
from .sanitizer import sanitize

logger = logging.getLogger("agentfetch.router")

STATIC_TIMEOUT = int(os.environ.get("AGENTFETCH_STATIC_TIMEOUT", "15"))
BROWSER_TIMEOUT = int(os.environ.get("AGENTFETCH_BROWSER_TIMEOUT", "30"))
COOKIES_FILE = os.environ.get("AGENTFETCH_COOKIES_FILE", "")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
]


def _get_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def _load_cookies() -> list[dict]:
    if not COOKIES_FILE:
        return []
    path = Path(COOKIES_FILE)
    if not path.exists():
        logger.warning("Cookies file not found: %s", COOKIES_FILE)
        return []
    try:
        raw = path.read_text()
        if COOKIES_FILE.endswith(".json"):
            return json.loads(raw)
        jars = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, _, path_str, secure, expires, name, value = parts[:7]
                jars.append(
                    {
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": path_str,
                    }
                )
        return jars
    except Exception as e:
        logger.warning("Failed to load cookies: %s", e)
        return []


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
        async with httpx.AsyncClient(
            headers=_get_headers(), timeout=STATIC_TIMEOUT
        ) as client:
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


async def _cloudflare_fetch(url: str) -> Optional[str]:
    try:
        from curl_cffi.requests import AsyncSession

        async with AsyncSession(impersonate="chrome124") as session:
            resp = await session.get(
                url, headers=_get_headers(), timeout=STATIC_TIMEOUT
            )
            return resp.text
    except ImportError:
        logger.debug("curl_cffi not installed, skipping Cloudflare bypass")
        return None
    except Exception as e:
        logger.warning("curl_cffi fetch failed for %s: %s", url, e)
        return None


async def _try_cloudflare(url: str) -> Optional[FetchResult]:
    html = await _cloudflare_fetch(url)
    if not html:
        return None
    text, extractor = extract_content(html, url)
    text, injection_detected = sanitize(text, url)
    if not text:
        return None
    content_type = detect_content_type(html, url)
    title = _extract_title(html)
    links = _extract_links(html)
    return FetchResult(
        url=url,
        content=text,
        title=title,
        confidence=0.8,
        content_type=content_type,
        word_count=len(text.split()),
        render_mode="static",
        injection_detected=injection_detected,
        links=links,
    )


async def _browser_fetch(url: str) -> FetchResult:
    start = time.monotonic()
    try:
        from playwright.async_api import async_playwright

        cookies = _load_cookies()

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-web-security",
                    "--no-sandbox",
                ],
            )
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
            )

            if cookies:
                await context.add_cookies(cookies)

            page = await context.new_page()

            await page.goto(
                url, wait_until="networkidle", timeout=BROWSER_TIMEOUT * 1000
            )

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
    return m.group(1).strip() if m else None


def _extract_links(html: str) -> list[str]:
    return re.findall(r'href=["\'](https?://[^"\']+)["\']', html)


def _is_static_url(url: str) -> bool:
    path = url.split("?")[0].split("#")[0]
    return any(path.endswith(ext) for ext in STATIC_EXTENSIONS)


def _is_cloudflare(html: str) -> bool:
    checks = [
        "cf-browser-verification",
        "cf-challenge",
        "cf-wrapper",
        "__cf_challenge",
        "cloudflare",
        "Checking your browser",
        "Just a moment",
    ]
    return any(c in html.lower() for c in checks)


async def smart_fetch(
    url: str,
    engine: str = "auto",
    use_cache: bool = True,
    cache_ttl: int = 3600,
    cookies: Optional[list[dict]] = None,
) -> FetchResult:
    if cookies:
        global COOKIES_FILE
        tmp_file = Path(f"/tmp/agentfetch_cookies_{int(time.time())}.json")
        tmp_file.write_text(json.dumps(cookies))
        COOKIES_FILE = str(tmp_file)

    if _is_static_url(url):
        result = await _static_fetch(url)
        result.render_mode = "static"
        return result

    result = await _static_fetch(url)
    if result.error:
        return result

    html = ""
    get_url = url
    try:
        async with httpx.AsyncClient(
            headers=_get_headers(), timeout=STATIC_TIMEOUT
        ) as client:
            resp = await client.get(get_url, follow_redirects=True)
            html = resp.text
    except Exception:
        html = ""

    if not html:
        return result

    if _is_cloudflare(html):
        logger.info("Cloudflare detected for %s, trying bypass", url)
        cf_result = await _try_cloudflare(url)
        if cf_result and cf_result.content:
            cf_result.render_mode = "static"
            return cf_result
        logger.info("Cloudflare bypass failed for %s, falling through to browser", url)

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
