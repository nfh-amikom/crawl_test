import asyncio
from crawl4ai import AsyncUrlSeeder, AsyncWebCrawler, SeedingConfig, CrawlerRunConfig

async def smart_blog_crawler():
    # Step 1: Create our URL discoverer
    seeder = AsyncUrlSeeder()

    # Step 2: Configure discovery - let's find all blog posts
    config = SeedingConfig(
        source="cc",      # Use the website's sitemap+cc
        pattern="*/courses/*",    # Only courses related posts
        extract_head=True,          # Get page metadata
        max_urls=100               # Limit for this example
    )

    # Step 3: Discover URLs from the Python blog
    print("🔍 Discovering course posts...")
    urls = await seeder.urls("realpython.com", config)
    print(f"✅ Found {len(urls)} course posts")

    # Step 4: Filter for Python tutorials (using metadata!)
    tutorials = [
        url for url in urls 
        if url["status"] == "valid" and 
        any(keyword in str(url["head_data"]).lower() 
            for keyword in ["tutorial", "guide", "how to"])
    ]
    print(f"📚 Filtered to {len(tutorials)} tutorials")

    # Step 5: Show what we found
    print("\n🎯 Found these tutorials:")
    for tutorial in tutorials[:5]:  # First 5
        title = tutorial["head_data"].get("title", "No title")
        print(f"  - {title}")
        print(f"    {tutorial['url']}")

    # Step 6: Now crawl ONLY these relevant pages
    print("\n🚀 Crawling tutorials...")
    async with AsyncWebCrawler() as crawler:
        config = CrawlerRunConfig(
            only_text=True,
            word_count_threshold=300,  # Only substantial articles
            stream=True
        )

        # Extract URLs and crawl them
        tutorial_urls = [t["url"] for t in tutorials[:10]]
        results = await crawler.arun_many(tutorial_urls, config=config)

        successful = 0
        async for result in results:
            if result.success:
                successful += 1
                print(f"✓ Crawled: {result.url[:60]}...")

        print(f"\n✨ Successfully crawled {successful} tutorials!")

# Run it!
asyncio.run(smart_blog_crawler())
