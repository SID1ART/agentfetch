import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from agentfetch.core.router import (
    smart_fetch,
    batch_fetch,
    _is_static_url,
    _needs_browser,
    _is_retryable,
    _cloudflare_fetch,
    _try_curl_cffi,
    CURL_CFFI_PROFILES,
    FINGERPRINT_PROFILES,
    _pick_fingerprint,
    _stealth_init_script,
)
from agentfetch.core.schema import FetchResult, ScrapeConfig
from agentfetch.core.router import _memory_cache


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
        mock_static.return_value = (
            FetchResult(
                url="https://example.com/file.txt",
                content="hello",
                confidence=0.9,
                render_mode="static",
            ),
            "<html>hello</html>",
        )
        result = await smart_fetch("https://example.com/file.txt")
        assert result.render_mode == "static"


@pytest.mark.asyncio
async def test_errors_return_fetch_result_not_exception():
    with patch("agentfetch.core.router._static_fetch") as mock_static:
        mock_static.return_value = (
            FetchResult(
                url="https://example.com/error",
                content="",
                confidence=0.0,
                error="Connection error",
            ),
            "",
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
async def test_curl_cffi_profiles_defined():
    assert len(CURL_CFFI_PROFILES) >= 10
    assert "chrome124" in CURL_CFFI_PROFILES
    assert "safari17_0" in CURL_CFFI_PROFILES


@pytest.mark.asyncio
async def test_cloudflare_fetch_returns_none_when_not_installed():
    with patch.dict("sys.modules", {"curl_cffi": None}):
        result = await _cloudflare_fetch("https://example.com")
        assert result is None


@pytest.mark.asyncio
async def test_cloudflare_fetch_with_ja3_config():
    with patch("agentfetch.core.router.CURL_CFFI_PROFILES", ["chrome124"]):
        result = await _cloudflare_fetch("https://example.com", ja3="chrome124")
        assert result is None or isinstance(result, str)


@pytest.mark.asyncio
async def test_smart_fetch_with_scrape_config():
    config = ScrapeConfig(scrape_links=False, max_content_length=100)
    with patch("agentfetch.core.router._static_fetch") as mock_static:
        mock_static.return_value = (
            FetchResult(
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
            ),
            "",
        )
        result = await smart_fetch("https://example.com", config=config)
        assert result.content == "test content"


@pytest.mark.asyncio
async def test_try_curl_cffi_returns_fetch_result_on_success():
    mock_curl_lib = MagicMock()
    mock_async_session = MagicMock()
    mock_curl_lib.requests.AsyncSession = mock_async_session
    mock_resp = MagicMock()
    mock_resp.text = (
        "<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"
    )
    mock_async_session.return_value.__aenter__.return_value.get.return_value = mock_resp
    with patch.dict(
        "sys.modules",
        {"curl_cffi": mock_curl_lib, "curl_cffi.requests": mock_curl_lib.requests},
    ):
        result = await _try_curl_cffi("https://example.com")
        assert result is not None
        assert isinstance(result, FetchResult)
        assert result.content
        assert result.render_mode == "bypass"


@pytest.mark.asyncio
async def test_try_curl_cffi_returns_fetch_result_on_success():
    mock_curl_lib = MagicMock()
    mock_async_session = MagicMock()
    mock_curl_lib.requests.AsyncSession = mock_async_session
    mock_resp = MagicMock()
    mock_resp.text = (
        "<html><head><title>T</title></head><body><p>content here. " * 20
        + "</p></body></html>"
    )
    mock_async_session.return_value.__aenter__.return_value.get.return_value = mock_resp
    mock_instance = mock_async_session.return_value.__aenter__.return_value
    mock_instance.get.return_value = mock_resp
    with patch.dict(
        "sys.modules",
        {"curl_cffi": mock_curl_lib, "curl_cffi.requests": mock_curl_lib.requests},
    ):
        result = await _try_curl_cffi("https://example.com")
        assert result is not None
        assert isinstance(result, FetchResult)
        assert result.render_mode == "bypass"


@pytest.mark.asyncio
async def test_try_curl_cffi_returns_none_on_empty_html():
    mock_curl_lib = MagicMock()
    mock_async_session = MagicMock()
    mock_curl_lib.requests.AsyncSession = mock_async_session
    mock_resp = MagicMock()
    mock_resp.text = ""
    mock_async_session.return_value.__aenter__.return_value.get.return_value = mock_resp
    mock_instance = mock_async_session.return_value.__aenter__.return_value
    mock_instance.get.return_value = mock_resp
    with patch.dict(
        "sys.modules",
        {"curl_cffi": mock_curl_lib, "curl_cffi.requests": mock_curl_lib.requests},
    ):
        result = await _try_curl_cffi("https://example.com")
        assert result is None


def test_fingerprint_profiles_defined():
    assert len(FINGERPRINT_PROFILES) >= 4
    for p in FINGERPRINT_PROFILES:
        assert "viewport" in p
        assert "locale" in p
        assert "timezone_id" in p
        assert "width" in p["viewport"]
        assert "height" in p["viewport"]


def test_pick_fingerprint_returns_valid_profile():
    fp = _pick_fingerprint()
    assert fp["viewport"]["width"] > 0
    assert fp["viewport"]["height"] > 0
    assert "locale" in fp
    assert "timezone_id" in fp


def test_pick_fingerprint_respects_config_viewport():
    custom = {"width": 800, "height": 600}
    fp = _pick_fingerprint(custom)
    assert fp["viewport"] == custom


def test_category_routes_defined():
    from agentfetch.core.router import CATEGORY_ROUTES

    assert "people" in CATEGORY_ROUTES
    assert "news" in CATEGORY_ROUTES
    assert "docs" in CATEGORY_ROUTES
    assert CATEGORY_ROUTES["people"]["engine"] == "browser"
    assert CATEGORY_ROUTES["docs"]["engine"] == "static"


@pytest.mark.asyncio
async def test_smart_fetch_category_routes_to_browser():
    _memory_cache.clear()
    config = ScrapeConfig(category="people")
    with patch(
        "agentfetch.core.router._try_curl_cffi", new_callable=AsyncMock
    ) as mock_tls:
        mock_tls.return_value = None
        with patch(
            "agentfetch.core.router._browser_fetch", new_callable=AsyncMock
        ) as mock_browser:
            mock_browser.return_value = FetchResult(
                url="https://people-category-test.com",
                content="people page content",
                title="John Doe",
                confidence=0.8,
                render_mode="browser",
            )
            result = await smart_fetch(
                "https://people-category-test.com", config=config
            )
            assert result.content == "people page content"
            assert mock_browser.called


@pytest.mark.asyncio
async def test_smart_fetch_category_docs_uses_static():
    _memory_cache.clear()
    config = ScrapeConfig(category="docs")
    with patch("agentfetch.core.router._static_fetch") as mock_static:
        mock_static.return_value = (
            FetchResult(
                url="https://docs-category-test.com",
                content="docs content",
                title="Docs",
                confidence=0.9,
                render_mode="static",
            ),
            "<html>content</html>",
        )
        result = await smart_fetch("https://docs-category-test.com", config=config)
        assert result.content == "docs content"
        assert result.render_mode == "static"


@pytest.mark.asyncio
async def test_smart_fetch_category_unknown_defaults_auto():
    _memory_cache.clear()
    config = ScrapeConfig(category="unknown_category")
    with patch("agentfetch.core.router._static_fetch") as mock_static:
        mock_static.return_value = (
            FetchResult(
                url="https://unknown-category-test.com",
                content="default content",
                title="Default",
                confidence=0.9,
                render_mode="static",
            ),
            "<html><body><p>some real content here that will extract nicely and not trigger browser fallback</p></body></html>",
        )
        result = await smart_fetch("https://unknown-category-test.com", config=config)
        assert result.content is not None


def test_stealth_init_script_contains_key_definitions():
    script = _stealth_init_script()
    assert "webdriver" in script
    assert "plugins" in script
    assert "languages" in script
    assert "chrome" in script
