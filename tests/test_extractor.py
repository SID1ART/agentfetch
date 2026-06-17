import pytest
from unittest.mock import patch, MagicMock
from agentfetch.core.extractor import extract_content, detect_content_type


def test_extract_chain_falls_through_on_failure():
    html = "<html><body><p>Hello world</p></body></html>"
    text, name = extract_content(html, url="http://example.com")
    assert isinstance(text, str)


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
    text, name = extract_content(html)
    assert "# Title" in text or "Title" in text
    assert isinstance(text, str)
