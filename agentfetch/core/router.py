import asyncio
import json
import logging
import os
import random
import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional

import httpx

from .schema import FetchResult, ScrapeConfig
from .extractor import (
    extract_content,
    detect_content_type,
    extract_highlights,
    extract_structured,
)
from .sanitizer import sanitize
from .normalizer import normalize_url, extract_domain
from .robotstxt import RobotsChecker
from .proxymanager import ProxyManager

logger = logging.getLogger("agentfetch.router")

STATIC_TIMEOUT = int(os.environ.get("AGENTFETCH_STATIC_TIMEOUT", "15"))
BROWSER_TIMEOUT = int(os.environ.get("AGENTFETCH_BROWSER_TIMEOUT", "30"))
COOKIES_FILE = os.environ.get("AGENTFETCH_COOKIES_FILE", "")
MAX_RETRIES = int(os.environ.get("AGENTFETCH_MAX_RETRIES", "2"))
DOMAIN_DELAY = float(os.environ.get("AGENTFETCH_DOMAIN_DELAY", "0.5"))
ROBOTS_CHECK = os.environ.get("AGENTFETCH_ROBOTS_CHECK", "false").lower() == "true"
CACHE_SIZE = int(os.environ.get("AGENTFETCH_CACHE_SIZE", "100"))
CACHE_TTL = int(os.environ.get("AGENTFETCH_CACHE_TTL", "300"))

SPA_SHELL_PATTERNS = [
    "Loading...",
    "Please enable JavaScript",
    "You need to enable JavaScript",
    "enable JavaScript",
    "We're sorry",
]

MIN_PROSE_RATIO = float(os.environ.get("AGENTFETCH_MIN_PROSE_RATIO", "0.4"))
MIN_WORDS = int(os.environ.get("AGENTFETCH_MIN_WORDS", "10"))


class MemoryCache:
    def __init__(self, maxsize: int = 100, ttl: float = 300):
        self._maxsize = maxsize
        self._ttl = ttl
        self._store: OrderedDict[str, tuple[float, FetchResult]] = OrderedDict()

    def get(self, key: str) -> Optional[FetchResult]:
        if key not in self._store:
            return None
        ts, result = self._store[key]
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return result

    def put(self, key: str, result: FetchResult):
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (time.monotonic(), result)
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def clear(self):
        self._store.clear()


_memory_cache = MemoryCache(maxsize=CACHE_SIZE, ttl=CACHE_TTL)


def _validate_content(text: str) -> tuple[float, Optional[str]]:
    if not text or not text.strip():
        return 0.0, "extraction returned empty content"

    stripped = text.strip()
    words = stripped.split()
    text_lower = stripped.lower()

    reasons: list[str] = []

    for pattern in SPA_SHELL_PATTERNS:
        if pattern.lower() in text_lower:
            reasons.append(f"SPA shell text: '{pattern}'")
            break

    alpha_chars = sum(c.isalpha() for c in stripped)
    total_chars = len(stripped)
    prose_ratio = alpha_chars / max(total_chars, 1)
    if prose_ratio < MIN_PROSE_RATIO:
        reasons.append(f"low prose ratio ({prose_ratio:.2f})")

    if len(words) < MIN_WORDS:
        reasons.append(f"too few words ({len(words)})")

    sentence_endings = sum(1 for c in stripped if c in ".!?")
    if words and sentence_endings / max(len(words), 1) < 0.005 and len(words) > 20:
        reasons.append("no sentence structure")

    if not reasons:
        return 1.0, None

    penalty = min(len(reasons) * 0.25, 0.75)
    confidence = max(0.1, 1.0 - penalty)
    return confidence, "; ".join(reasons)


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
]

_domain_last_access: dict[str, float] = {}
_robots_checker: Optional[RobotsChecker] = None
_proxy_manager: Optional[ProxyManager] = None


def _get_robots() -> RobotsChecker:
    global _robots_checker
    if _robots_checker is None:
        _robots_checker = RobotsChecker()
    return _robots_checker


def _get_proxy_manager() -> ProxyManager:
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager


async def _domain_throttle(url: str, delay: Optional[float] = None):
    domain = extract_domain(url)
    now = time.monotonic()
    last = _domain_last_access.get(domain, 0.0)
    d = delay if delay is not None else DOMAIN_DELAY
    elapsed = now - last
    if elapsed < d:
        await asyncio.sleep(d - elapsed)
    _domain_last_access[domain] = time.monotonic()


def _is_retryable(error: str) -> bool:
    retryable_patterns = [
        "timeout",
        "connection refused",
        "connection reset",
        "connection aborted",
        "remote end closed",
        "temporarily unavailable",
        "too many requests",
        "503",
        "502",
        "429",
        "408",
        "name resolution error",
        "read timeout",
    ]
    lower = error.lower()
    return any(p in lower for p in retryable_patterns)


def _get_headers(custom_headers: Optional[dict[str, str]] = None) -> dict:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if custom_headers:
        headers.update(custom_headers)
    return headers


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
                    {"name": name, "value": value, "domain": domain, "path": path_str}
                )
        return jars
    except Exception as e:
        logger.warning("Failed to load cookies: %s", e)
        return []


CURL_CFFI_PROFILES = [
    "chrome99",
    "chrome101",
    "chrome104",
    "chrome107",
    "chrome110",
    "chrome116",
    "chrome119",
    "chrome120",
    "chrome123",
    "chrome124",
    "safari15_3",
    "safari17_0",
]

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


async def _curl_fetch_raw(
    url: str,
    config: ScrapeConfig,
    proxy: Optional[str] = None,
) -> Optional[str]:
    try:
        from curl_cffi.requests import AsyncSession

        profile = (
            config.ja3
            or os.environ.get("AGENTFETCH_JA3_PROFILE", "")
            or random.choice(CURL_CFFI_PROFILES)
        )
        session_kwargs = {"impersonate": profile}
        if proxy:
            session_kwargs["proxies"] = {"https": proxy, "http": proxy}
        async with AsyncSession(**session_kwargs) as session:
            resp = await session.get(
                url,
                headers=_get_headers(config.headers),
                timeout=STATIC_TIMEOUT,
            )
            return resp.text
    except ImportError:
        return None
    except Exception as e:
        logger.debug("curl_cffi fetch failed for %s: %s", url, e)
        return None


async def _fetch_with_retry(
    url: str,
    config: Optional[ScrapeConfig] = None,
) -> tuple[str, int, Optional[str]]:
    last_error = ""
    proxy_used = None
    config = config or ScrapeConfig()
    timeout = STATIC_TIMEOUT
    use_curl_cffi = True

    for attempt in range(1 + MAX_RETRIES):
        robots_delay = 0.0
        if ROBOTS_CHECK:
            robots_delay = await _get_robots().crawl_delay(url)
        await _domain_throttle(url, delay=max(DOMAIN_DELAY, robots_delay))

        proxy = config.proxy
        pm = None
        if not proxy:
            pm = _get_proxy_manager()
            if pm.is_enabled():
                proxy = await pm.get_proxy()

        try:
            if use_curl_cffi:
                html = await _curl_fetch_raw(url, config, proxy)
                if html is not None:
                    if proxy:
                        proxy_used = proxy
                        if pm:
                            await pm.mark_success(proxy)
                    return html, attempt, proxy_used
                use_curl_cffi = False
                logger.debug("curl_cffi unavailable for %s, falling back to httpx", url)

            client_kwargs = {
                "headers": _get_headers(config.headers),
                "timeout": timeout,
            }
            if proxy:
                client_kwargs["proxies"] = proxy

            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                if proxy:
                    proxy_used = proxy
                    if pm:
                        await pm.mark_success(proxy)
                return resp.text, attempt, proxy_used
        except Exception as e:
            last_error = str(e)
            if proxy and pm:
                await pm.mark_failed(proxy)
            if not _is_retryable(last_error) and attempt < MAX_RETRIES:
                logger.info("Non-retryable error for %s: %s", url, last_error)
                raise
            if attempt < MAX_RETRIES:
                wait = (2**attempt) + random.uniform(0, 0.5)
                logger.info(
                    "Retry %d/%d for %s after %.1fs (error: %s)",
                    attempt + 1,
                    MAX_RETRIES,
                    url,
                    wait,
                    last_error,
                )
                await asyncio.sleep(wait)
    raise Exception(last_error)


def _apply_post_extraction(result: FetchResult, config: ScrapeConfig):
    if config.extract_highlights:
        result.highlights = extract_highlights(result.content)
    if config.output_schema:
        result.structured_output = extract_structured(
            result.content, config.output_schema
        )
    return result


async def _static_fetch(
    url: str,
    config: Optional[ScrapeConfig] = None,
) -> tuple[FetchResult, str]:
    start = time.monotonic()
    retries = 0
    config = config or ScrapeConfig()
    proxy_used = None
    try:
        html, retries, proxy_used = await _fetch_with_retry(url, config)
    except Exception as e:
        return FetchResult(
            url=url,
            content="",
            confidence=0.0,
            error=str(e),
            latency_ms=int((time.monotonic() - start) * 1000),
            render_mode="static",
            retries=retries,
            normalized_url=normalize_url(url),
            proxy_used=proxy_used,
        ), ""
    text, extractor, citations = extract_content(html, url, config)
    text, injection_detected = sanitize(text, url)
    content_type = detect_content_type(html, url)
    title = _extract_title(html)
    latency = int((time.monotonic() - start) * 1000)
    wc = len(text.split())
    links = _extract_links(html) if config.scrape_links else None
    result = FetchResult(
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
        retries=retries,
        normalized_url=normalize_url(url),
        citations=citations if config.citation_links else None,
        proxy_used=proxy_used,
    )
    return result, html


async def _cloudflare_fetch(url: str, ja3: Optional[str] = None) -> Optional[str]:
    try:
        from curl_cffi.requests import AsyncSession

        profile = (
            ja3
            or os.environ.get("AGENTFETCH_JA3_PROFILE", "")
            or random.choice(CURL_CFFI_PROFILES)
        )
        async with AsyncSession(impersonate=profile) as session:
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


async def _try_cloudflare(
    url: str,
    config: Optional[ScrapeConfig] = None,
) -> Optional[FetchResult]:
    config = config or ScrapeConfig()
    html = await _cloudflare_fetch(url, ja3=config.ja3)
    if not html:
        return None
    config = config or ScrapeConfig()
    text, extractor, citations = extract_content(html, url, config)
    text, injection_detected = sanitize(text, url)
    if not text:
        return None
    content_type = detect_content_type(html, url)
    title = _extract_title(html)
    links = _extract_links(html) if config.scrape_links else None
    result = FetchResult(
        url=url,
        content=text,
        title=title,
        confidence=0.8,
        content_type=content_type,
        word_count=len(text.split()),
        render_mode="static",
        injection_detected=injection_detected,
        links=links,
        normalized_url=normalize_url(url),
        citations=citations if (config and config.citation_links) else None,
    )
    q_confidence, q_error = _validate_content(result.content)
    if q_confidence < result.confidence:
        result.confidence = q_confidence
        if q_error:
            result.error = (result.error + "; " if result.error else "") + q_error
    return result


async def _try_curl_cffi(
    url: str,
    config: Optional[ScrapeConfig] = None,
) -> Optional[FetchResult]:
    config = config or ScrapeConfig()
    try:
        from curl_cffi.requests import AsyncSession

        profile = (
            config.ja3
            or os.environ.get("AGENTFETCH_JA3_PROFILE", "")
            or random.choice(CURL_CFFI_PROFILES)
        )
        async with AsyncSession(impersonate=profile) as session:
            resp = await session.get(
                url, headers=_get_headers(config.headers), timeout=STATIC_TIMEOUT
            )
            html = resp.text
    except ImportError:
        return None
    except Exception as e:
        logger.debug("curl_cffi TLS fallback failed for %s: %s", url, e)
        return None

    if not html:
        return None

    text, extractor, citations = extract_content(html, url, config)
    text, injection_detected = sanitize(text, url)
    if not text:
        return None
    content_type = detect_content_type(html, url)
    title = _extract_title(html)
    links = _extract_links(html) if config.scrape_links else None
    result = FetchResult(
        url=url,
        content=text,
        title=title,
        confidence=0.8,
        content_type=content_type,
        word_count=len(text.split()),
        render_mode="bypass",
        injection_detected=injection_detected,
        links=links,
        normalized_url=normalize_url(url),
        citations=citations if config.citation_links else None,
    )
    q_confidence, q_error = _validate_content(result.content)
    if q_confidence < result.confidence:
        result.confidence = q_confidence
        if q_error:
            result.error = (result.error + "; " if result.error else "") + q_error
    return result


STEALTH_ENABLED = os.environ.get("AGENTFETCH_STEALTH", "true").lower() == "true"
STEALTH_BASIC_FALLBACK = (
    os.environ.get("AGENTFETCH_STEALTH_BASIC_FALLBACK", "true").lower() == "true"
)


FINGERPRINT_PROFILES = [
    {
        "viewport": {"width": 1920, "height": 1080},
        "locale": "en-US",
        "timezone_id": "America/New_York",
    },
    {
        "viewport": {"width": 1536, "height": 864},
        "locale": "en-US",
        "timezone_id": "America/Chicago",
    },
    {
        "viewport": {"width": 1440, "height": 900},
        "locale": "en-GB",
        "timezone_id": "Europe/London",
    },
    {
        "viewport": {"width": 1512, "height": 982},
        "locale": "en-CA",
        "timezone_id": "America/Toronto",
    },
    {
        "viewport": {"width": 1920, "height": 1080},
        "locale": "en-US",
        "timezone_id": "America/Los_Angeles",
    },
    {
        "viewport": {"width": 1366, "height": 768},
        "locale": "en-AU",
        "timezone_id": "Australia/Sydney",
    },
    {
        "viewport": {"width": 2560, "height": 1440},
        "locale": "en-US",
        "timezone_id": "America/New_York",
    },
    {
        "viewport": {"width": 1280, "height": 720},
        "locale": "en-IN",
        "timezone_id": "Asia/Kolkata",
    },
]


def _pick_fingerprint(config_viewport: Optional[dict] = None) -> dict:
    profile = random.choice(FINGERPRINT_PROFILES).copy()
    if config_viewport:
        profile["viewport"] = config_viewport
    return profile


def _stealth_init_script() -> str:
    return """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    window.chrome = { runtime: {} };
    """


async def _execute_actions(
    page, actions: list, base_url: str = ""
) -> None:
    from urllib.parse import urljoin

    for i, action in enumerate(actions):
        try:
            if action.type == "click":
                if action.selector:
                    await page.wait_for_selector(
                        action.selector, timeout=action.timeout
                    )
                    await page.click(action.selector)
                    logger.debug(
                        "Action %d: clicked '%s' on %s", i, action.selector, base_url
                    )

            elif action.type == "scroll":
                if action.selector:
                    await page.wait_for_selector(
                        action.selector, timeout=action.timeout
                    )
                    await page.evaluate(
                        f"document.querySelector('{action.selector}').scrollIntoView({{behavior: 'smooth', block: 'center'}})"
                    )
                elif action.value and action.value == "bottom":
                    await page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight)"
                    )
                elif action.value and action.value == "top":
                    await page.evaluate("window.scrollTo(0, 0)")
                else:
                    await page.evaluate(
                        f"window.scrollBy(0, {action.value or 500})"
                    )
                await page.wait_for_timeout(300)
                logger.debug("Action %d: scrolled on %s", i, base_url)

            elif action.type == "type":
                if action.selector and action.value is not None:
                    await page.wait_for_selector(
                        action.selector, timeout=action.timeout
                    )
                    await page.fill(action.selector, action.value)
                    logger.debug(
                        "Action %d: typed into '%s' on %s",
                        i,
                        action.selector,
                        base_url,
                    )

            elif action.type == "wait":
                ms = int(action.value) if action.value else 1000
                await page.wait_for_timeout(ms)
                logger.debug("Action %d: waited %dms on %s", i, ms, base_url)

            elif action.type == "press":
                key = action.value or "Enter"
                if action.selector:
                    await page.wait_for_selector(
                        action.selector, timeout=action.timeout
                    )
                    await page.press(action.selector, key)
                else:
                    await page.keyboard.press(key)
                logger.debug(
                    "Action %d: pressed '%s' on %s", i, key, base_url
                )

            elif action.type == "select":
                if action.selector and action.value is not None:
                    await page.wait_for_selector(
                        action.selector, timeout=action.timeout
                    )
                    await page.select_option(
                        action.selector, action.value
                    )
                    logger.debug(
                        "Action %d: selected '%s' in '%s' on %s",
                        i,
                        action.value,
                        action.selector,
                        base_url,
                    )

            elif action.type == "screenshot":
                logger.debug(
                    "Action %d: screenshot triggered mid-flow on %s",
                    i,
                    base_url,
                )

        except Exception as e:
            logger.warning(
                "Action %d (%s) failed on %s: %s",
                i,
                action.type,
                base_url,
                e,
            )


async def _browser_fetch(
    url: str,
    config: Optional[ScrapeConfig] = None,
) -> FetchResult:
    start = time.monotonic()
    config = config or ScrapeConfig()
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return FetchResult(
            url=url,
            content="",
            confidence=0.0,
            error="Playwright not installed. Install with: pip install agentfetch[browser]",
            latency_ms=int((time.monotonic() - start) * 1000),
            render_mode="browser",
            normalized_url=normalize_url(url),
        )
    screenshot_data = None
    try:
        cookies = config.cookies or _load_cookies()
        fp = _pick_fingerprint(config.viewport)
        ua = random.choice(USER_AGENTS)

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
                user_agent=ua,
                viewport=fp["viewport"],
                locale=fp["locale"],
                timezone_id=fp["timezone_id"],
            )

            await context.add_init_script(_stealth_init_script())

            if config.stealth and STEALTH_ENABLED:
                try:
                    from playwright_stealth import Stealth

                    Stealth(context)
                    logger.debug("playwright-stealth applied for %s", url)
                except ImportError:
                    logger.debug(
                        "playwright-stealth not installed, using basic stealth"
                    )

            if cookies:
                await context.add_cookies(cookies)

            page = await context.new_page()
            await page.goto(
                url, wait_until="networkidle", timeout=BROWSER_TIMEOUT * 1000
            )

            if config.wait_for:
                try:
                    await page.wait_for_selector(config.wait_for, timeout=5000)
                except Exception:
                    logger.debug(
                        "wait_for selector '%s' not found on %s", config.wait_for, url
                    )

            if config.js_wait_ms:
                await page.wait_for_timeout(config.js_wait_ms)

            if config.actions:
                await _execute_actions(page, config.actions, base_url=url)

            if config.screenshot:
                screenshot_bytes = await page.screenshot(
                    full_page=True, type="png"
                )
                import base64

                screenshot_data = base64.b64encode(screenshot_bytes).decode("utf-8")

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
            normalized_url=normalize_url(url),
        )

    text, extractor, citations = extract_content(html, url, config)
    text, injection_detected = sanitize(text, url)
    content_type = detect_content_type(html, url)
    title = _extract_title(html)
    latency = int((time.monotonic() - start) * 1000)
    wc = len(text.split())
    links = _extract_links(html) if config.scrape_links else None

    confidence = 1.0
    confidence -= 0.2
    if extractor not in ("trafilatura", ""):
        confidence -= 0.3
    confidence = max(0.1, confidence)

    result = FetchResult(
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
        normalized_url=normalize_url(url),
        citations=citations if (config and config.citation_links) else None,
        screenshot_data=screenshot_data,
    )
    return result


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


CATEGORY_ROUTES = {
    "article": {"engine": "auto", "confidence_floor": 0.5},
    "news": {"engine": "auto", "confidence_floor": 0.4},
    "company": {"engine": "auto", "confidence_floor": 0.3},
    "people": {"engine": "browser", "confidence_floor": 0.2},
    "research_paper": {"engine": "auto", "confidence_floor": 0.4},
    "personal_site": {"engine": "auto", "confidence_floor": 0.4},
    "docs": {"engine": "static", "confidence_floor": 0.6},
    "product": {"engine": "auto", "confidence_floor": 0.3},
    "listing": {"engine": "static", "confidence_floor": 0.3},
    "financial_report": {"engine": "auto", "confidence_floor": 0.4},
}


async def smart_fetch(
    url: str,
    engine: str = "auto",
    use_cache: bool = True,
    cache_ttl: int = 3600,
    cookies: Optional[list[dict]] = None,
    config: Optional[ScrapeConfig] = None,
) -> FetchResult:
    raw_url = url
    url = normalize_url(url)
    config = config or ScrapeConfig()
    confidence_floor = 0.0
    if config.category != "auto" and config.category in CATEGORY_ROUTES:
        route = CATEGORY_ROUTES[config.category]
        if engine == "auto":
            engine = route.get("engine", "auto")
        confidence_floor = route.get("confidence_floor", 0.0)

    if use_cache:
        ck = _cache_key(url, config)
        cached = _memory_cache.get(ck)
        if cached is not None:
            cached.cached = True
            if config:
                _apply_post_extraction(cached, config)
            return cached

    if cookies:
        config.cookies = cookies

    if ROBOTS_CHECK:
        robots = _get_robots()
        allowed = await robots.is_allowed(url)
        if not allowed:
            return FetchResult(
                url=url,
                content="",
                confidence=0.0,
                error=f"Blocked by robots.txt: {url}",
                robots_allowed=False,
                normalized_url=url,
            )

    if engine == "browser":
        tls_result = await _try_curl_cffi(url, config)
        if tls_result and tls_result.content:
            tls_result.render_mode = "bypass"
            _quality_and_cache(
                url,
                tls_result,
                confidence_floor=confidence_floor,
                config=config,
                do_cache=use_cache,
            )
            return tls_result
        stealth_result = await _browser_fetch(url, config)
        if not stealth_result.content and config.stealth and STEALTH_BASIC_FALLBACK:
            basic_config = config.model_copy(update={"stealth": False})
            logger.info("Stealth browser failed for %s, trying basic browser", url)
            basic_result = await _browser_fetch(url, basic_config)
            _quality_and_cache(
                url,
                basic_result,
                confidence_floor=confidence_floor,
                config=config,
                do_cache=use_cache,
            )
            return basic_result
        _quality_and_cache(
            url,
            stealth_result,
            confidence_floor=confidence_floor,
            config=config,
            do_cache=use_cache,
        )
        return stealth_result

    if _is_static_url(url):
        result, _ = await _static_fetch(url, config)
        result.render_mode = "static"
        _quality_and_cache(
            url,
            result,
            confidence_floor=confidence_floor,
            config=config,
            do_cache=use_cache,
        )
        return result

    result, html = await _static_fetch(url, config)

    if engine == "static":
        _quality_and_cache(
            url,
            result,
            confidence_floor=confidence_floor,
            config=config,
            do_cache=use_cache,
        )
        return result

    is_403 = result.error and (
        "403" in result.error or "forbidden" in result.error.lower()
    )
    if result.error and not is_403:
        _quality_and_cache(
            url,
            result,
            confidence_floor=confidence_floor,
            config=config,
            do_cache=use_cache,
        )
        return result

    if not html:
        _quality_and_cache(
            url,
            result,
            confidence_floor=confidence_floor,
            config=config,
            do_cache=use_cache,
        )
        return result

    if _is_cloudflare(html):
        logger.info("Cloudflare detected for %s, trying bypass", url)
        cf_result = await _try_cloudflare(url, config)
        if cf_result and cf_result.content:
            cf_result.render_mode = "static"
            _quality_and_cache(
                url,
                cf_result,
                confidence_floor=confidence_floor,
                config=config,
                do_cache=use_cache,
            )
            return cf_result
        logger.info(
            "Cloudflare bypass failed for %s, falling through to TLS fallback", url
        )

    text, _, _ = extract_content(html, url, config)
    needs_browser, reasons = _needs_browser(html, text)

    if needs_browser or is_403:
        tls_result = await _try_curl_cffi(url, config)
        if tls_result and tls_result.content:
            tls_result.render_mode = "bypass"
            _quality_and_cache(
                url,
                tls_result,
                confidence_floor=confidence_floor,
                config=config,
                do_cache=use_cache,
            )
            return tls_result
        stealth_result = await _browser_fetch(url, config)
        if not stealth_result.content and config.stealth and STEALTH_BASIC_FALLBACK:
            basic_config = config.model_copy(update={"stealth": False})
            logger.info("Stealth browser failed for %s, trying basic browser", url)
            basic_result = await _browser_fetch(url, basic_config)

            _quality_and_cache(
                url,
                basic_result,
                confidence_floor=confidence_floor,
                config=config,
                do_cache=use_cache,
            )
            return basic_result
        _quality_and_cache(
            url,
            stealth_result,
            confidence_floor=confidence_floor,
            config=config,
            do_cache=use_cache,
        )
        return stealth_result

    if _is_static_url(url):
        result, _ = await _static_fetch(url, config)
        result.render_mode = "static"
        _quality_and_cache(
            url,
            result,
            confidence_floor=confidence_floor,
            config=config,
            do_cache=use_cache,
        )
        return result

    result, html = await _static_fetch(url, config)

    if engine == "static":
        _quality_and_cache(
            url,
            result,
            confidence_floor=confidence_floor,
            config=config,
            do_cache=use_cache,
        )
        return result

    is_403 = result.error and (
        "403" in result.error or "forbidden" in result.error.lower()
    )
    if result.error and not is_403:
        _quality_and_cache(
            url,
            result,
            confidence_floor=confidence_floor,
            config=config,
            do_cache=use_cache,
        )
        return result

    if not html:
        _quality_and_cache(
            url,
            result,
            confidence_floor=confidence_floor,
            config=config,
            do_cache=use_cache,
        )
        return result

    if _is_cloudflare(html):
        logger.info("Cloudflare detected for %s, trying bypass", url)
        cf_result = await _try_cloudflare(url, config)
        if cf_result and cf_result.content:
            cf_result.render_mode = "static"
            _quality_and_cache(
                url,
                cf_result,
                confidence_floor=confidence_floor,
                config=config,
                do_cache=use_cache,
            )
            return cf_result
        logger.info(
            "Cloudflare bypass failed for %s, falling through to TLS fallback", url
        )

    text, _, _ = extract_content(html, url, config)
    needs_browser, reasons = _needs_browser(html, text)

    if needs_browser or is_403:
        tls_result = await _try_curl_cffi(url, config)
        if tls_result and tls_result.content:
            tls_result.render_mode = "bypass"
            _quality_and_cache(
                url,
                tls_result,
                confidence_floor=confidence_floor,
                config=config,
                do_cache=use_cache,
            )
            return tls_result
        logger.info("curl_cffi TLS fallback failed for %s, trying browser", url)
        stealth_result = await _browser_fetch(url, config)
        if not stealth_result.content and config.stealth and STEALTH_BASIC_FALLBACK:
            basic_config = config.model_copy(update={"stealth": False})
            logger.info("Stealth browser failed for %s, trying basic browser", url)
            basic_result = await _browser_fetch(url, basic_config)

            _quality_and_cache(
                url,
                basic_result,
                confidence_floor=confidence_floor,
                config=config,
                do_cache=use_cache,
            )
            return basic_result
        _quality_and_cache(
            url,
            stealth_result,
            confidence_floor=confidence_floor,
            config=config,
            do_cache=use_cache,
        )
        return stealth_result

    _quality_and_cache(
        url,
        result,
        confidence_floor=confidence_floor,
        config=config,
        do_cache=use_cache,
    )
    return result


async def batch_fetch(
    urls: list[str],
    concurrency: int = 5,
    config: Optional[ScrapeConfig] = None,
) -> list[FetchResult]:
    normalized = [normalize_url(u) for u in urls]
    sem = asyncio.Semaphore(concurrency)

    async def _fetch_one(url: str) -> FetchResult:
        async with sem:
            return await smart_fetch(url, config=config)

    tasks = [_fetch_one(url) for url in normalized]
    return await asyncio.gather(*tasks)


def _cache_key(url: str, config: Optional[ScrapeConfig] = None) -> str:
    if config and (config.extract_highlights or config.output_schema):
        schema_hash = hash(
            json.dumps(config.output_schema, sort_keys=True)
            if config.output_schema
            else 0
        )
        return f"{url}|hl={config.extract_highlights}|sh={schema_hash}"
    return url


def _quality_and_cache(
    url: str,
    result: FetchResult,
    confidence_floor: float = 0.0,
    config: Optional[ScrapeConfig] = None,
    do_cache: bool = True,
):
    if config:
        _apply_post_extraction(result, config)
    q_confidence, q_error = _validate_content(result.content)
    if q_confidence < result.confidence:
        result.confidence = q_confidence
        if q_error:
            result.error = (result.error + "; " if result.error else "") + q_error
    if confidence_floor > 0 and result.confidence < confidence_floor:
        result.confidence = confidence_floor
    if do_cache:
        _memory_cache.put(_cache_key(url, config), result)
