from __future__ import annotations
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from typing import List

# Adapter pattern: add site-specific tweaks when needed.

class BaseAdapter:
    domains: List[str] = []

    def applies(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(d in host for d in self.domains)

    def pre_process(self, html: str) -> str:
        # Optionally clean/expand HTML before generic parsing
        return html

class TripAdvisorAdapter(BaseAdapter):
    domains = ["tripadvisor."]

    def pre_process(self, html: str) -> str:
        # TA often hides emails/phones; generic extraction may still catch visible info.
        # Here we could add future heuristics if needed.
        return html

ADAPTERS = [TripAdvisorAdapter()]


def apply_adapters(url: str, html: str) -> str:
    for a in ADAPTERS:
        if a.applies(url):
            return a.pre_process(html)
    return html
