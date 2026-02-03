from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    LLMConfig,
    LLMExtractionStrategy
)

from pydantic import BaseModel, Field

import asyncio
import sys
import json
import httpx
import os

ollama_api_key = os.getenv("OLLAMA_API_KEY")

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


app = FastAPI()
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "result": ""}
    )

class PageSummary(BaseModel):
    summary: str = Field(..., description="A single paragraph summary of the page content")

@app.post("/crawl", response_class=HTMLResponse)
async def crawl(request: Request, url: str = Form(...)):
    result_text = ""

    browser_conf = BrowserConfig(headless=True)

    llm_conf = LLMConfig(
        provider="ollama/llama3.2:latest",
        api_token=None,
        base_url="http://localhost:11434" 
    )

    extraction_strategy = LLMExtractionStrategy(
        llm_config=llm_conf,
        extraction_type="block",
        input_format="fit_markdown",
        apply_chunking=False,
        instruction="""From the crawled site, find out what the topic is about"""
    )

    run_conf = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        # extraction_strategy=extraction_strategy,
        exclude_external_links=True,    # Remove external links
        remove_overlay_elements=True,   # Remove popups/modals
        process_iframes=True,   
        verbose=True,
    )

    try:
        # async with AsyncWebCrawler(config=browser_conf) as crawler:
        #     result = await crawler.arun(
        #         url=url,
        #         config=run_conf,
        #     )
        #     result_text = result.markdown
        async with AsyncWebCrawler(config=browser_conf) as crawler:
            result = await crawler.arun(url=url, config=run_conf)
            raw_markdown = result.markdown

        # -------- STEP 2: OLLAMA WEB SEARCH --------
        ollama_api_key = os.getenv("OLLAMA_API_KEY")

        if not ollama_api_key:
            raise RuntimeError("OLLAMA_API_KEY not set in environment")

        async with httpx.AsyncClient(timeout=60.0) as client:
            search_resp = await client.post(
                "https://ollama.com/api/web_search",
                headers={
                    "Authorization": f"Bearer {ollama_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "query": f"Additional context and references about: {url}"
                }
            )

            if search_resp.status_code == 200:
                search_data = search_resp.json()
                search_context = json.dumps(search_data, indent=2)
            else:
                search_context = f"Web search failed: {search_resp.text}"

        # -------- STEP 3: COMBINED SUMMARIZATION --------
        async with httpx.AsyncClient(timeout=120.0) as client:
            ollama_response = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2:latest",
                    "prompt": f"""
You are summarizing a webpage using BOTH the crawled content and external sources.

=== CRAWLED PAGE CONTENT (PRIMARY SOURCE) ===
{raw_markdown}

=== WEB SEARCH RESULTS (SECONDARY SOURCES) ===
{search_context}

TASK:
- Produce detailed summarization about the page
- Explain what the page is about and its purpose
- Enrich the summary with external context if relevant
- Explain using the original language of the content
- Provide each explanation using the provided links, ex: Source:https://source-url.com
""",
                    "stream": False
                }
            )

            if ollama_response.status_code == 200:
                data = ollama_response.json()
                result_text = data.get("response", "No response from Ollama.")
            else:
                result_text = f"Ollama Error: {ollama_response.status_code} - {ollama_response.text}"

    except Exception as e:
        result_text = f"Error while crawling:\n{repr(e)}"

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "result": result_text,
            "url": url
        }
    )
