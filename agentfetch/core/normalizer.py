import hashlib
import logging
import re
from typing import Optional
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

logger = logging.getLogger("agentfetch.normalizer")

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "_ga",
    "_gl",
    "igshid",
    "ref",
    "ref_src",
    "ref_url",
    "source",
    "si",
    "s_kwcid",
}

STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "by",
    "with",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "can",
    "could",
    "may",
    "might",
    "shall",
    "should",
    "not",
    "no",
    "nor",
    "it",
    "its",
    "that",
    "this",
    "these",
    "those",
}

SHINGLE_SIZE = 3
FINGERPRINT_BITS = 64
SIMILARITY_THRESHOLD = 0.85


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path.rstrip("/") or "/"

    query = parse_qs(parsed.query, keep_blank_values=True)
    for key in list(query):
        if key.lower() in TRACKING_PARAMS:
            del query[key]
    sorted_query = urlencode(sorted(query.items()), doseq=True)

    fragment = ""

    normalized = urlunparse(
        (scheme, netloc, path, parsed.params, sorted_query, fragment)
    )
    return normalized


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _shingles(text: str) -> set[int]:
    words = [w.lower() for w in re.findall(r"\w+", text) if w.lower() not in STOP_WORDS]
    hashes: set[int] = set()
    for i in range(len(words) - SHINGLE_SIZE + 1):
        shingle = " ".join(words[i : i + SHINGLE_SIZE])
        h = int(hashlib.md5(shingle.encode()).hexdigest()[:16], 16)
        hashes.add(h)
    return hashes


def simhash_fingerprint(text: str) -> int:
    words = [w.lower() for w in re.findall(r"\w+", text) if w.lower() not in STOP_WORDS]
    v = [0] * FINGERPRINT_BITS
    for word in words:
        h = int(hashlib.md5(word.encode()).hexdigest()[:16], 16)
        for i in range(FINGERPRINT_BITS):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1
    fingerprint = 0
    for i in range(FINGERPRINT_BITS):
        if v[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def similarity(a: int, b: int) -> float:
    return 1.0 - hamming_distance(a, b) / FINGERPRINT_BITS


def is_near_duplicate(
    new_fp: int,
    existing_fps: list[int],
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[bool, float]:
    if not existing_fps:
        return False, 0.0
    best = max(similarity(new_fp, ef) for ef in existing_fps)
    return best >= threshold, best


def extract_domain(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip("www.")


def is_navigation_path(path: str) -> bool:
    nav_patterns = [
        "/login",
        "/signup",
        "/register",
        "/forgot",
        "/privacy",
        "/terms",
        "/legal",
        "/cookie",
        "/account",
        "/profile",
        "/settings",
        "/cart",
        "/checkout",
        "/wishlist",
        "/faq",
        "/contact",
        "/about",
        "/careers",
        "/press",
        "/sitemap",
    ]
    lower = path.lower()
    for pat in nav_patterns:
        if lower.startswith(pat) or lower == pat:
            return True
    return False
