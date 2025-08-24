import os, random, time, asyncio
from fake_useragent import UserAgent
from robotexclusionrulesparser import RobotExclusionRulesParser
import httpx

_UA = UserAgent()

class RateLimiter:
    def __init__(self, rate_per_sec: float = 1.0):
        self.min_interval = 1.0 / max(rate_per_sec, 1e-6)
        self._last = 0.0
    async def wait(self):
        now = time.monotonic()
        delta = now - self._last
        if delta < self.min_interval:
            await asyncio.sleep(self.min_interval - delta)
        self._last = time.monotonic()

def randomized_headers(extra: dict | None = None) -> dict:
    h = {
        "User-Agent": _UA.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": random.choice(["en-US,en;q=0.9", "it-IT,it;q=0.9,en;q=0.8"]),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
    }
    if extra: h.update(extra)
    return h

def build_proxy_kwargs() -> dict:
    proxies = {}
    if os.getenv("HTTP_PROXY"):
        proxies["http://"] = os.getenv("HTTP_PROXY")
    if os.getenv("HTTPS_PROXY"):
        proxies["https://"] = os.getenv("HTTPS_PROXY")
    return {"proxies": proxies} if proxies else {}

async def fetch_robots_txt(base: str) -> RobotExclusionRulesParser | None:
    try:
        async with httpx.AsyncClient(timeout=10, **build_proxy_kwargs()) as client:
            r = await client.get(base.rstrip("/") + "/robots.txt", headers=randomized_headers())
            if r.status_code == 200 and r.text:
                rp = RobotExclusionRulesParser()
                rp.parse(r.text)
                return rp
    except Exception:
        return None
    return None

def allowed_by_robots(rp: RobotExclusionRulesParser | None, url: str) -> bool:
    if rp is None:
        return True
    try:
        return rp.is_allowed("*", url)
    except Exception:
        return True

def is_pec_email(email: str) -> bool:
    email_l = email.lower()
    for m in [".pec.it", ".pec.cloud", "@pec.", "postacert", "legalmail", "cert.legal", "poste-cert"]:
        if m in email_l: return True
    return False

def backoff_delay(try_idx: int, base_ms: int = 250, max_ms: int = 3500) -> float:
    ms = min(max_ms, base_ms * (2 ** try_idx))
    jitter = random.randint(0, int(ms * 0.3))
    return (ms + jitter) / 1000.0
