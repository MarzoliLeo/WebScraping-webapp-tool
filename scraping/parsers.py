from __future__ import annotations
import json, re, html, unicodedata
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
import extruct
from w3lib.html import get_base_url
from urllib.parse import urljoin

from .utils import is_pec_email

# Regex di fallback
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}")

# Tipi schema.org che teniamo come "entity" valida
ALLOWED_TYPES = {"Restaurant", "FoodEstablishment", "LocalBusiness", "Hotel", "LodgingBusiness"}

def _clean_text(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    # converti entità HTML & unicode escapes visive (\u0027)
    s = s.replace("\\u0027", "'").replace("\\u0026", "&")
    s = html.unescape(s)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None

def _collect_emails(html_text: str) -> List[str]:
    raw = set(m.group(0) for m in _EMAIL_RE.finditer(html_text))
    return sorted([e for e in raw if not is_pec_email(e) and not e.lower().startswith("no-reply")])

def _collect_phones(text: str) -> List[str]:
    raw = set(m.group(0) for m in _PHONE_RE.finditer(text))
    out: List[str] = []
    for p in raw:
        # normalizza ma mantieni il formato umano in output
        digits = re.sub(r"\D", "", p)
        if len(digits) >= 7:
            out.append(_clean_text(p) or p)
    return sorted(set(out))

def _extract_structured(html_doc: str, url: str) -> Dict[str, Any]:
    base = get_base_url(html_doc, url)
    return extruct.extract(html_doc, base_url=base, syntaxes=["json-ld", "microdata", "opengraph", "rdfa"])

def _type_matches(t: Any, allowed: set[str]) -> bool:
    if isinstance(t, str):
        return t in allowed
    if isinstance(t, list):
        return any(isinstance(x, str) and x in allowed for x in t)
    return False

def _address_fields(addr: Any) -> Dict[str, Optional[str]]:
    out = {"address": None, "locality": None, "region": None, "postal_code": None, "country": None}
    if isinstance(addr, dict):
        out["address"] = _clean_text(addr.get("streetAddress") or addr.get("addressLine1") or addr.get("street"))
        out["locality"] = _clean_text(addr.get("addressLocality"))
        out["region"] = _clean_text(addr.get("addressRegion"))
        out["postal_code"] = _clean_text(addr.get("postalCode"))
        out["country"] = _clean_text(addr.get("addressCountry"))
    return out

def _rating(block: dict) -> Optional[float]:
    r = block.get("aggregateRating")
    if isinstance(r, dict):
        val = r.get("ratingValue")
        try:
            return float(val)
        except Exception:
            return None
    return None

def _entity_from_jsonld_item(item: dict, source_url: str) -> dict:
    # item è un blocco Restaurant/LocalBusiness
    name = _clean_text(item.get("name"))
    addr = _address_fields(item.get("address"))
    tel = item.get("telephone")
    phones = []
    if tel:
        tel = _clean_text(str(tel))
        if tel:
            phones = [tel]
    ent = {
        "entity_type": "Restaurant" if _type_matches(item.get("@type"), {"Restaurant"}) else _clean_text(item.get("@type") if isinstance(item.get("@type"), str) else None),
        "name": name,
        **addr,
        "phones": phones,
        "emails": [],  # quasi mai presenti in TA
        "website": _clean_text(item.get("url") or source_url),
        "socials": {},
        "geo": None,
        "categories": [],
        "rating": _rating(item),
    }
    # punteggio qualità semplice
    score = 0
    score += 30 if name else 0
    score += 25 if phones else 0
    score += 10 if ent["website"] else 0
    score += 10 if ent["address"] else 0
    score += 25 if ent["rating"] is not None else 0
    ent["data_quality"] = float(min(100, score))
    return ent

def _from_itemlist(block: dict, source_url: str) -> List[dict]:
    items: List[dict] = []
    elems = block.get("itemListElement")
    if not isinstance(elems, list):
        return items
    for li in elems:
        if not isinstance(li, dict):
            continue
        item = li.get("item")
        if not isinstance(item, dict):
            continue
        if _type_matches(item.get("@type"), ALLOWED_TYPES):
            items.append(_entity_from_jsonld_item(item, source_url))
    return items

def parse_entity(html_doc: str, url: str) -> Dict[str, List[dict]]:
    soup = BeautifulSoup(html_doc, "lxml")
    data = _extract_structured(html_doc, url)
    results: List[dict] = []

    # 1) Se c'è un ItemList con ristoranti, estrai direttamente le schede (solo ristoranti).
    for block in data.get("json-ld", []):
        if isinstance(block, dict) and block.get("@type") == "ItemList":
            items = _from_itemlist(block, url)
            if items:
                results.extend(items)

    # 2) Se non abbiamo trovato nulla via ItemList, cerca blocchi singoli Restaurant/LocalBusiness/Hotel ecc.
    if not results:
        for block in data.get("json-ld", []):
            if not isinstance(block, dict):
                continue
            if _type_matches(block.get("@type"), ALLOWED_TYPES):
                results.append(_entity_from_jsonld_item(block, url))

    # 3) Fallback minimale: estrai email/phone visibili nella pagina – ma solo se NON abbiamo nulla.
    if not results:
        page_text = soup.get_text("\n", strip=True)
        phones = _collect_phones(page_text)
        emails = _collect_emails(html_doc)
        if phones or emails:
            results.append({
                "entity_type": None,
                "name": _clean_text(soup.title.string) if soup.title and soup.title.string else None,
                "address": None, "locality": None, "region": None, "postal_code": None, "country": None,
                "phones": phones, "emails": emails,
                "website": url, "socials": {}, "geo": None, "categories": [],
                "rating": None,
                "data_quality": float(min(100, (25 if phones else 0) + (25 if emails else 0) + (10 if url else 0))),
            })

    return {"items": results}
