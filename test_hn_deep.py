import asyncio
from agentfetch import smart_fetch, batch_fetch
from agentfetch.core.schema import ScrapeConfig

async def test_individual_hn_posts():
    """Test scraping individual Hacker News posts and comments"""
    print("=" * 60)
    print("Testing individual HN post pages")
    print("=" * 60)
    
    # Get the front page first to find item IDs
    front_page = await smart_fetch(
        "https://news.ycombinator.com/",
        config=ScrapeConfig(
            max_content_length=10000,
            exclude_tags=["nav", "footer", "script", "style"],
            include_tags=["table", "tr", "td", "a", "span"],
        ),
        engine="static"
    )
    
    # Extract item URLs from the front page
    import re
    item_urls = re.findall(r'(https://news\.ycombinator\.com/item\?id=\d+)', front_page.content)
    # Also look for relative links
    relative_items = re.findall(r'(item\?id=\d+)', front_page.content)
    item_urls.extend([f"https://news.ycombinator.com/{u}" for u in relative_items])
    
    # Deduplicate
    item_urls = list(dict.fromkeys(item_urls))
    print(f"Found {len(item_urls)} item URLs on front page")
    
    # Test scraping first 3 item pages
    test_urls = item_urls[:3]
    
    for url in test_urls:
        print(f"\n--- Scraping: {url} ---")
        result = await smart_fetch(
            url,
            config=ScrapeConfig(
                max_content_length=15000,
                exclude_tags=["nav", "footer", "script", "style"],
                include_tags=["table", "tr", "td", "a", "span", "div"],
            ),
            engine="static"
        )
        print(f"Title: {result.title}")
        print(f"Confidence: {result.confidence}")
        print(f"Word Count: {result.word_count}")
        print(f"Render Mode: {result.render_mode}")
        print(f"Latency: {result.latency_ms}ms")
        print(f"Error: {result.error}")
        print(f"Content Preview: {result.content[:500]}...")

async def test_hn_user_pages():
    """Test scraping HN user pages"""
    print("\n" + "=" * 60)
    print("Testing HN user pages")
    print("=" * 60)
    
    # Test a known user
    test_users = ["pg", "dang", "sama"]
    
    for user in test_users:
        url = f"https://news.ycombinator.com/user?id={user}"
        print(f"\n--- Scraping: {url} ---")
        result = await smart_fetch(
            url,
            config=ScrapeConfig(
                max_content_length=15000,
                exclude_tags=["nav", "footer", "script", "style"],
            ),
            engine="static"
        )
        print(f"Title: {result.title}")
        print(f"Confidence: {result.confidence}")
        print(f"Word Count: {result.word_count}")
        print(f"Render Mode: {result.render_mode}")
        print(f"Latency: {result.latency_ms}ms")
        print(f"Error: {result.error}")
        print(f"Content Preview: {result.content[:500]}...")

async def main():
    await test_individual_hn_posts()
    await test_hn_user_pages()
    print("\n" + "=" * 60)
    print("ALL DEEP TESTS COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())