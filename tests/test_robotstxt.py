import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from agentfetch.core.robotstxt import RobotsChecker


@pytest.mark.asyncio
async def test_robots_allowed_when_no_robots():
    checker = RobotsChecker()
    with patch.object(checker, "_fetch_robots", AsyncMock(return_value=None)):
        allowed = await checker.is_allowed("https://example.com/page")
        assert allowed is True


@pytest.mark.asyncio
async def test_robots_allowed_when_disallowed():
    from urllib.robotparser import RobotFileParser

    rp = RobotFileParser()
    rp.parse([f"User-agent: *", "Disallow: /"])
    checker = RobotsChecker()
    with patch.object(checker, "_fetch_robots", AsyncMock(return_value=rp)):
        allowed = await checker.is_allowed("https://example.com/page")
        assert allowed is False


@pytest.mark.asyncio
async def test_robots_allowed_when_allowed():
    from urllib.robotparser import RobotFileParser

    rp = RobotFileParser()
    rp.parse([f"User-agent: *", "Allow: /"])
    checker = RobotsChecker()
    with patch.object(checker, "_fetch_robots", AsyncMock(return_value=rp)):
        allowed = await checker.is_allowed("https://example.com/page")
        assert allowed is True


@pytest.mark.asyncio
async def test_crawl_delay():
    from urllib.robotparser import RobotFileParser

    rp = RobotFileParser()
    rp.parse([f"User-agent: *", "Crawl-delay: 5"])
    checker = RobotsChecker()
    with patch.object(checker, "_fetch_robots", AsyncMock(return_value=rp)):
        delay = await checker.crawl_delay("https://example.com/page")
        assert delay == 5


@pytest.mark.asyncio
async def test_crawl_delay_default():
    from urllib.robotparser import RobotFileParser

    rp = RobotFileParser()
    rp.parse([f"User-agent: *", "Allow: /"])
    checker = RobotsChecker()
    with patch.object(checker, "_fetch_robots", AsyncMock(return_value=rp)):
        delay = await checker.crawl_delay("https://example.com/page")
        assert delay == 0.0


@pytest.mark.asyncio
async def test_cache_hit():
    from urllib.robotparser import RobotFileParser

    rp = RobotFileParser()
    rp.parse([f"User-agent: *", "Allow: /"])
    checker = RobotsChecker()
    with patch.object(checker, "_fetch_robots", AsyncMock(return_value=rp)) as mock:
        await checker.is_allowed("https://example.com/page")
        await checker.is_allowed("https://example.com/other")
        assert mock.call_count == 1


def test_clear_cache():
    checker = RobotsChecker()
    checker._cache["example.com"] = (0.0, None)
    checker.clear_cache()
    assert len(checker._cache) == 0
