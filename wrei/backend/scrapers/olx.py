"""
OLX scraper — pobiera ogłoszenia nieruchomości z OLX.pl.
Używa __NEXT_DATA__ JSON zamiast kruchego regex na HTML.
Fallback: Apollo cache w oknie globalnym.
"""
import json
import re
import logging

from backend.scraper_utils import (
    apply_filters,
    fetch_html,
    extract_area_from_text,
    validate_listing,
)

logger = logging.getLogger(__name__)

OLX_BASE = "https://www.olx.pl/nieruchomosci/mieszkania/sprzedaz/warszawa"


def available():
    return "olx"


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------

ROOMS_MAP = {
    "1": "one", "2": "two", "3": "three",
    "4": "four", "5": "five", "6": "six",
}

DISTRICT_SLUGS = {
    "Bemowo": "bemowo", "Białołęka": "bialoleka", "Bielany": "bielany",
    "Mokotów": "mokotow", "Ochota": "ochota", "Praga-Południe": "praga-poludnie",
    "Praga-Północ": "praga-polnoc", "Śródmieście": "srodmiescie",
    "Targówek": "targowek", "Ursus": "ursus", "Ursynów": "ursynow",
    "Wawer": "wawer", "Wilanów": "wilanow", "Włochy": "wlochy",
    "Wola": "wola", "Żoliborz": "zoliborz",
}


def build_olx_url(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, direct_only=False,
    page=1, district=None,
) -> str:
    params = []

    if min_price:
        params.append(f"search[filter_float_price:from]={int(min_price)}")
    if max_price:
        params.append(f"search[filter_float_price:to]={int(max_price)}")
    if min_area:
        params.append(f"search[filter_float_m:from]={int(min_area)}")
    if max_area:
        params.append(f"search[filter_float_m:to]={int(max_area)}")

    if rooms:
        room_list = rooms if isinstance(rooms, list) else [str(rooms)]
        for r in room_list:
            mapped = ROOMS_MAP.get(str(r))
            if mapped:
                params.append(f"search[filter_enum_rooms][0]={mapped}")

    if direct_only:
        params.append("search[filter_enum_advertiser_type][0]=private")

    if page > 1:
        params.append(f"page={page}")

    # Baza URL z opcjonalną dzielnicą
    if district and district in DISTRICT_SLUGS:
        base = f"{OLX_BASE}/{DISTRICT_SLUGS[district]}"
    else:
        base = OLX_BASE

    return f"{base}?{'&'.join(params)}" if params else base


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def _extract_next_data(html: str) -> dict:
    """Wyciąga __NEXT_DATA__ z HTML OLX w sposób odporny na zmiany."""
    try:
        # Próbujemy znaleźć tag script o dowolnym ID zawierający NEXT_DATA
        pattern = r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>'
        match = re.search(pattern, html, re.S)
        if match:
            return json.loads(match.group(1))
        
        # Fallback: szukamy samej zmiennej w kodzie JS
        pattern_js = r'__NEXT_DATA__\s*=\s*(\{.*?\});'
        match_js = re.search(pattern_js, html, re.S)
        if match_js:
            return json.loads(match_js.group(1))
    except Exception as e:
        logger.warning("[OLX] Błąd ekstrakcji JSON: %s", e)
    return {}


def _find_listings_in_payload(payload: dict) -> list[dict]:
    """Znajduje listę ogłoszeń w różnych możliwych miejscach JSON OLX."""
    paths = [
        # Nowa struktura OLX
        lambda p: p.get("props", {}).get("pageProps", {}).get("listing", {}).get("listing", {}).get("ads", []),
        # Starsza struktura
        lambda p: p.get("props", {}).get("pageProps", {}).get("ads", []),
        # Inna możliwa ścieżka
        lambda p: p.get("props", {}).get("pageProps", {}).get("data", {}).get("ads", []),
    ]
    for path_fn in paths:
        try:
            result = path_fn(payload)
            if result and isinstance(result, list) and len(result) > 0:
                return result
        except (AttributeError, TypeError):
            continue
    return []


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def _get_param(params: list, key: str) -> str | None:
    """Pobiera wartość parametru z listy {key, value} OLX."""
    for p in params:
        if isinstance(p, dict) and p.get("key") == key:
            val = p.get("value")
            if isinstance(val, list) and val:
                return val[0]
            return val
    return None


def _normalize_olx_listing(item: dict) -> dict | None:
    """Normalizuje jeden rekord OLX."""
    # Cena
    price_obj = item.get("price") or {}
    price = None
    if isinstance(price_obj, dict):
        price_val = price_obj.get("value", {})
        if isinstance(price_val, dict):
            price = price_val.get("value") or price_val.get("amount")
        elif isinstance(price_val, (int, float)):
            price = price_val
    if not price:
        # Fallback z regularPrice
        reg = item.get("regularPrice") or {}
        if isinstance(reg, dict):
            price = reg.get("value", {}).get("value") if isinstance(reg.get("value"), dict) else reg.get("value")

    if not price:
        return None
    try:
        price = int(float(str(price).replace(" ", "")))
    except (ValueError, TypeError):
        return None

    # Parametry
    params = item.get("params") or []

    # Metraż
    area = None
    area_raw = _get_param(params, "m")
    if area_raw:
        try:
            area = float(str(area_raw).replace(",", ".").replace(" ", ""))
        except (ValueError, TypeError):
            pass
    if not area:
        area = extract_area_from_text(item.get("title") or "")

    # Pokoje
    rooms = _get_param(params, "rooms") or _get_param(params, "number_of_rooms")
    rooms_map_rev = {
        "one": "1", "two": "2", "three": "3",
        "four": "4", "five": "5", "six": "6",
    }
    if rooms and str(rooms).lower() in rooms_map_rev:
        rooms = rooms_map_rev[str(rooms).lower()]

    # URL
    url = item.get("url") or ""
    if url and not url.startswith("http"):
        url = f"https://www.olx.pl{url}"

    # Zdjęcia
    photos = item.get("photos") or item.get("images") or []
    images = []
    for p in photos:
        if isinstance(p, dict):
            img_url = (
                p.get("link")
                or p.get("url")
                or (p.get("thumbnail") or {}).get("url")
            )
            if img_url:
                # OLX zwraca template {width}x{height} — podmień na duże zdjęcie
                img_url = img_url.replace("{width}", "800").replace("{height}", "600")
                images.append(img_url)
        elif isinstance(p, str) and p.startswith("http"):
            images.append(p)

    # Dzielnica z lokalizacji
    location = item.get("location") or {}
    district = None  # zamiast district = "Warszawa"
    city_label = location.get("cityName") or location.get("city", {})
    if isinstance(city_label, dict):
        city_label = city_label.get("name", "")
    district_obj = location.get("district") or {}
    if isinstance(district_obj, dict):
        district = district_obj.get("name") or district
    elif isinstance(district_obj, str) and district_obj:
        district = district_obj
    # Oferta bezpośrednia
    advertiser = item.get("advertiserType") or item.get("advertType") or ""
    direct_offer = str(advertiser).lower() in ("private", "owner", "prywatne")

    # Floor z parametrów
    floor_raw = _get_param(params, "floor_select") or _get_param(params, "floor")
    floor = None
    if floor_raw:
        floor_str = str(floor_raw).lower().replace("floor_", "").replace("parter", "0")
        try:
            floor = int(floor_str)
        except (ValueError, TypeError):
            pass

    psm = round(price / area, 2) if area else None

    listing = {
        "portal": "olx",
        "title": (item.get("title") or "")[:200],
        "price": price,
        "area": area,
        "rooms": str(rooms) if rooms else None,
        "district": district,
        "price_per_m2": psm,
        "url": url,
        "direct_offer": direct_offer,
    }

    if not validate_listing(listing):
        return None

    return {
        **listing,
        "description": item.get("description") or "",
        "images": images[:8],
        "floor": floor,
        "total_floors": None,
        "year_built": None,
        "condition": None,
        "building_type": None,
        "heating": None,
        "ownership": None,
        "raw_location": location,
        "features": {},
        "source": "olx",
    }


# ---------------------------------------------------------------------------
# Public search function
# ---------------------------------------------------------------------------

def search(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=3,
    direct_only=False, district=None,
    **kwargs,
) -> list[dict]:
    all_listings = []

    for page in range(1, pages + 1):
        url = build_olx_url(
            min_price=min_price, max_price=max_price,
            min_area=min_area, max_area=max_area,
            rooms=rooms, direct_only=direct_only,
            page=page, district=district,
        )
        logger.info("[OLX] Strona %d: %s", page, url)

        html = fetch_html(url, portal="olx")
        if not html:
            logger.warning("[OLX] Pusta odpowiedź na stronie %d", page)
            break

        payload = _extract_next_data(html)
        if not payload:
            logger.warning("[OLX] Brak __NEXT_DATA__ na stronie %d", page)
            break

        items = _find_listings_in_payload(payload)
        if not items:
            logger.info("[OLX] Brak ofert na stronie %d — koniec paginacji", page)
            break

        normalized = []
        for item in items:
            listing = _normalize_olx_listing(item)
            if listing:
                normalized.append(listing)

        logger.info("[OLX] Strona %d: %d/%d ofert", page, len(normalized), len(items))
        all_listings.extend(normalized)

    return apply_filters(
        all_listings,
        min_price=min_price, max_price=max_price,
        min_area=min_area, max_area=max_area,
        rooms=rooms, direct_only=direct_only,
    )
