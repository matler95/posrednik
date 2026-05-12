import os
import re
import time
from pathlib import Path
from urllib.parse import quote_plus

from backend.http_client import fetch_html as _fetch_html_core
from backend.rate_limiter import rate_limiter

DEBUG_DIR = Path(os.getcwd()) / "debug_scrapers"

def fetch_html(url: str, portal: str = "default", timeout: float = 20.0) -> str:
    rate_limiter.wait(portal)
    html = _fetch_html_core(url, timeout=timeout)
    if html:
        save_debug_html(url, portal, html)
    else:
        _save_debug(url, portal, b"[EMPTY RESPONSE]")
    return html

def _save_debug(url: str, portal: str, content: bytes):
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        safe_url = re.sub(r"[^\w]", "_", url)[:80]
        ts = int(time.time())
        path = DEBUG_DIR / f"{portal}_{ts}_{safe_url}.html"
        path.write_bytes(content)
    except Exception:
        pass

def save_debug_html(url: str, portal: str, html: str):
    _save_debug(url, portal, html.encode("utf-8", errors="replace"))

def build_query_string(params: dict) -> str:
    return "&".join(f"{quote_plus(k, safe='')}={quote_plus(str(v), safe='')}" for k, v in params.items())

def normalize_rooms_value(value) -> int | None:
    if value is None: return None
    if isinstance(value, int): return value
    if isinstance(value, str):
        mapping = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6}
        if value.isdigit(): return int(value)
        return mapping.get(value.upper())
    return None


def validate_listing(listing: dict) -> bool:
    """
    Sprawdza, czy oferta ma sensowne dane (nie jest anomalią).
    Zwraca True, jeśli oferta przechodzi walidację.
    """
    price = listing.get("price")
    area = listing.get("area")
    url = listing.get("url")
    title = listing.get("title")

    if not url or not title:
        return False

    # 1. Zakresy bazowe
    if not price or not (10_000 <= price <= 100_000_000):
        return False
    if not area or not (5 <= area <= 2000):
        return False

    # 2. Anomalie ceny za m2
    psm = listing.get("price_per_m2")
    if not psm and area > 0:
        psm = price / area

    if psm:
        # Poniżej 2000 zł/m2 to błąd (chyba że dom, ale tu celujemy w mieszkania)
        # Powyżej 100 000 zł/m2 to prawdopodobnie błąd przecinkowy
        if not (2_000 <= psm <= 100_000):
            return False

    return True

def room_matches(query, listing_rooms) -> bool:
    if query is None or query == "" or (isinstance(query, list) and len(query) == 0): 
        return True
    
    normalized = normalize_rooms_value(listing_rooms)
    if normalized is None: 
        return False
        
    if isinstance(query, list):
        # Wsparcie dla listy pokoi [2, 3] z hunt_config
        choices = []
        for q in query:
            if isinstance(q, int): choices.append(q)
            elif isinstance(q, str) and q.isdigit(): choices.append(int(q))
        return normalized in choices if choices else True

    query_str = str(query).strip()
    if "," in query_str:
        choices = [int(p) for p in query_str.split(",") if p.strip().isdigit()]
        return normalized in choices
    if "-" in query_str:
        parts = [p.strip() for p in query_str.split("-")]
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]) <= normalized <= int(parts[1])
    if query_str.isdigit(): 
        return normalized == int(query_str)
    return False

def apply_filters(listings: list[dict], min_price=None, max_price=None, min_area=None, max_area=None, rooms=None, direct_only=False) -> list[dict]:
    filtered = []
    for listing in listings:
        price = listing.get("price")
        area = listing.get("area")
        if min_price is not None and (price is None or price < min_price): continue
        if max_price is not None and (price is None or price > max_price): continue
        if min_area is not None and area is not None and area < min_area: continue
        if max_area is not None and area is not None and area > max_area: continue
        if direct_only and not listing.get("direct_offer", False): continue
        if not room_matches(rooms, listing.get("rooms")): continue
        filtered.append(listing)
    return filtered

def deduplicate_listings(listings: list[dict]) -> list[dict]:
    best = {}
    for listing in listings:
        key = listing.get("url") or listing.get("title")
        if not key: continue
        
        if key in best:
            curr_updated = listing.get("updated_at")
            best_updated = best[key].get("updated_at")
            
            if curr_updated and best_updated:
                if curr_updated > best_updated:
                    best[key] = listing
            elif curr_updated and not best_updated:
                best[key] = listing
        else:
            best[key] = listing
            
    return list(best.values())

def extract_price(text: str) -> int | None:
    if not text: return None
    clean = re.sub(r"[^\d]", "", text)
    try: return int(clean)
    except: return None

def extract_area_from_text(text: str) -> float | None:
    if not text: return None
    match = re.search(r"(\d+[\.,]?\d*)\s*m", text.lower())
    if match:
        val = match.group(1).replace(",", ".")
        try: return float(val)
        except: return None
    return None