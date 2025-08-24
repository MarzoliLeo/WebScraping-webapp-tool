from typing import List, Tuple
from urllib.parse import urlsplit
from .fetchers import HttpFetcher, BrowserFetcher
from .parsers import parse_entity
from .site_adapters import apply_adapters
from .utils import fetch_robots_txt, allowed_by_robots
import os

async def scrape_url(url: str, use_browser: bool = True, max_wait_ms: int = 2000, respect_robots: bool = True) -> Tuple[List[dict], List[str]]:
    errors: List[str] = []
    url = str(url)  # garanzia

    if respect_robots:
        try:
            parts = urlsplit(url)
            base_url = f"{parts.scheme}://{parts.netloc}"
            rp = await fetch_robots_txt(base_url)
            if not allowed_by_robots(rp, url):
                return [], [f"Blocked by robots.txt: {url}"]
        except Exception as e:
            errors.append(f"robots.txt check failed: {e}")

    http_fetcher = HttpFetcher(max_retries=3, max_wait_ms=max_wait_ms)
    try:
        status, html = await http_fetcher.fetch(url)
        if status == 200 and html:
            html = apply_adapters(url, html)
            parsed = parse_entity(html, url)
            return parsed["items"], errors
    except Exception as e:
        errors.append(f"http fetch error: {e}")

    if use_browser and not os.getenv("DISABLE_BROWSER"):
        bf = BrowserFetcher(max_wait_ms=max_wait_ms)
        try:
            status, html = bf.fetch_sync(url)
            html = apply_adapters(url, html)
            parsed = parse_entity(html, url)
            return parsed["items"], errors
        except Exception as e:
            errors.append(f"browser fetch error: {e}")
        finally:
            bf.close()

    return [], errors
