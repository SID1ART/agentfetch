import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from agentfetch.core.router import smart_fetch, batch_fetch
from agentfetch.core.schema import FetchResult


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

    async def slow_fetch(url):
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
    with patch("agentfetch.core.router._static_fetch") as mock_static:
        from agentfetch.core.extractor import extract_content

        text, _ = extract_content(html)
        mock_static.return_value = FetchResult(
            url="https://example.com/nextjs",
            content=text,
            confidence=1.0,
            render_mode="static",
        )

    from agentfetch.core.router import _needs_browser

    needs, reasons = _needs_browser(html, text)
    assert needs
    assert any("NEXT_DATA" in r for r in reasons)
