from __future__ import annotations
import os, asyncio
from typing import Optional
import httpx
from .utils import randomized_headers, backoff_delay, build_proxy_kwargs

class HttpFetcher:
    def __init__(self, max_retries: int = 3, max_wait_ms: int = 2000):
        self.max_retries = max_retries
        self.max_wait_ms = max_wait_ms

    async def fetch(self, url: str) -> tuple[int, str]:
        async with httpx.AsyncClient(http2=True, timeout=20, **build_proxy_kwargs()) as client:
            last_exc: Optional[Exception] = None
            for i in range(self.max_retries):
                try:
                    r = await client.get(url, headers=randomized_headers())
                    if r.status_code in (200, 201):
                        await asyncio.sleep(self.max_wait_ms / 1000.0)
                        return r.status_code, r.text
                    if r.status_code in (403, 429, 500, 502, 503):
                        await asyncio.sleep(backoff_delay(i))
                        continue
                    return r.status_code, r.text
                except Exception as e:
                    last_exc = e
                    await asyncio.sleep(backoff_delay(i))
            if last_exc:
                raise last_exc
            raise RuntimeError("Fetch failed without exception")

# --------------------- Selenium headless ---------------------
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ChromeOptions

class BrowserFetcher:
    def __init__(self, max_wait_ms: int = 2000):
        self.max_wait_ms = max_wait_ms
        self._driver = None

    def _build_driver(self):
        opts = ChromeOptions()
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1365,800")
        proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
        if proxy:
            opts.add_argument(f"--proxy-server={proxy}")
        return uc.Chrome(options=opts)

    def _ensure_driver(self):
        if self._driver is None:
            self._driver = self._build_driver()

    def close(self) -> None:
        try:
            if self._driver:
                self._driver.quit()
        finally:
            self._driver = None

    def fetch_sync(self, url: str) -> tuple[int, str]:
        self._ensure_driver()
        d = self._driver
        d.get(url)
        try:
            WebDriverWait(d, max(1, self.max_wait_ms // 1000)).until(
                lambda drv: drv.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass
        try:
            WebDriverWait(d, min(5, max(1, self.max_wait_ms // 1000))).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            pass
        html = d.page_source or ""
        return 200, html
