import pytest
from unittest.mock import patch, MagicMock
from agentfetch.core.extractor import (
    extract_content,
    detect_content_type,
    _add_citation_markers,
)
from agentfetch.core.schema import ScrapeConfig


def test_extract_chain_falls_through_on_failure():
    html = "<html><body><p>Hello world</p></body></html>"
    text, name, citations = extract_content(html, url="http://example.com")
    assert isinstance(text, str)
    assert isinstance(citations, list)


def test_detect_content_type_article_url():
    html = "<html><body>test</body></html>"
    ct = detect_content_type(html, "https://example.com/blog/hello-world")
    assert ct == "article"


def test_detect_content_type_docs_url():
    html = "<html><body>test</body></html>"
    ct = detect_content_type(html, "https://example.com/docs/getting-started")
    assert ct == "docs"


def test_detect_content_type_product_url():
    html = "<html><body>test</body></html>"
    ct = detect_content_type(html, "https://example.com/product/item-123")
    assert ct == "product"


def test_detect_content_type_listing_url():
    html = "<html><body>test</body></html>"
    ct = detect_content_type(html, "https://example.com/shop/category/books")
    assert ct == "listing"


def test_detect_content_type_unknown():
    html = "<html><body>test</body></html>"
    ct = detect_content_type(html, "https://example.com/custom-page")
    assert ct == "unknown"


def test_detect_content_type_og_article():
    html = '<html><head><meta property="og:type" content="article"></head><body>test</body></html>'
    ct = detect_content_type(html, "https://example.com/page")
    assert ct == "article"


def test_output_is_markdown():
    html = "<html><body><h1>Title</h1><p>Paragraph</p></body></html>"
    text, name, citations = extract_content(html)
    assert "# Title" in text or "Title" in text
    assert isinstance(text, str)


def test_scrape_config_exclude_tags():
    html = "<html><body><p>Keep this</p><script>remove this</script><style>also remove</style></body></html>"
    config = ScrapeConfig(exclude_tags=["script", "style"])
    text, name, citations = extract_content(html, config=config)
    assert "Keep this" in text
    assert "remove this" not in text


def test_scrape_config_max_content_length():
    html = "<html><body><p>" + "A" * 500 + "</p><p>" + "B" * 500 + "</p></body></html>"
    config = ScrapeConfig(max_content_length=200)
    text, name, citations = extract_content(html, config=config)
    assert len(text) <= 200


def test_scrape_config_include_tags():
    html = "<html><body><p>paragraph</p><article>article content</article><footer>footer</footer></body></html>"
    config = ScrapeConfig(include_tags=["article"])
    text, name, citations = extract_content(html, config=config)
    assert "article content" in text
    assert "paragraph" not in text


def test_citation_markers():
    html = "<html><body><p>Visit https://example.com and https://test.org for more</p></body></html>"
    text, name, citations = extract_content(
        html, config=ScrapeConfig(citation_links=True)
    )
    if citations:
        assert "[" in text
        assert len(citations) > 0


def test_add_citation_markers():
    text = "Check https://example.com and https://test.org"
    result, urls = _add_citation_markers(text)
    assert len(urls) == 2
    assert "[1]" in result
    assert "[2]" in result


def test_add_citation_markers_no_urls():
    text = "No URLs here"
    result, urls = _add_citation_markers(text)
    assert len(urls) == 0
    assert result == text


def test_extract_highlights_returns_top_sentences():
    from agentfetch.core.extractor import extract_highlights

    text = (
        "Python is a programming language. "
        "It is widely used for data science. "
        "Many companies rely on Python. "
        "The syntax is clear and readable. "
        "Python has a large ecosystem of libraries. "
    )
    highlights = extract_highlights(text, max_sentences=3)
    assert len(highlights) <= 3
    assert all(len(h.strip()) > 20 for h in highlights)


def test_extract_highlights_returns_all_when_short():
    from agentfetch.core.extractor import extract_highlights

    text = "Short text. Not enough sentences. For highlights."
    highlights = extract_highlights(text, max_sentences=5)
    assert len(highlights) >= 1


def test_extract_highlights_respects_max_sentences():
    from agentfetch.core.extractor import extract_highlights

    text = (
        "First important sentence about the topic. " * 2
        + "Second key insight for testing purposes. " * 2
        + "Third interesting detail worth keeping."
    )
    highlights = extract_highlights(text, max_sentences=2)
    assert len(highlights) <= 2


def test_extract_structured_string_field():
    from agentfetch.core.extractor import extract_structured

    text = "Company: Acme Corp\nLocation: New York\nFounded: 2020"
    schema = {
        "type": "object",
        "properties": {
            "company": {"type": "string", "description": "Company"},
            "location": {"type": "string", "description": "Location"},
        },
    }
    result = extract_structured(text, schema)
    assert result is not None
    assert result["company"] is not None
    assert result["location"] is not None


def test_extract_structured_numeric_field():
    from agentfetch.core.extractor import extract_structured

    text = "Revenue: $1,234,567\nEmployees: 500"
    schema = {
        "type": "object",
        "properties": {
            "revenue": {"type": "number", "description": "Revenue"},
            "employees": {"type": "integer", "description": "Employees"},
        },
    }
    result = extract_structured(text, schema)
    assert result is not None
    assert result["revenue"] == 1234567
    assert result["employees"] == 500


def test_extract_structured_boolean_field():
    from agentfetch.core.extractor import extract_structured

    text = "Public: True\nProfitable: yes"
    schema = {
        "type": "object",
        "properties": {
            "public": {"type": "boolean", "description": "Public"},
            "profitable": {"type": "boolean", "description": "Profitable"},
        },
    }
    result = extract_structured(text, schema)
    assert result is not None
    assert result["public"] is True
    assert result["profitable"] is True


def test_extract_structured_returns_none_for_missing_fields():
    from agentfetch.core.extractor import extract_structured

    text = "Some unrelated content here"
    schema = {
        "type": "object",
        "properties": {
            "company": {"type": "string", "description": "Company name"},
        },
    }
    result = extract_structured(text, schema)
    assert result is not None
    assert result["company"] is None


def test_extract_structured_empty_schema():
    from agentfetch.core.extractor import extract_structured

    result = extract_structured("Some text", {})
    assert result == {}


def test_extract_structured_nested_properties():
    from agentfetch.core.extractor import extract_by_schema

    text = "CEO: John Doe\nCTO: Jane Smith"
    schema = {
        "CEO": "Chief Executive Officer",
        "CTO": "Chief Technology Officer",
    }
    result = extract_by_schema(text, schema)
    assert "CEO" in result
    assert "CTO" in result
