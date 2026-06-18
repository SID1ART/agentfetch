import asyncio, json, time
from agentfetch import (
    smart_fetch,
    batch_fetch,
    search_fetch,
    parallel_search,
    stream_search,
    generate_query_variations,
    extract_highlights,
    extract_structured,
)
from agentfetch.core.schema import ScrapeConfig, FetchResult
from agentfetch.core.searchengine import EngineResult

PASS = 0
FAIL = 0
RESULTS = []


def ok(name, detail=""):
    global PASS
    PASS += 1
    RESULTS.append(f"  PASS {name} {detail}")


def fail(name, detail=""):
    global FAIL
    FAIL += 1
    RESULTS.append(f"  FAIL {name} {detail}")


def check(name, cond, detail=""):
    if cond:
        ok(name, detail)
    else:
        fail(name, detail)


async def test_1_smart_fetch_basic():
    """smart_fetch HN front page"""
    r = await smart_fetch("https://news.ycombinator.com/", engine="static")
    check("smart_fetch_basic", r.content and len(r.content) > 200, f"wc={r.word_count}")
    check("smart_fetch_title", r.title and "Hacker" in r.title, f"title={r.title}")
    check("smart_fetch_confidence", r.confidence > 0.5, f"conf={r.confidence}")
    check(
        "smart_fetch_links",
        r.links and len(r.links) > 5,
        f"links={len(r.links) if r.links else 0}",
    )
    return r


async def test_2_smart_fetch_with_highlights():
    """smart_fetch + extract_highlights"""
    r = await smart_fetch(
        "https://news.ycombinator.com/",
        engine="static",
        config=ScrapeConfig(extract_highlights=True),
    )
    check(
        "highlights_present",
        r.highlights is not None and len(r.highlights) > 0,
        f"highlights={r.highlights[:2] if r.highlights else 'none'}",
    )
    check(
        "highlights_are_strings",
        all(isinstance(h, str) for h in (r.highlights or [])),
        "",
    )
    return r


async def test_3_smart_fetch_structured_output():
    """smart_fetch + output_schema"""
    schema = {
        "type": "object",
        "properties": {
            "site_name": {"type": "string", "description": "Hacker News"},
            "num_stories": {
                "type": "integer",
                "description": "number of stories on front page",
            },
        },
    }
    r = await smart_fetch(
        "https://news.ycombinator.com/",
        engine="static",
        config=ScrapeConfig(output_schema=schema),
    )
    check(
        "structured_present",
        r.structured_output is not None,
        f"so={r.structured_output}",
    )
    if r.structured_output:
        check(
            "structured_site_name",
            r.structured_output.get("site_name") is not None,
            f"v={r.structured_output.get('site_name')}",
        )
    return r


async def test_4_smart_fetch_category_news():
    """smart_fetch with category='news' routing"""
    r = await smart_fetch(
        "https://news.ycombinator.com/",
        engine="static",
        config=ScrapeConfig(category="news"),
    )
    check("category_news_fetched", r.content and len(r.content) > 200, "")
    check("category_news_confidence_floor", r.confidence >= 0.4, f"conf={r.confidence}")
    return r


async def test_5_batch_fetch():
    """batch_fetch multiple HN pages"""
    urls = [
        "https://news.ycombinator.com/",
        "https://news.ycombinator.com/newest",
    ]
    results = await batch_fetch(urls, concurrency=2)
    check("batch_count", len(results) == 2, f"got {len(results)}")
    for i, r in enumerate(results):
        check(
            f"batch_{i}_content",
            r.content and len(r.content) > 100,
            f"wc={r.word_count}",
        )
    return results


async def test_6_parallel_search():
    """parallel_search with depth='deep'"""
    eng_results, engines_used, engine_errors = await parallel_search(
        "Hacker News AI",
        sources=["duckduckgo"],
        max_results=3,
        depth="deep",
    )
    check(
        "parallel_search_has_results", len(eng_results) > 0, f"count={len(eng_results)}"
    )
    check("parallel_search_engines", len(engines_used) > 0, f"engines={engines_used}")
    for i, er in enumerate(eng_results):
        check(f"parallel_result_{i}_url", bool(er.url), f"url={er.url}")
        check(f"parallel_result_{i}_source", bool(er.source), f"src={er.source}")
    return eng_results


async def test_7_parallel_search_with_category():
    """parallel_search with category modifier"""
    eng_results, _, _ = await parallel_search(
        "Hacker News",
        sources=["duckduckgo"],
        max_results=3,
        category="news",
    )
    check(
        "category_modifier_results", len(eng_results) > 0, f"count={len(eng_results)}"
    )
    return eng_results


async def test_8_stream_search():
    """stream_search"""
    seen = 0
    async for er in stream_search(
        "Hacker News AI", sources=["duckduckgo"], max_results=3
    ):
        check(f"stream_result_{seen}_url", bool(er.url), f"url={er.url}")
        seen += 1
        if seen >= 3:
            break
    check("stream_search_count", seen > 0, f"seen={seen}")
    return seen


async def test_9_search_fetch():
    """search_fetch full pipeline"""
    sr = await search_fetch(
        "Hacker News AI",
        sources=["duckduckgo"],
        max_results=2,
        scrape_results=True,
    )
    check("search_fetch_has_results", len(sr.results) > 0, f"count={len(sr.results)}")
    check("search_fetch_query", sr.query == "Hacker News AI", f"q={sr.query}")
    check(
        "search_fetch_sources_used",
        len(sr.sources_used) > 0,
        f"sources={sr.sources_used}",
    )
    for i, r in enumerate(sr.results):
        check(f"search_fetch_result_{i}_url", bool(r.url), "")
    return sr


async def test_10_search_fetch_with_category():
    """search_fetch with category news + depth deep"""
    sr = await search_fetch(
        "Hacker News",
        sources=["duckduckgo"],
        max_results=2,
        category="news",
        depth="deep",
    )
    check(
        "search_fetch_cat_has_results", len(sr.results) > 0, f"count={len(sr.results)}"
    )
    return sr


async def test_11_generate_query_variations():
    """generate_query_variations"""
    qs = generate_query_variations("Hacker News latest technology trends")
    check("query_variations_count", len(qs) >= 2, f"variations={qs}")
    check(
        "query_variations_original", qs[0] == "Hacker News latest technology trends", ""
    )
    return qs


async def test_12_direct_extract_highlights():
    """direct extract_highlights call"""
    text = "Python is a great language. It is used for AI and web development. Many people love Python for its simplicity. Data science relies heavily on Python. Machine learning frameworks use Python extensively."
    hl = extract_highlights(text, max_sentences=3)
    check("direct_highlights", len(hl) > 0 and len(hl) <= 3, f"count={len(hl)}")
    return hl


async def test_13_direct_extract_structured():
    """direct extract_structured call"""
    text = "The company has 1500 employees. Revenue is $500 million. It was founded in 2010. The CEO is Jane Smith."
    schema = {
        "type": "object",
        "properties": {
            "employees": {"type": "integer", "description": "number of employees"},
            "revenue_usd": {"type": "number", "description": "revenue"},
            "founded_year": {"type": "integer", "description": "founded"},
            "ceo": {"type": "string", "description": "CEO name"},
        },
    }
    so = extract_structured(text, schema)
    check("direct_structured", so is not None, f"so={so}")
    if so:
        check(
            "direct_structured_employees",
            so.get("employees") == 1500,
            f"emp={so.get('employees')}",
        )
        check(
            "direct_structured_ceo",
            so.get("ceo") and "Jane" in str(so.get("ceo")),
            f"ceo={so.get('ceo')}",
        )
    return so


async def test_14_batch_fetch_stories():
    """fetch individual HN story pages"""
    urls = [
        "https://news.ycombinator.com/item?id=1",
        "https://news.ycombinator.com/item?id=2",
    ]
    results = await batch_fetch(urls, concurrency=2)
    check("batch_stories_count", len(results) == 2, f"got {len(results)}")
    for i, r in enumerate(results):
        check(f"batch_story_{i}_no_crash", True, f"error={r.error}")
    return results


async def test_15_smart_fetch_ask_hn():
    """smart_fetch Ask HN page"""
    r = await smart_fetch("https://news.ycombinator.com/ask", engine="static")
    check("ask_hn_fetched", r.content and len(r.content) > 100, f"wc={r.word_count}")
    return r


async def main():
    print("=" * 65)
    print("  agentfetch HN Scrape: All Features Test")
    print("=" * 65)
    tests = [
        ("1.  smart_fetch basic", test_1_smart_fetch_basic),
        ("2.  smart_fetch + highlights", test_2_smart_fetch_with_highlights),
        ("3.  smart_fetch + structured output", test_3_smart_fetch_structured_output),
        ("4.  smart_fetch + category routing", test_4_smart_fetch_category_news),
        ("5.  batch_fetch", test_5_batch_fetch),
        ("6.  parallel_search (deep)", test_6_parallel_search),
        ("7.  parallel_search (category)", test_7_parallel_search_with_category),
        ("8.  stream_search", test_8_stream_search),
        ("9.  search_fetch", test_9_search_fetch),
        ("10. search_fetch (category+deep)", test_10_search_fetch_with_category),
        ("11. generate_query_variations", test_11_generate_query_variations),
        ("12. extract_highlights (direct)", test_12_direct_extract_highlights),
        ("13. extract_structured (direct)", test_13_direct_extract_structured),
        ("14. batch_fetch stories", test_14_batch_fetch_stories),
        ("15. smart_fetch Ask HN", test_15_smart_fetch_ask_hn),
    ]
    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            t0 = time.monotonic()
            await fn()
            ms = (time.monotonic() - t0) * 1000
            print(f"    done in {ms:.0f}ms")
        except Exception as e:
            fail(name, f"EXCEPTION: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 65)
    print(f"  RESULTS: {PASS} passed, {FAIL} failed out of {PASS + FAIL} total")
    print("=" * 65)
    for r in RESULTS:
        print(r)
    return PASS, FAIL


if __name__ == "__main__":
    asyncio.run(main())
