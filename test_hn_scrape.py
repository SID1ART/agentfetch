import asyncio
from agentfetch import smart_fetch, batch_fetch, search_fetch, parallel_search
from agentfetch.core.schema import ScrapeConfig, SearchConfig

async def test_smart_fetch():
    """Test smart_fetch on Hacker News"""
    print("=" * 60)
    print("Testing smart_fetch on Hacker News (static mode)")
    print("=" * 60)
    
    # Try static mode first since HN is a static site
    result = await smart_fetch(
        "https://news.ycombinator.com/",
        config=ScrapeConfig(
            max_content_length=10000,
            citation_links=True,
            exclude_tags=["nav", "footer", "script", "style"],
            include_tags=["table", "tr", "td", "a", "span"],
        ),
        engine="static"
    )
    
    print(f"URL: {result.url}")
    print(f"Title: {result.title}")
    print(f"Confidence: {result.confidence}")
    print(f"Content Type: {result.content_type}")
    print(f"Word Count: {result.word_count}")
    print(f"Render Mode: {result.render_mode}")
    print(f"Latency: {result.latency_ms}ms")
    print(f"Cached: {result.cached}")
    print(f"Injection Detected: {result.injection_detected}")
    print(f"Robots Allowed: {result.robots_allowed}")
    print(f"Links Found: {len(result.links)}")
    print(f"Citations: {len(result.citations)}")
    print(f"Error: {result.error}")
    print(f"\nContent Preview (first 2000 chars):")
    print(result.content[:2000])
    print("...")
    return result

async def test_batch_fetch():
    """Test batch_fetch on multiple HN pages"""
    print("\n" + "=" * 60)
    print("Testing batch_fetch on multiple HN pages")
    print("=" * 60)
    
    urls = [
        "https://news.ycombinator.com/",
        "https://news.ycombinator.com/newest",
        "https://news.ycombinator.com/ask",
        "https://news.ycombinator.com/show",
    ]
    
    results = await batch_fetch(urls, concurrency=4)
    
    for i, result in enumerate(results):
        print(f"\n--- Result {i+1}: {result.url} ---")
        print(f"Title: {result.title}")
        print(f"Confidence: {result.confidence}")
        print(f"Word Count: {result.word_count}")
        print(f"Render Mode: {result.render_mode}")
        print(f"Latency: {result.latency_ms}ms")
        print(f"Error: {result.error}")
        print(f"Content Preview: {result.content[:300]}...")
    
    return results

async def test_search_fetch():
    """Test search_fetch for Hacker News related queries"""
    print("\n" + "=" * 60)
    print("Testing search_fetch for 'Hacker News AI'")
    print("=" * 60)
    
    sr = await search_fetch(
        "Hacker News AI technology",
        sources=["duckduckgo", "bing"],
        max_results=3,
    )
    
    print(f"Query: {sr.query}")
    print(f"Sources Used: {sr.sources_used}")
    print(f"Total Results: {sr.total_results}")
    print(f"Errors: {sr.errors}")
    print(f"Suggestions: {sr.suggestions}")
    
    for i, result in enumerate(sr.results):
        print(f"\n--- Search Result {i+1}: {result.url} ---")
        print(f"Title: {result.title}")
        print(f"Confidence: {result.confidence}")
        print(f"Word Count: {result.word_count}")
        print(f"Render Mode: {result.render_mode}")
        print(f"Content Preview: {result.content[:300]}...")
    
    return sr

async def test_parallel_search():
    """Test parallel_search without scraping"""
    print("\n" + "=" * 60)
    print("Testing parallel_search for 'site:news.ycombinator.com AI'")
    print("=" * 60)
    
    engine_results, errors, suggestions = await parallel_search(
        "site:news.ycombinator.com AI",
        sources=["duckduckgo", "bing"],
        max_results=5,
    )
    
    print(f"Engine Results: {len(engine_results)}")
    print(f"Errors: {errors}")
    print(f"Suggestions: {suggestions}")
    
    for i, er in enumerate(engine_results):
        print(f"\n--- Engine Result {i+1}: {er.engine} ---")
        print(f"URL: {er.url}")
        print(f"Title: {er.title}")
        print(f"Snippet: {er.snippet}")
        print(f"Position: {er.position}")

async def main():
    print("Testing agentfetch on Hacker News (news.ycombinator.com)")
    print("Using all available methods...\n")
    
    # Test 1: Smart fetch
    await test_smart_fetch()
    
    # Test 2: Batch fetch
    await test_batch_fetch()
    
    # Test 3: Search fetch
    await test_search_fetch()
    
    # Test 4: Parallel search
    await test_parallel_search()
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())