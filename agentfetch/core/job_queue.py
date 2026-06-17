import asyncio
import json
import logging
import os
import time
import uuid
from typing import Optional

from .schema import CrawlResult, FetchResult

logger = logging.getLogger("agentfetch.job_queue")

REDIS_URL = os.environ.get("REDIS_URL", "")
CRAWL_QUEUE_KEY = "agentfetch:crawl_queue"
CRAWL_RESULT_PREFIX = "agentfetch:crawl_result:"
CRAWL_LOCK_PREFIX = "agentfetch:crawl_lock:"
CRAWL_TTL = 86400

redis_client = None
if REDIS_URL:
    try:
        import redis as redis_lib

        redis_client = redis_lib.from_url(REDIS_URL)
        logger.info("Redis connected for job queue")
    except Exception as e:
        logger.warning("Redis not available for job queue: %s", e)


class JobQueue:
    @staticmethod
    async def enqueue_crawl(
        url: str, max_depth: int = 3, max_pages: int = 20, query: str = ""
    ) -> str:
        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            "url": url,
            "max_depth": max_depth,
            "max_pages": max_pages,
            "query": query,
            "created_at": time.time(),
        }
        if redis_client:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: redis_client.lpush(CRAWL_QUEUE_KEY, json.dumps(job))
                )
                logger.info("Enqueued crawl job %s for %s", job_id, url)
            except Exception as e:
                logger.warning("Failed to enqueue crawl job: %s", e)
        return job_id

    @staticmethod
    async def dequeue_crawl(timeout: int = 5) -> Optional[dict]:
        if not redis_client:
            return None
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: redis_client.brpop(CRAWL_QUEUE_KEY, timeout=timeout)
            )
            if result:
                return json.loads(result[1])
        except Exception as e:
            logger.warning("Failed to dequeue crawl job: %s", e)
        return None

    @staticmethod
    async def store_crawl_result(job_id: str, result: CrawlResult) -> None:
        if not redis_client:
            return
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: redis_client.setex(
                    f"{CRAWL_RESULT_PREFIX}{job_id}",
                    CRAWL_TTL,
                    result.model_dump_json(),
                ),
            )
        except Exception as e:
            logger.warning("Failed to store crawl result: %s", e)

    @staticmethod
    async def get_crawl_result(job_id: str) -> Optional[CrawlResult]:
        if not redis_client:
            return None
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, lambda: redis_client.get(f"{CRAWL_RESULT_PREFIX}{job_id}")
            )
            if data:
                return CrawlResult.model_validate_json(data)
        except Exception as e:
            logger.warning("Failed to get crawl result: %s", e)
        return None

    @staticmethod
    async def acquire_lock(job_id: str, ttl: int = 300) -> bool:
        if not redis_client:
            return True
        try:
            loop = asyncio.get_event_loop()
            locked = await loop.run_in_executor(
                None,
                lambda: redis_client.set(
                    f"{CRAWL_LOCK_PREFIX}{job_id}",
                    "1",
                    nx=True,
                    ex=ttl,
                ),
            )
            return bool(locked)
        except Exception as e:
            logger.warning("Failed to acquire lock: %s", e)
            return True

    @staticmethod
    async def release_lock(job_id: str) -> None:
        if not redis_client:
            return
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: redis_client.delete(f"{CRAWL_LOCK_PREFIX}{job_id}")
            )
        except Exception as e:
            logger.warning("Failed to release lock: %s", e)

    @staticmethod
    def is_available() -> bool:
        return redis_client is not None


async def crawl_worker():
    logger.info("Crawl worker started")
    while True:
        job = await JobQueue.dequeue_crawl(timeout=5)
        if not job:
            continue

        job_id = job["job_id"]
        if not await JobQueue.acquire_lock(job_id):
            continue

        try:
            from ..api.routes import _run_crawl
            from ..api.routes import CrawlRequest

            req = CrawlRequest(
                url=job["url"],
                max_depth=job.get("max_depth", 3),
                max_pages=job.get("max_pages", 20),
                query=job.get("query", ""),
            )
            logger.info("Worker processing crawl job %s for %s", job_id, job["url"])
            await _run_crawl(job_id, req)
        except Exception as e:
            logger.exception("Crawl worker failed for job %s: %s", job_id, e)
        finally:
            await JobQueue.release_lock(job_id)
