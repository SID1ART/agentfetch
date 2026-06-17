import asyncio
import logging
import time
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .normalizer import extract_domain

logger = logging.getLogger("agentfetch.robotstxt")

USER_AGENT = "agentfetch/1.0"
CACHE_TTL = 3600


class RobotsChecker:
    def __init__(self):
        self._cache: dict[str, tuple[float, Optional[RobotFileParser]]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def is_allowed(self, url: str) -> bool:
        domain = extract_domain(url)
        parser = await self._get_parser(domain)
        if parser is None:
            return True
        return parser.can_fetch(USER_AGENT, url)

    async def crawl_delay(self, url: str) -> float:
        domain = extract_domain(url)
        parser = await self._get_parser(domain)
        if parser is None:
            return 0.0
        return parser.crawl_delay(USER_AGENT) or 0.0

    async def site_maps(self, url: str) -> list[str]:
        domain = extract_domain(url)
        parser = await self._get_parser(domain)
        if parser is None:
            return []
        return parser.site_maps() or []

    async def _get_parser(self, domain: str) -> Optional[RobotFileParser]:
        now = time.monotonic()
        if domain in self._cache:
            ts, parser = self._cache[domain]
            if now - ts < CACHE_TTL:
                return parser

        async with self._lock:
            if domain in self._cache:
                ts, parser = self._cache[domain]
                if now - ts < CACHE_TTL:
                    return parser

            parser = await self._fetch_robots(domain)
            self._cache[domain] = (time.monotonic(), parser)
            return parser

    async def _fetch_robots(self, domain: str) -> Optional[RobotFileParser]:
        robots_url = f"https://{domain}/robots.txt"
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(robots_url)
                if resp.status_code == 200:
                    rp = RobotFileParser()
                    rp.parse(resp.text.splitlines())
                    logger.info("Fetched robots.txt for %s", domain)
                    return rp
                else:
                    logger.debug(
                        "robots.txt not found for %s (status=%d)",
                        domain,
                        resp.status_code,
                    )
                    return None
        except Exception as e:
            logger.warning("Failed to fetch robots.txt for %s: %s", domain, e)
            return None

    def clear_cache(self) -> None:
        self._cache.clear()
