import json
import logging
import os
import sqlite3
import threading
import time
from typing import Optional

from .schema import CrawlResult

logger = logging.getLogger("agentfetch.crawl_store")

DB_PATH = os.environ.get("AGENTFETCH_CRAWL_DB", "agentfetch_crawl.db")
CRAWL_TTL = 86400

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute(
            """CREATE TABLE IF NOT EXISTS crawl_jobs (
                job_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )"""
        )
    return _local.conn


class CrawlStore:
    def __init__(self):
        self._memory: dict[str, CrawlResult] = {}
        self._use_sqlite = os.environ.get(
            "AGENTFETCH_CRAWL_DB"
        ) is not None or not os.environ.get("REDIS_URL")

    def store(self, job_id: str, result: CrawlResult):
        self._memory[job_id] = result
        if not self._use_sqlite:
            return
        try:
            conn = _get_conn()
            conn.execute(
                "INSERT OR REPLACE INTO crawl_jobs (job_id, data, created_at) VALUES (?, ?, ?)",
                (job_id, result.model_dump_json(), time.time()),
            )
            conn.commit()
            self._prune(conn)
        except Exception as e:
            logger.warning("SQLite store failed for %s: %s", job_id, e)

    def get(self, job_id: str) -> Optional[CrawlResult]:
        cached = self._memory.get(job_id)
        if cached is not None:
            return cached
        if not self._use_sqlite:
            return None
        try:
            conn = _get_conn()
            row = conn.execute(
                "SELECT data FROM crawl_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row:
                result = CrawlResult.model_validate_json(row["data"])
                self._memory[job_id] = result
                return result
        except Exception as e:
            logger.warning("SQLite read failed for %s: %s", job_id, e)
        return None

    def _prune(self, conn: sqlite3.Connection):
        cutoff = time.time() - CRAWL_TTL
        try:
            conn.execute("DELETE FROM crawl_jobs WHERE created_at < ?", (cutoff,))
            conn.commit()
        except Exception:
            pass

    def clear(self):
        self._memory.clear()
        if self._use_sqlite:
            try:
                conn = _get_conn()
                conn.execute("DELETE FROM crawl_jobs")
                conn.commit()
            except Exception:
                pass
