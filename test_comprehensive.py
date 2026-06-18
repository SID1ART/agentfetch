import asyncio
from agentfetch import smart_fetch, batch_fetch, search_fetch, parallel_search
from agentfetch.core.schema import ScrapeConfig

async def test_all_methods():
    """Comprehensive test of all agentfetch methods on HN"""
    
    print("=" * 70)
    print("COMPREHENSIVE AGENTFETCH TEST ON HACKER NEWS")
    print("=" * 70)
    
    # Test 1: smart_fetch with different configs
    print("\n1. SMART_FETCH - Front page (auto mode)")
    result = await smart_fetch("https://news.ycombinator.com/")
    print(f"   Mode: {result.render_mode}, Confidence: {result.confidence}, Words: {result.word_count}, Error: {result.error}")
    
    print("\n2. SMART_FETCH - Front page (static mode with table tags)")
    result = await smart_fetch(
        "https://news.ycombinator.com/",
        config=ScrapeConfig(
            max_content_length=20000,
            include_tags=["table", "tr", "td", "a", "span", "td.subtext"],
            citation_links=True,
        ),
        engine="static"
    )
    print(f"   Mode: {result.render_mode}, Confidence: {result.confidence}, Words: {result.word_count}, Citations: {len(result.citations) if result.citations else 0}")
    print(f"   Links: {len(result.links) if result.links else 0}")
    print(f"   Preview: {result.content[:300]}...")
    
    # Test 3: batch_fetch
    print("\n3. BATCH_FETCH - Multiple pages")
    urls = [
        "https://news.ycombinator.com/",
        "https://news.ycombinator.com/newest",
        "https://news.ycombinator.com/ask",
        "https://news.ycombinator.com/show",
    ]
    results = await batch_fetch(urls, concurrency=4)
    for r in results:
        print(f"   {r.url}: {r.word_count} words, {r.render_mode}, {r.confidence} conf, {r.latency_ms}ms")
    
    # Test 4: search_fetch
    print("\n4. SEARCH_FETCH - 'Hacker News'")
    sr = await search_fetch("Hacker News", sources=["duckduckgo"], max_results=3)
    print(f"   Sources: {sr.sources_used}, Results: {len(sr.results)}, Errors: {sr.errors}")
    for r in sr.results:
        print(f"   {r.url}: {r.word_count} words, conf={r.confidence}")
    
    # Test 5: parallel_search (no scrape)
    print("\n5. PARALLEL_SEARCH - 'site:news.ycombinator.com'")
    eng_results, errors, suggestions = await parallel_search(
        "site:news.ycombinator.com AI", 
        sources=["duckduckgo"], 
        max_results=5
    )
    print(f"   Engine results: {len(eng_results)}, Errors: {errors}")
    for er in eng_results[:3]:
        print(f"   {er.engine}: {er.title[:60]}... ({er.url[:60]})")
    
    # Test 6: Test with wait_for and js_wait_ms (browser mode)
    print("\n6. SMART_FETCH - Browser mode test (with wait_for)")
    result = await smart_fetch(
        "https://news.ycombinator.com/",
        config=ScrapeConfig(
            wait_for=".athing",
            js_wait_ms=1000,
        ),
        engine="browser"
    )
    print(f"   Mode: {result.render_mode}, Confidence: {result.confidence}, Words: {result.word_count}, Error: {result.error}")
    
    # Test 7: Individual item page
    print("\n7. SMART_FETCH - Individual item page")
    result = await smart_fetch(
        "https://news.ycombinator.com/item?id=48581350",
        config=ScrapeConfig(
            max_content_length=15000,
            include_tags=["table", "tr", "td", "a", "span", "div"],
        ),
        engine="static"
    )
    print(f"   Mode: {result.render_mode}, Confidence: {result.confidence}, Words: {result.word_count}, Error: {result.error}")
    print(f"   Preview: {result.content[:300]}...")
    
    # Test 8: User page
    print("\n8. SMART_FETCH - User profile")
    result = await smart_fetch(
        "https://news.ycombinator.com/user?id=pg",
        config=ScrapeConfig(max_content_length=15000),
        engine="static"
    )
    print(f"   Mode: {result.render_mode}, Confidence: {result.confidence}, Words: {result.word_count}, Error: {result.error}")
    print(f"   Preview: {result.content[:300]}...")
    
    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_all_methods())