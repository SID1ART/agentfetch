import json
import pytest
from agentfetch.core.schema import FetchResult, CrawlResult, SearchResult, ScrapeConfig


def test_fetch_result_serializes_to_json():
    r = FetchResult(url="https://example.com", content="hello", confidence=0.9)
    data = r.model_dump_json()
    assert isinstance(data, str)
    parsed = json.loads(data)
    assert parsed["url"] == "https://example.com"
    assert parsed["content"] == "hello"
    assert parsed["confidence"] == 0.9


def test_fetch_result_deserializes_from_json():
    data = '{"url":"https://example.com","content":"hello","confidence":0.9,"content_type":"unknown","word_count":0,"render_mode":"static","latency_ms":0,"cached":false,"injection_detected":false}'
    r = FetchResult.model_validate_json(data)
    assert r.url == "https://example.com"
    assert r.content == "hello"
    assert r.confidence == 0.9
    assert r.duplicate_of is None
    assert r.retries == 0
    assert r.normalized_url is None
    assert r.citations is None
    assert r.robots_allowed is True
    assert r.proxy_used is None


def test_required_fields_cannot_be_none():
    with pytest.raises(Exception):
        FetchResult(url=None, content=None, confidence=None)  # type: ignore


def test_crawl_result_defaults():
    r = CrawlResult(job_id="test-123", status="running")
    assert r.job_id == "test-123"
    assert r.status == "running"
    assert r.pages == []
    assert r.total_pages == 0
    assert r.unique_pages == 0
    assert r.duplicates_skipped == 0
    assert r.stopped_reason is None
    assert r.queued is False


def test_search_result():
    fr = FetchResult(url="https://example.com", content="test", confidence=0.5)
    sr = SearchResult(query="test query", results=[fr], source="duckduckgo")
    assert sr.query == "test query"
    assert len(sr.results) == 1
    assert sr.source == "duckduckgo"
    assert sr.suggestions is None


def test_scrape_config_defaults():
    c = ScrapeConfig()
    assert c.wait_for is None
    assert c.include_tags is None
    assert c.exclude_tags is None
    assert c.viewport is None
    assert c.js_wait_ms == 0
    assert c.scrape_links is True
    assert c.max_content_length == 50000
    assert c.citation_links is False
    assert c.proxy is None
    assert c.cookies is None
    assert c.headers is None


def test_scrape_config_custom():
    c = ScrapeConfig(
        wait_for=".content",
        include_tags=["article", "p"],
        exclude_tags=["script", "style"],
        viewport={"width": 1024, "height": 768},
        js_wait_ms=2000,
        scrape_links=False,
        max_content_length=10000,
        citation_links=True,
        proxy="http://proxy:8080",
        headers={"Authorization": "Bearer test"},
    )
    assert c.wait_for == ".content"
    assert c.include_tags == ["article", "p"]
    assert c.js_wait_ms == 2000
    assert c.scrape_links is False
    assert c.max_content_length == 10000
    assert c.citation_links is True
    assert c.proxy == "http://proxy:8080"


def test_fetch_result_new_fields():
    r = FetchResult(
        url="https://example.com",
        content="test",
        confidence=0.9,
        citations=["https://example.com/1", "https://example.com/2"],
        robots_allowed=False,
        proxy_used="http://proxy:8080",
    )
    assert len(r.citations) == 2
    assert r.robots_allowed is False
    assert r.proxy_used == "http://proxy:8080"
