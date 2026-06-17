import pytest
from agentfetch.core.job_queue import JobQueue


def test_job_queue_disabled_by_default():
    assert JobQueue.is_available() is False


@pytest.mark.asyncio
async def test_enqueue_crawl_no_redis():
    job_id = await JobQueue.enqueue_crawl(
        url="https://example.com", max_depth=2, max_pages=10
    )
    assert job_id is not None
    assert isinstance(job_id, str)


@pytest.mark.asyncio
async def test_get_crawl_result_no_redis():
    result = await JobQueue.get_crawl_result("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_acquire_lock_no_redis():
    locked = await JobQueue.acquire_lock("test-job")
    assert locked is True


@pytest.mark.asyncio
async def test_release_lock_no_redis():
    await JobQueue.release_lock("test-job")
