import json
import pytest
from agentfetch.core.schema import FetchResult, CrawlResult, SearchResult


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


def test_required_fields_cannot_be_none():
    with pytest.raises(Exception):
        FetchResult(url=None, content=None, confidence=None)  # type: ignore


def test_crawl_result_defaults():
    r = CrawlResult(job_id="test-123", status="running")
    assert r.job_id == "test-123"
    assert r.status == "running"
    assert r.pages == []
    assert r.total_pages == 0
    assert r.stopped_reason is None


def test_search_result():
    fr = FetchResult(url="https://example.com", content="test", confidence=0.5)
    sr = SearchResult(query="test query", results=[fr], source="duckduckgo")
    assert sr.query == "test query"
    assert len(sr.results) == 1
    assert sr.source == "duckduckgo"
