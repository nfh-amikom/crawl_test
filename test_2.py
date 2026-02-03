import asyncio
from crawl4ai import AsyncUrlSeeder, AsyncWebCrawler, SeedingConfig, CrawlerRunConfig

async def smart_blog_crawler():
    seeder = AsyncUrlSeeder()

    config = SeedingConfig(
        source="sitemap+cc",
        extract_head=True,
        query="politics",
        max_urls=50,
        scoring_method="bm25",
        score_threshold=0.5
    )

    print("🔍 Discovering posts...")
    urls = await seeder.urls("tribunnews.com", config)
    print(f"✅ Found {len(urls)} posts")

    valid_urls = [u for u in urls if u.get("status") == "valid"]
    print(f"📚 Filtered to {len(valid_urls)} valid urls")

    print("\n🎯 Found these posts:")
    for valid_url in valid_urls[:5]:
        head = valid_url.get("head_data") or {}
        title = head.get("title", "No title")
        print(f"  - {title}")
        print(f"    {valid_url['url']}")

    print("\n🚀 Crawling urls...")
    async with AsyncWebCrawler() as crawler:
        crawl_config = CrawlerRunConfig(
            only_text=True,
            word_count_threshold=300,
            stream=True
        )

        urls_to_crawl = [u["url"] for u in valid_urls[:10]]
        results = await crawler.arun_many(urls_to_crawl, config=crawl_config)

        successful = 0
        async for result in results:
            if result.success:
                successful += 1
                print(f"Crawled: {result.url[:60]}...")

        print(f"\n✨ Successfully crawled {successful} urls!")

asyncio.run(smart_blog_crawler())
