from dotenv import load_dotenv
load_dotenv()

import asyncio
import sys
import os
import json
import re
from typing import List

import httpx
from fastapi import FastAPI, Form, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from rank_bm25 import BM25Okapi

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
)

# ------------------------------------------------------------------

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")

if not OLLAMA_API_KEY:
    raise RuntimeError("OLLAMA_API_KEY not set")

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ------------------------------------------------------------------

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "result": "", "url": ""}
    )

# ------------------------------------------------------------------
# UTILITIES
# ------------------------------------------------------------------

def tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())

# ------------------------------------------------------------------
# CORE PIPELINE
# ------------------------------------------------------------------

@app.get("/crawl")
async def crawl(request: Request, url: str = Query(...)):

    browser_conf = BrowserConfig(headless=True)
    run_conf = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        exclude_external_links=True,
        remove_overlay_elements=True,
        process_iframes=True,
        verbose=False,
    )

    # ------------------------------------------------------------
    # STEP 1 — CRAWL MAIN URL
    # ------------------------------------------------------------
    async with AsyncWebCrawler(config=browser_conf) as crawler:
        result = await crawler.arun(url=url, config=run_conf)
        raw_markdown = result.markdown

    query_tokens = tokenize(raw_markdown)[:200]

    # ------------------------------------------------------------
    # STEP 1.1 — URL SEEDING VIA OLLAMA WEB SEARCH
    # ------------------------------------------------------------
    async with httpx.AsyncClient(timeout=60.0) as client:
        search_resp = await client.post(
            "https://ollama.com/api/web_search",
            headers={
                "Authorization": f"Bearer {OLLAMA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"query": url},
        )

    search_data = search_resp.json()
    candidates = search_data.get("results", [])

    documents = []
    urls = []

    for item in candidates:
        snippet = item.get("snippet", "")
        if snippet:
            documents.append(tokenize(snippet))
            urls.append(item.get("url"))

    if not documents:
    # No candidates → fallback to main URL only
        print("[WARN] No BM25 candidates found, falling back to main URL")
        seed_urls = [url]
    else:
        bm25 = BM25Okapi(documents)
        scores = bm25.get_scores(query_tokens)

        ranked = sorted(
            zip(urls, scores, documents),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        seed_urls = [r[0] for r in ranked]

    # ------------------------------------------------------------
    # STEP 1.1 — BM25 RANKING
    # ------------------------------------------------------------
    bm25 = BM25Okapi(documents)
    scores = bm25.get_scores(query_tokens)

    ranked = sorted(
        zip(urls, scores, documents),
        key=lambda x: x[1],
        reverse=True
    )[:5]

    seed_urls = [r[0] for r in ranked]

    # ------------------------------------------------------------
    # STEP 2 — SUMMARIZE EACH SEED URL (WEB SEARCH)
    # ------------------------------------------------------------
    seed_summaries = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for seed in seed_urls:
            resp = await client.post(
                "https://ollama.com/api/web_search",
                headers={
                    "Authorization": f"Bearer {OLLAMA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"query": seed},
            )
            data = resp.json()
            summary = json.dumps(data, indent=2)
            seed_summaries.append((seed, summary))

    # ------------------------------------------------------------
    # STEP 3 — STREAM LLaMA 3.2 OUTPUT
    # ------------------------------------------------------------
    async def event_stream():

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2:latest",
                    "stream": True,
                    "prompt": f"""
You are an evidence-based fact checker.

PRIMARY SOURCE:
{raw_markdown}

SECONDARY SOURCES:
{chr(10).join([f"{u}: {s}" for u, s in seed_summaries])}

TASK:
1. Summarize the primary source
2. Cross-check against secondary sources
3. Output '==END=='
4. Then output:

SCORES:
MAIN_URL | score=FLOAT
<url> | score=FLOAT
"""
                },
            ) as r:

                async for line in r.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("response", "")
                    yield f"data: {token}\n\n"

                    if "==END==" in token:
                        break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )
