import os
import re
import time
from pathlib import Path
from urllib.parse import quote_plus

from backend.http_client import fetch_html as _fetch_html_core
from backend.rate_limiter import rate_limiter

DEBUG_DIR = Path(os.getenv("WREI_DEBUG_DIR", "/tmp/wrei_debug"))

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def fetch_html(url: str, portal: str = "default", timeout: float = 20.0) -> str:
    """
    Publiczne API dla scraperów.
    - Rate limiting per portal
    - Retry z backoff (w http_client)
    - Zapis debug HTML przy pustej odpowiedzi
    """
    rate_limiter.wait(portal)
    html = _fetch_html_core(url, timeout=timeout)

    if not html:
        _save_debug(url, portal, b"[EMPTY RESPONSE]")
    return html


def _save_debug(url: str, portal: str, content: bytes):
    """Zapisuje surową odpowiedź do /tmp/wrei_debug/ przy błędzie parsowania."""
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        safe_url = re.sub(r"[^\w]", "_", url)[:80]
        ts = int(time.time())
        path = DEBUG_DIR / f"{portal}_{ts}_{safe_url}.html"
        path.write_bytes(content)
    except Exception:
        pass


def save_debug_html(url: str, portal: str, html: str):
    """Wywołaj ręcznie z scrapera gdy parsowanie zwróci 0 wyników."""
    _save_debug(url, portal, html.encode("utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------

def build_query_string(params: dict) -> str:
    return "&".join(
        f"{quote_plus(k, safe='')}={quote_plus(str(v), safe='')}"
        for k, v in params.items()
    )


# ---------------------------------------------------------------------------
# Rooms normalization
# ---------------------------------------------------------------------------

def normalize_rooms_value(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        mapping = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6}
        if value.isdigit():
            return int(value)
        return mapping.get(value.upper())
    return None


def room_matches(query, listing_rooms) -> bool:
    if query is None or query == "":
        return True
    normalized = normalize_rooms_value(listing_rooms)
    if normalized is None:
        return False
    query = str(query).strip()
    if "," in query:
        choices = [int(p) for p in query.split(",") if p.strip().isdigit()]
        return normalized in choices
    if "-" in query:
        parts = [p.strip() for p in query.split("-")]
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]) <= normalized <= int(parts[1])
    if query.isdigit():
        return normalized == int(query)
    return False


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def apply_filters(
    listings: list[dict],
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, direct_only=False,
) -> list[dict]:
    filtered = []
    for listing in listings:
        price = listing.get("price")
        area = listing.get("area")
        if min_price is not None and (price is None or price < min_price):
            continue
        if max_price is not None and (price is None or price > max_price):
            continue
        if min_area is not None and area is not None and area < min_area:
            continue
        if max_area is not None and area is not None and area > max_area:
            continue
        if direct_only and not listing.get("direct_offer", False):
            continue
        if not room_matches(rooms, listing.get("rooms")):
            continue
        filtered.append(listing)
    return filtered


def deduplicate_listings(listings: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for listing in listings:
        key = listing.get("url") or listing.get("title")
        if key in seen:
            continue
        seen.add(key)
        unique.append(listing)
    return unique