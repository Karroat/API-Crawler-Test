import asyncio
from playwright.async_api import async_playwright
import json
import re
from urllib.parse import urlparse, urljoin, urldefrag
from datetime import datetime, timezone
import sys

# NEW: Import FastAPI and Pydantic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --- CONFIGURATION (Your existing configuration here) ---
IGNORE_PATH_KEYWORDS = [
    "privacy", "legal", "terms", "cookie", "contact", "support", "security", 
    "accessibility", "login", "account", "shop", "cart", "forum", "download",
    "driver", "events"
]
PRIORITY_PATH_KEYWORDS = [
    "about", "solution", "product", "industry", "enterprise", "company",
    "news", "press", "blog", "investor", "career", "platform", "who-we-are", "about us"
]
IGNORE_EXTENSIONS_PROTOCOLS = [
    ".pdf", ".zip", ".jpg", ".png", ".svg", ".css", ".js", ".xml", ".rss",
    "mailto:", "tel:", "javascript:"
]
IGNORE_LANG_CODES_REGEX = re.compile(r'^/([a-z]{2}(-[a-zA-Z]{2})?)/')
IGNORE_PATTERN_REGEX = re.compile(r'/(catalogue|item|product|page-)/|\d{4,}')
MAX_DEPTH = 2
MAX_PAGES = 25
CONCURRENCY = 5
PAGE_TIMEOUT = 15000  # ms
TOTAL_TIMEOUT = 45   # seconds - Aggressive timeout
MAX_TEXT_CHARS = 8000

# --- SCRIPT LOGIC (Your existing functions: clean_text, get_link_priority, etc.) ---
# ... (paste all your functions from clean_text to crawl_final here) ...

def clean_text(text: str) -> str:
    """Removes excess whitespace from text."""
    return re.sub(r'\s+', ' ', text).strip()

def get_link_priority(path: str) -> int:
    """Scores a link's relevance based on keywords."""
    path_lower = path.lower()
    if any(keyword in path_lower for keyword in PRIORITY_PATH_KEYWORDS):
        return 2  # High priority
    if path_lower == "/":
        return 1 # Medium priority for homepage
    return 0  # Low priority

def is_relevant_link(href: str, base_netloc: str) -> bool:
    """Checks if a link is internal and relevant."""
    if not href or href.startswith("#"):
        return False

    if any(href.lower().startswith(prefix) for prefix in IGNORE_EXTENSIONS_PROTOCOLS):
        return False

    parsed_href = urlparse(href)
    if parsed_href.netloc and parsed_href.netloc != base_netloc:
        return False

    path = parsed_href.path.lower()
    if any(keyword in path for keyword in IGNORE_PATH_KEYWORDS):
        return False
        
    if IGNORE_PATTERN_REGEX.search(path):
        return False
        
    return True

async def extract_main_content(page):
    """Removes common noise elements and extracts text from the main content area."""
    await page.evaluate("document.querySelectorAll('header, footer, nav, aside, script, style').forEach(el => el.remove())")
    
    main_content = await page.query_selector("main, article, .main-content, .content, #main, #content")
    if main_content:
        return await main_content.inner_text()
    return await page.locator("body").inner_text()

async def crawl_final(domain: str):
    # This function remains exactly the same as yours, but it will return data
    # instead of printing to the console or writing to a file.
    if not domain.startswith(("http://", "https://")):
        domain = "https://" + domain

    parsed_domain = urlparse(domain)
    base_url = f"{parsed_domain.scheme}://{parsed_domain.netloc}"
    base_netloc = parsed_domain.netloc
    
    initial_path = parsed_domain.path
    
    results = {}
    visited_urls = set()
    priority_queue = asyncio.PriorityQueue()

    start_url = urljoin(base_url, initial_path)
    await priority_queue.put((-3, start_url, 1)) # Highest priority
    visited_urls.add(start_url)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="ColetteBot/1.4 (+https://example.com/bot-info)")
        
        async def worker(worker_id):
            page = await context.new_page()
            while True:
                try:
                    priority, full_url, depth = await asyncio.wait_for(priority_queue.get(), timeout=3.0)

                    if len(results) >= MAX_PAGES:
                        priority_queue.task_done()
                        continue
                    
                    await page.goto(full_url, timeout=PAGE_TIMEOUT, wait_until="commit")
                    
                    text = await extract_main_content(page)
                    path_key = urlparse(full_url).path or "/"
                    
                    if "page not found" in text.lower() and len(text) < 150:
                         priority_queue.task_done()
                         continue

                    results[path_key] = clean_text(text)[:MAX_TEXT_CHARS]
                    # Removed the print statement for cleaner API logs

                    if depth < MAX_DEPTH:
                        links = await page.eval_on_selector_all("a[href]", "elements => elements.map(e => ({ href: e.getAttribute('href'), inNav: !!e.closest('nav') }))")
                        
                        unique_hrefs = {link['href'] for link in links if link['href']}

                        for href in unique_hrefs:
                            if is_relevant_link(href, base_netloc):
                                abs_url = urldefrag(urljoin(full_url, href)).url
                                if abs_url not in visited_urls:
                                    if len(visited_urls) < MAX_PAGES * 5:
                                        visited_urls.add(abs_url)
                                        link_priority = get_link_priority(urlparse(abs_url).path)
                                        # Check if the original link was in a nav
                                        if any(link.get('href') == href and link.get('inNav') for link in links):
                                            link_priority = 3 # Boost priority for nav links
                                        await priority_queue.put((-link_priority, abs_url, depth + 1))
                except asyncio.TimeoutError:
                    break
                except Exception as e:
                    if 'Target page, context or browser has been closed' not in str(e):
                        # Suppress noise during shutdown
                        pass
                finally:
                    if not priority_queue.empty():
                        priority_queue.task_done()
            await page.close()

        tasks = [asyncio.create_task(worker(i)) for i in range(CONCURRENCY)]
        
        try:
            await asyncio.wait_for(priority_queue.join(), timeout=TOTAL_TIMEOUT)
        except asyncio.TimeoutError:
            # Using print(file=sys.stderr) is good for logging on servers
            print(f"🚨 Total crawl timeout of {TOTAL_TIMEOUT}s reached.", file=sys.stderr)

        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await context.close()
        await browser.close()

    # MODIFIED: Instead of writing to a file, return the dictionary
    return {
        "domain": base_url,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "sections": results
    }

# --- NEW: FastAPI SERVER ---
app = FastAPI(
    title="Website Crawler API",
    description="An API to crawl a website and extract its main text content.",
    version="1.0.0"
)

# Pydantic model for input validation
class CrawlRequest(BaseModel):
    domain: str

@app.post("/crawl/", summary="Crawl a website")
async def run_crawl(request: CrawlRequest):
    """
    Takes a domain, crawls it based on predefined rules, and returns the extracted text content.
    """
    try:
        print(f"Starting crawl for {request.domain}...")
        data = await crawl_final(request.domain)
        if not data["sections"]:
            raise HTTPException(status_code=404, detail="Could not crawl the domain or found no content.")
        print(f"Crawl for {request.domain} successful, found {len(data['sections'])} pages.")
        return data
    except Exception as e:
        print(f"An error occurred during crawl for {request.domain}: {e}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {str(e)}")

# Remove the old __main__ block
# if __name__ == "__main__":
#     asyncio.run(main())