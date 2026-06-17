from agentfetch.core.normalizer import (
    normalize_url,
    content_hash,
    is_near_duplicate,
    simhash_fingerprint,
    is_navigation_path,
    extract_domain,
)


def test_normalize_removes_tracking():
    url = "https://example.com/page?utm_source=twitter&utm_medium=social&q=real"
    n = normalize_url(url)
    assert "utm_source" not in n
    assert "utm_medium" not in n
    assert "q=real" in n


def test_normalize_lowercases():
    url = "HTTPS://Example.COM/Path"
    n = normalize_url(url)
    assert n == "https://example.com/Path"  # scheme + host lowercased, path preserved


def test_normalize_removes_www():
    url = "https://www.example.com/page"
    n = normalize_url(url)
    assert "www." not in n
    assert n == "https://example.com/page"


def test_normalize_removes_fbclid():
    url = "https://example.com/page?fbclid=abc123"
    n = normalize_url(url)
    assert "fbclid" not in n


def test_content_hash_is_deterministic():
    h1 = content_hash("hello world")
    h2 = content_hash("hello world")
    assert h1 == h2


def test_simhash_similar_texts():
    fp1 = simhash_fingerprint("The quick brown fox jumps over the lazy dog")
    fp2 = simhash_fingerprint("The quick brown fox jumps over the lazy cat")
    dup, sim = is_near_duplicate(fp2, [fp1])
    assert sim > 0.5


def test_simhash_different_texts():
    fp1 = simhash_fingerprint("Python programming language")
    fp2 = simhash_fingerprint("Quantum physics and mechanics")
    dup, sim = is_near_duplicate(fp2, [fp1])
    assert sim < 0.8


def test_is_navigation_path():
    assert is_navigation_path("/login")
    assert is_navigation_path("/privacy-policy")
    assert is_navigation_path("/terms-of-service")
    assert not is_navigation_path("/blog/post-1")
    assert not is_navigation_path("/docs/getting-started")


def test_extract_domain():
    assert extract_domain("https://www.example.com/page") == "example.com"
    assert extract_domain("https://blog.example.com") == "blog.example.com"
