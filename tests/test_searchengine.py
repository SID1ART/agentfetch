import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from agentfetch.core.searchengine import (
    EngineResult,
    parallel_search,
    search_fetch,
    _search_ddg,
    _search_google,
    _search_bing,
    _search_searxng,
    ENGINE_REGISTRY,
    _configure_searxng,
    _get_engine_fn,
)
from agentfetch.core.schema import SearchResult, FetchResult


def test_engine_result_dataclass():
    r = EngineResult(
        title="Test", url="https://example.com", snippet="snippet", source="duckduckgo"
    )
    assert r.title == "Test"
    assert r.url == "https://example.com"
    assert r.snippet == "snippet"
    assert r.source == "duckduckgo"


def test_engine_registry_contains_core_engines():
    assert "duckduckgo" in ENGINE_REGISTRY
    assert "google" in ENGINE_REGISTRY
    assert "bing" in ENGINE_REGISTRY
    assert "searxng" in ENGINE_REGISTRY


@pytest.mark.asyncio
async def test_search_ddg_returns_empty_on_failure():
    results = await _search_ddg("", 5)
    assert results == []


@pytest.mark.asyncio
async def test_search_google_returns_empty_when_not_installed():
    with patch.dict("sys.modules", {"googlesearch": None}):
        results = await _search_google("test", 5)
        assert results == []


@pytest.mark.asyncio
async def test_search_bing_returns_empty_on_http_error():
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.side_effect = Exception("connection error")
        results = await _search_bing("test", 5)
        assert results == []


@pytest.mark.asyncio
async def test_search_searxng_returns_empty_when_no_url():
    _configure_searxng("")
    results = await _search_searxng("test", 5)
    assert results == []


@pytest.mark.asyncio
async def test_parallel_search_defaults_to_ddg_when_no_sources():
    with patch("agentfetch.core.searchengine._search_ddg") as mock_ddg:
        mock_ddg.return_value = [
            EngineResult(
                title="A", url="https://a.com", snippet="a", source="duckduckgo"
            )
        ]
        with patch("agentfetch.core.searchengine._search_google") as mock_google:
            mock_google.return_value = []
            with patch("agentfetch.core.searchengine._search_bing") as mock_bing:
                mock_bing.return_value = []
                results, engines, errors = await parallel_search("test", max_results=5)
                assert len(results) >= 1
                assert "duckduckgo" in engines


@pytest.mark.asyncio
async def test_parallel_search_deduplicates_by_url():
    with patch("agentfetch.core.searchengine._search_ddg") as mock_ddg:
        mock_ddg.return_value = [
            EngineResult(
                title="A",
                url="https://example.com/page",
                snippet="a",
                source="duckduckgo",
            )
        ]
        with patch("agentfetch.core.searchengine._search_google") as mock_google:
            mock_google.return_value = [
                EngineResult(
                    title="A",
                    url="https://example.com/page",
                    snippet="a",
                    source="google",
                )
            ]
            with patch("agentfetch.core.searchengine._search_bing") as mock_bing:
                mock_bing.return_value = [
                    EngineResult(
                        title="B",
                        url="https://example.com/other",
                        snippet="b",
                        source="bing",
                    )
                ]
                results, engines, errors = await parallel_search(
                    "test", sources=["duckduckgo", "google", "bing"], max_results=5
                )
                assert len(results) == 2
                urls = [r.url for r in results]
                assert urls.count("https://example.com/page") == 1


@pytest.mark.asyncio
async def test_parallel_search_honors_sources_param():
    with patch("agentfetch.core.searchengine._search_ddg") as mock_ddg:
        mock_ddg.return_value = [
            EngineResult(
                title="A", url="https://a.com", snippet="a", source="duckduckgo"
            )
        ]
        with patch("agentfetch.core.searchengine._search_bing") as mock_bing:
            mock_bing.return_value = []
            results, engines, errors = await parallel_search(
                "test", sources=["duckduckgo"], max_results=5
            )
            assert len(engines) == 1
            assert "duckduckgo" in engines
            assert "bing" not in engines


@pytest.mark.asyncio
async def test_parallel_search_engine_exception_does_not_crash():
    with patch("agentfetch.core.searchengine._search_ddg") as mock_ddg:
        mock_ddg.side_effect = Exception("DDG down")
        with patch("agentfetch.core.searchengine._search_bing") as mock_bing:
            mock_bing.return_value = [
                EngineResult(title="B", url="https://b.com", snippet="b", source="bing")
            ]
            with patch("agentfetch.core.searchengine._search_google") as mock_google:
                mock_google.return_value = []
                results, engines, errors = await parallel_search(
                    "test", sources=["duckduckgo", "bing"], max_results=5
                )
                assert len(results) >= 1
                assert "bing" in engines
                assert "duckduckgo" in errors


@pytest.mark.asyncio
async def test_parallel_search_defaults_to_ddg_when_no_sources():
    with patch(
        "agentfetch.core.searchengine._search_ddg", new_callable=AsyncMock
    ) as mock_ddg:
        mock_ddg.return_value = [
            EngineResult(
                title="A", url="https://a.com", snippet="a", source="duckduckgo"
            )
        ]
        with patch(
            "agentfetch.core.searchengine._search_google", new_callable=AsyncMock
        ) as mock_google:
            mock_google.return_value = []
            with patch(
                "agentfetch.core.searchengine._search_bing", new_callable=AsyncMock
            ) as mock_bing:
                mock_bing.return_value = []
                results, engines, errors = await parallel_search("test", max_results=5)
                assert len(results) >= 1
                assert "duckduckgo" in engines


@pytest.mark.asyncio
async def test_parallel_search_deduplicates_by_url():
    with patch(
        "agentfetch.core.searchengine._search_ddg", new_callable=AsyncMock
    ) as mock_ddg:
        mock_ddg.return_value = [
            EngineResult(
                title="A",
                url="https://example.com/page",
                snippet="a",
                source="duckduckgo",
            )
        ]
        with patch(
            "agentfetch.core.searchengine._search_google", new_callable=AsyncMock
        ) as mock_google:
            mock_google.return_value = [
                EngineResult(
                    title="A",
                    url="https://example.com/page",
                    snippet="a",
                    source="google",
                )
            ]
            with patch(
                "agentfetch.core.searchengine._search_bing", new_callable=AsyncMock
            ) as mock_bing:
                mock_bing.return_value = [
                    EngineResult(
                        title="B",
                        url="https://example.com/other",
                        snippet="b",
                        source="bing",
                    )
                ]
                results, engines, errors = await parallel_search(
                    "test", sources=["duckduckgo", "google", "bing"], max_results=5
                )
                assert len(results) == 2
                urls = [r.url for r in results]
                assert urls.count("https://example.com/page") == 1


@pytest.mark.asyncio
async def test_parallel_search_honors_sources_param():
    with patch(
        "agentfetch.core.searchengine._search_ddg", new_callable=AsyncMock
    ) as mock_ddg:
        mock_ddg.return_value = [
            EngineResult(
                title="A", url="https://a.com", snippet="a", source="duckduckgo"
            )
        ]
        with patch(
            "agentfetch.core.searchengine._search_bing", new_callable=AsyncMock
        ) as mock_bing:
            mock_bing.return_value = []
            results, engines, errors = await parallel_search(
                "test", sources=["duckduckgo"], max_results=5
            )
            assert len(engines) == 1
            assert "duckduckgo" in engines
            assert "bing" not in engines


@pytest.mark.asyncio
async def test_parallel_search_engine_exception_does_not_crash():
    with patch(
        "agentfetch.core.searchengine._search_ddg", new_callable=AsyncMock
    ) as mock_ddg:
        mock_ddg.side_effect = Exception("DDG down")
        with patch(
            "agentfetch.core.searchengine._search_bing", new_callable=AsyncMock
        ) as mock_bing:
            mock_bing.return_value = [
                EngineResult(title="B", url="https://b.com", snippet="b", source="bing")
            ]
            with patch(
                "agentfetch.core.searchengine._search_google", new_callable=AsyncMock
            ) as mock_google:
                mock_google.return_value = []
                results, engines, errors = await parallel_search(
                    "test", sources=["duckduckgo", "bing"], max_results=5
                )
                assert len(results) >= 1
                assert "bing" in engines
                assert "duckduckgo" in errors


@pytest.mark.asyncio
async def test_parallel_search_records_engine_errors():
    with patch(
        "agentfetch.core.searchengine._search_ddg", new_callable=AsyncMock
    ) as mock_ddg:
        mock_ddg.side_effect = Exception("DDG rate limited")
        with patch(
            "agentfetch.core.searchengine._search_bing", new_callable=AsyncMock
        ) as mock_bing:
            mock_bing.return_value = []
            with patch(
                "agentfetch.core.searchengine._search_google", new_callable=AsyncMock
            ) as mock_google:
                mock_google.return_value = []
                results, engines, errors = await parallel_search(
                    "test", sources=["duckduckgo", "bing", "google"], max_results=5
                )
                assert "duckduckgo" in errors
                assert "rate limited" in errors["duckduckgo"]


@pytest.mark.asyncio
async def test_search_fetch_returns_search_result():
    with patch("agentfetch.core.searchengine.parallel_search") as mock_ps:
        mock_ps.return_value = (
            [
                EngineResult(
                    title="A", url="https://a.com", snippet="a", source="duckduckgo"
                )
            ],
            ["duckduckgo"],
            {},
        )
        with patch("agentfetch.core.searchengine.smart_fetch") as mock_fetch:
            mock_fetch.return_value = FetchResult(
                url="https://a.com", content="full content", title="A", confidence=1.0
            )
            result = await search_fetch("test", max_results=5, scrape_results=True)
            assert isinstance(result, SearchResult)
            assert result.query == "test"
            assert len(result.results) == 1
            assert result.results[0].content == "full content"
            assert result.source == "duckduckgo"
            assert result.sources_used == ["duckduckgo"]
            assert result.total_results == 1


@pytest.mark.asyncio
async def test_search_fetch_no_scrape():
    with patch("agentfetch.core.searchengine.parallel_search") as mock_ps:
        mock_ps.return_value = (
            [
                EngineResult(
                    title="A",
                    url="https://a.com",
                    snippet="a snippet",
                    source="duckduckgo",
                )
            ],
            ["duckduckgo"],
            {},
        )
        result = await search_fetch("test", max_results=5, scrape_results=False)
        assert len(result.results) == 1
        assert result.results[0].content == "a snippet"
        assert result.results[0].confidence == 0.5


@pytest.mark.asyncio
async def test_search_fetch_graceful_error_on_scrape_failure():
    with patch("agentfetch.core.searchengine.parallel_search") as mock_ps:
        mock_ps.return_value = (
            [
                EngineResult(
                    title="A", url="https://a.com", snippet="a", source="duckduckgo"
                )
            ],
            ["duckduckgo"],
            {},
        )
        with patch("agentfetch.core.searchengine.smart_fetch") as mock_fetch:
            mock_fetch.side_effect = Exception("scrape failed")
            result = await search_fetch("test", max_results=5, scrape_results=True)
            assert len(result.results) == 1
            assert result.results[0].error is not None
            assert result.results[0].confidence == 0.3


@pytest.mark.asyncio
async def test_search_fetch_returns_engine_errors():
    with patch("agentfetch.core.searchengine.parallel_search") as mock_ps:
        mock_ps.return_value = (
            [],
            [],
            {"google": "429 rate limited", "bing": "returned zero results"},
        )
        result = await search_fetch("test", max_results=5, scrape_results=False)
        assert result.total_results == 0
        assert len(result.results) == 0
        assert "google" in result.errors
        assert "bing" in result.errors
