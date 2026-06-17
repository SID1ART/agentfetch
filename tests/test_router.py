import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from agentfetch.core.router import (
    smart_fetch,
    batch_fetch,
    _is_static_url,
    _needs_browser,
    _is_retryable,
)
from agentfetch.core.schema import FetchResult, ScrapeConfig


def test_is_static_url():
    assert _is_static_url("https://example.com/file.txt") is True
    assert _is_static_url("https://example.com/file.md") is True
    assert _is_static_url("https://example.com/file.json") is True
    assert _is_static_url("https://example.com/page.html") is False
    assert _is_static_url("https://example.com/") is False


def test_needs_browser_empty_extraction():
    html = "<html><body>test</body></html>"
    needs, reasons = _needs_browser(html, "")
    assert needs is True
    assert "extraction returned empty" in reasons


def test_needs_browser_short_text():
    html = "<html><body>test</body></html>"
    needs, reasons = _needs_browser(html, "short")
    assert needs is True
    assert any("too short" in r for r in reasons)


def test_needs_browser_js_markers():
    html = '<html><body><div id="__NEXT_DATA__">test</div></body></html>'
    needs, reasons = _needs_browser(html, "some longer text here for testing purposes")
    assert needs is True


def test_needs_browser_not_needed():
    html = "<html><body><p>" + "long content here. " * 20 + "</p></body></html>"
    text = "long content here. " * 20
    needs, reasons = _needs_browser(html, text)
    assert needs is False, f"reasons: {reasons}"


def test_is_retryable():
    assert _is_retryable("timeout error") is True
    assert _is_retryable("connection refused") is True
    assert _is_retryable("429 too many requests") is True
    assert _is_retryable("503 service unavailable") is True
    assert _is_retryable("404 not found") is False
    assert _is_retryable("invalid URL") is False


@pytest.mark.asyncio
async def test_static_url_returns_static_mode():
    with patch("agentfetch.core.router._static_fetch") as mock_static:
        mock_static.return_value = FetchResult(
            url="https://example.com/file.txt",
            content="hello",
            confidence=0.9,
            render_mode="static",
        )
        result = await smart_fetch("https://example.com/file.txt")
        assert result.render_mode == "static"


@pytest.mark.asyncio
async def test_errors_return_fetch_result_not_exception():
    with patch("agentfetch.core.router._static_fetch") as mock_static:
        mock_static.return_value = FetchResult(
            url="https://example.com/error",
            content="",
            confidence=0.0,
            error="Connection error",
        )
        result = await smart_fetch("https://example.com/error")
        assert isinstance(result, FetchResult)
        assert result.error is not None
        assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_batch_fetch_respects_concurrency():
    called = []

    async def slow_fetch(url, **kwargs):
        called.append(url)
        return FetchResult(url=url, content="ok", confidence=1.0)

    with patch("agentfetch.core.router.smart_fetch", side_effect=slow_fetch):
        urls = [f"https://example.com/{i}" for i in range(10)]
        results = await batch_fetch(urls, concurrency=5)
        assert len(results) == 10
        assert all(isinstance(r, FetchResult) for r in results)


@pytest.mark.asyncio
async def test_js_markers_route_to_browser():
    html = "<html><body>__NEXT_DATA__</body></html>"

    from agentfetch.core.router import _needs_browser

    needs, reasons = _needs_browser(html, "")
    assert needs
    assert any("NEXT_DATA" in r for r in reasons)


@pytest.mark.asyncio
async def test_smart_fetch_with_scrape_config():
    config = ScrapeConfig(scrape_links=False, max_content_length=100)
    with patch("agentfetch.core.router._static_fetch") as mock_static:
        mock_static.return_value = FetchResult(
            url="https://example.com",
            content="test content",
            title="Test",
            confidence=1.0,
            content_type="unknown",
            word_count=2,
            render_mode="static",
            latency_ms=0,
            injection_detected=False,
            links=None,
            retries=0,
            normalized_url="https://example.com",
        )
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.side_effect = Exception("mock network closed")
            result = await smart_fetch("https://example.com", config=config)
            assert result.content == "test content"
