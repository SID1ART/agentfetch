import asyncio
import json
import logging
import os
import random
from typing import Optional

logger = logging.getLogger("agentfetch.proxymanager")


class ProxyManager:
    def __init__(self):
        self._proxies: list[str] = []
        self._index: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()
        self._failed: dict[str, int] = {}
        self._max_failures = 3
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        raw = os.environ.get("AGENTFETCH_PROXY_LIST", "")
        if not raw:
            self._loaded = True
            return
        if (
            raw.startswith("http://")
            or raw.startswith("socks")
            or raw.startswith("https://")
        ):
            self._proxies = [p.strip() for p in raw.split(",") if p.strip()]
        else:
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    self._proxies = [
                        p.strip() for p in data if isinstance(p, str) and p.strip()
                    ]
                elif isinstance(data, dict):
                    self._proxies = (
                        [data.get("url", "").strip()] if data.get("url") else []
                    )
            except (json.JSONDecodeError, ValueError):
                self._proxies = [raw]

        if self._proxies:
            logger.info("Loaded %d proxies", len(self._proxies))
        else:
            logger.debug("No proxies configured")
        self._loaded = True

    def is_enabled(self) -> bool:
        self._ensure_loaded()
        return len(self._proxies) > 0

    async def get_proxy(self) -> Optional[str]:
        self._ensure_loaded()
        if not self._proxies:
            return None

        async with self._lock:
            valid = [
                p for p in self._proxies if self._failed.get(p, 0) < self._max_failures
            ]
            if not valid:
                logger.warning("All proxies exhausted, resetting failure counts")
                self._failed.clear()
                valid = self._proxies.copy()

            strategy = os.environ.get("AGENTFETCH_PROXY_STRATEGY", "round-robin")
            if strategy == "random":
                proxy = random.choice(valid)
            else:
                proxy = valid[self._index % len(valid)]
                self._index = (self._index + 1) % len(valid)

            return proxy

    async def mark_failed(self, proxy: str) -> None:
        async with self._lock:
            self._failed[proxy] = self._failed.get(proxy, 0) + 1
            logger.debug(
                "Proxy %s failed (%d/%d)",
                proxy,
                self._failed[proxy],
                self._max_failures,
            )

    async def mark_success(self, proxy: str) -> None:
        async with self._lock:
            self._failed.pop(proxy, None)

    def get_all(self) -> list[str]:
        self._ensure_loaded()
        return self._proxies.copy()

    def count(self) -> int:
        self._ensure_loaded()
        return len(self._proxies)
