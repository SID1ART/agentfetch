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
