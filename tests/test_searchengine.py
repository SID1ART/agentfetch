import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from agentfetch.core.searchengine import (
    EngineResult,
    parallel_search,
    search_fetch,
    _search_ddg,
    _search_google,
    _search_google_api,
    _search_bing,
    _search_searxng,
    _search_brave_api,
    _search_serpapi,
    ENGINE_REGISTRY,
    ENGINE_NAMES,
    _configure_searxng,
    _get_engine_fn,
    BRAVE_SEARCH_API_KEY,
    SERPAPI_KEY,
    GOOGLE_API_KEY,
    GOOGLE_CX,
)
from agentfetch.core.schema import SearchResult, FetchResult
import asyncio


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
    assert "brave" in ENGINE_REGISTRY
    assert "serpapi" in ENGINE_REGISTRY


def test_engine_names_contains_new_engines():
    assert "brave" in ENGINE_NAMES
    assert "serpapi" in ENGINE_NAMES


@pytest.mark.asyncio
async def test_search_brave_api_returns_empty_when_no_key():
    with patch("agentfetch.core.searchengine.BRAVE_SEARCH_API_KEY", ""):
        results = await _search_brave_api("test", 5)
        assert results == []


@pytest.mark.asyncio
async def test_search_serpapi_returns_empty_when_no_key():
    with patch("agentfetch.core.searchengine.SERPAPI_KEY", ""):
        results = await _search_serpapi("test", 5)
        assert results == []


@pytest.mark.asyncio
async def test_search_google_api_returns_empty_when_no_keys():
    with patch("agentfetch.core.searchengine.GOOGLE_API_KEY", ""):
        with patch("agentfetch.core.searchengine.GOOGLE_CX", ""):
            results = await _search_google_api("test", 5)
            assert results == []


@pytest.mark.asyncio
async def test_search_brave_api_returns_results_when_key_set():
    mock_data = {
        "web": {
            "results": [
                {
                    "title": "Brave Result",
                    "url": "https://brave.com",
                    "description": "Brave search engine",
                }
            ]
        }
    }
    with patch("agentfetch.core.searchengine.BRAVE_SEARCH_API_KEY", "test_key"):
        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_data
            mock_resp.raise_for_status.return_value = None
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_resp
            )
            results = await _search_brave_api("test", 5)
            assert len(results) == 1
            assert results[0].title == "Brave Result"
            assert results[0].url == "https://brave.com"
            assert results[0].source == "brave"


@pytest.mark.asyncio
async def test_search_serpapi_returns_results_when_key_set():
    mock_data = {
        "organic_results": [
            {
                "title": "Serp Result",
                "link": "https://example.com",
                "snippet": "a snippet",
            }
        ]
    }
    with patch("agentfetch.core.searchengine.SERPAPI_KEY", "test_key"):
        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_data
            mock_resp.raise_for_status.return_value = None
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_resp
            )
            results = await _search_serpapi("test", 5)
            assert len(results) == 1
            assert results[0].title == "Serp Result"
            assert results[0].source == "serpapi"


@pytest.mark.asyncio
async def test_search_google_api_returns_results_when_keys_set():
    mock_data = {
        "items": [
            {
                "title": "G Result",
                "link": "https://google.com",
                "snippet": "google result",
            }
        ]
    }
    with patch("agentfetch.core.searchengine.GOOGLE_API_KEY", "test_key"):
        with patch("agentfetch.core.searchengine.GOOGLE_CX", "test_cx"):
            with patch("httpx.AsyncClient") as mock_client:
                mock_resp = MagicMock()
                mock_resp.json.return_value = mock_data
                mock_resp.raise_for_status.return_value = None
                mock_client.return_value.__aenter__.return_value.get.return_value = (
                    mock_resp
                )
                results = await _search_google_api("test", 5)
                assert len(results) == 1
                assert results[0].title == "G Result"
                assert results[0].source == "google_api"


@pytest.mark.asyncio
async def test_search_google_uses_api_when_key_set():
    with patch("agentfetch.core.searchengine.GOOGLE_API_KEY", "test_key"):
        with patch("agentfetch.core.searchengine.GOOGLE_CX", "test_cx"):
            with patch(
                "agentfetch.core.searchengine._search_google_api",
                new_callable=AsyncMock,
            ) as mock_api:
                mock_api.return_value = [
                    EngineResult(
                        title="API Result",
                        url="https://api.com",
                        snippet="api",
                        source="google_api",
                    )
                ]
                results, engines, errors = await parallel_search(
                    "test", sources=["google"], max_results=5
                )
                assert len(results) >= 1
                assert results[0].source == "google_api"


@pytest.mark.asyncio
async def test_parallel_search_includes_brave_when_key_set():
    with patch("agentfetch.core.searchengine.BRAVE_SEARCH_API_KEY", "test_key"):
        with patch("agentfetch.core.searchengine.SERPAPI_KEY", ""):
            with patch(
                "agentfetch.core.searchengine._search_brave_api", new_callable=AsyncMock
            ) as mock_brave:
                mock_brave.return_value = [
                    EngineResult(
                        title="B", url="https://brave.com", snippet="b", source="brave"
                    )
                ]
                with patch("agentfetch.core.searchengine._search_ddg") as mock_ddg:
                    mock_ddg.return_value = []
                    with patch(
                        "agentfetch.core.searchengine._search_google"
                    ) as mock_google:
                        mock_google.return_value = []
                        with patch(
                            "agentfetch.core.searchengine._search_bing"
                        ) as mock_bing:
                            mock_bing.return_value = []
                            results, engines, errors = await parallel_search(
                                "test", max_results=5
                            )
                            assert "brave" in engines


@pytest.mark.asyncio
async def test_parallel_search_includes_serpapi_when_key_set():
    with patch("agentfetch.core.searchengine.BRAVE_SEARCH_API_KEY", ""):
        with patch("agentfetch.core.searchengine.SERPAPI_KEY", "test_key"):
            with patch(
                "agentfetch.core.searchengine._search_serpapi", new_callable=AsyncMock
            ) as mock_serp:
                mock_serp.return_value = [
                    EngineResult(
                        title="S", url="https://serp.com", snippet="s", source="serpapi"
                    )
                ]
                with patch("agentfetch.core.searchengine._search_ddg") as mock_ddg:
                    mock_ddg.return_value = []
                    with patch(
                        "agentfetch.core.searchengine._search_google"
                    ) as mock_google:
                        mock_google.return_value = []
                        with patch(
                            "agentfetch.core.searchengine._search_bing"
                        ) as mock_bing:
                            mock_bing.return_value = []
                            results, engines, errors = await parallel_search(
                                "test", max_results=5
                            )
                            assert "serpapi" in engines


@pytest.mark.asyncio
async def test_search_ddg_raises_on_failure():
    with pytest.raises(Exception):
        await _search_ddg("", 5)


@pytest.mark.asyncio
async def test_search_google_returns_empty_when_not_installed():
    with patch.dict("sys.modules", {"googlesearch": None}):
        results = await _search_google("test", 5)
        assert results == []


@pytest.mark.asyncio
async def test_search_bing_raises_on_http_error():
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.side_effect = Exception("connection error")
        with pytest.raises(Exception):
            await _search_bing("test", 5)


@pytest.mark.asyncio
async def test_search_searxng_returns_empty_when_no_url():
    _configure_searxng("")
    results = await _search_searxng("test", 5)
    assert results == []


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
async def test_generate_query_variations_short_query():
    from agentfetch.core.searchengine import generate_query_variations

    vars = generate_query_variations("hello world")
    assert len(vars) >= 1
    assert "hello world" in vars


def test_generate_query_variations_long_query():
    from agentfetch.core.searchengine import generate_query_variations

    vars = generate_query_variations("how to build a web crawler")
    assert len(vars) >= 2
    assert "how to build a web crawler" in vars


def test_generate_query_variations_max_four():
    from agentfetch.core.searchengine import generate_query_variations

    vars = generate_query_variations("a b c d e f g")
    assert len(vars) <= 4


def test_parallel_search_deep_generates_variations():
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
                results, engines, errors = asyncio.run(
                    parallel_search(
                        "test query with many words",
                        sources=["duckduckgo"],
                        max_results=5,
                        depth="deep",
                    )
                )
                assert len(results) >= 1


def test_parallel_search_category_modifier():
    with patch(
        "agentfetch.core.searchengine._search_ddg", new_callable=AsyncMock
    ) as mock_ddg:
        mock_ddg.return_value = [
            EngineResult(
                title="N", url="https://news.com", snippet="news", source="duckduckgo"
            )
        ]
        results, engines, errors = asyncio.run(
            parallel_search(
                "test",
                sources=["duckduckgo"],
                max_results=5,
                category="news",
            )
        )
        assert len(results) >= 1


def test_parallel_search_category_unknown_no_modifier():
    with patch(
        "agentfetch.core.searchengine._search_ddg", new_callable=AsyncMock
    ) as mock_ddg:
        mock_ddg.return_value = [
            EngineResult(
                title="A", url="https://a.com", snippet="a", source="duckduckgo"
            )
        ]
        results, engines, errors = asyncio.run(
            parallel_search(
                "test",
                sources=["duckduckgo"],
                max_results=5,
                category="unknown_category",
            )
        )
        assert len(results) >= 1


@pytest.mark.asyncio
async def test_stream_search_yields_results():
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
                from agentfetch.core.searchengine import stream_search

                results = []
                async for r in stream_search(
                    "test", sources=["duckduckgo"], max_results=5
                ):
                    results.append(r)
                assert len(results) >= 1
                assert all(isinstance(r, EngineResult) for r in results)


@pytest.mark.asyncio
async def test_stream_search_deduplicates():
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
                mock_bing.return_value = []
                from agentfetch.core.searchengine import stream_search

                results = []
                async for r in stream_search(
                    "test", sources=["duckduckgo", "google"], max_results=5
                ):
                    results.append(r)
                urls = [r.url for r in results]
                assert urls.count("https://example.com/page") == 1


@pytest.mark.asyncio
async def test_stream_search_skips_failed_engines():
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
            from agentfetch.core.searchengine import stream_search

            results = []
            async for r in stream_search(
                "test", sources=["duckduckgo", "bing"], max_results=5
            ):
                results.append(r)
            assert len(results) >= 1


def test_search_fetch_returns_engine_errors():
    with patch("agentfetch.core.searchengine.parallel_search") as mock_ps:
        mock_ps.return_value = (
            [],
            [],
            {"google": "429 rate limited", "bing": "returned zero results"},
        )
        result = asyncio.run(search_fetch("test", max_results=5, scrape_results=False))
        assert result.total_results == 0
        assert len(result.results) == 0
        assert "google" in result.errors
        assert "bing" in result.errors
