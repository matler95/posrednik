"""
Otodom scraper — robust extraction z wieloma fallback ścieżkami.
Naprawiony: price, area, images, district, url extraction.
"""
import json
import re
import logging

from backend.scraper_utils import (
    apply_filters,
    fetch_html,
    extract_price,
    extract_area_from_text,
    validate_listing,
)

logger = logging.getLogger(__name__)

OTODOM_BASE = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/mazowieckie/warszawa/warszawa"


def available():
    return "otodom"


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------

def build_otodom_url(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, page=1,
    direct_only=False, district=None,
) -> str:
    query = []
    if max_price:
        query.append(f"priceMax={int(max_price)}")
    if min_price:
        query.append(f"priceMin={int(min_price)}")
    if max_area:
        query.append(f"areaMax={int(max_area)}")
    if min_area:
        query.append(f"areaMin={int(min_area)}")
    if rooms:
        # Obsługa listy lub pojedynczej wartości
        room_list = rooms if isinstance(rooms, list) else [rooms]
        for r in room_list:
            query.append(f"roomsNumber={r}")
    if direct_only:
        query.append("ownerTypeSingleSelect=PRIVATE")
    else:
        query.append("ownerTypeSingleSelect=ALL")
    query.append("viewType=listing")
    if page > 1:
        query.append(f"page={page}")

    return f"{OTODOM_BASE}?{'&'.join(query)}"


# ---------------------------------------------------------------------------
# JSON payload extraction
# ---------------------------------------------------------------------------

def extract_json_payload(html: str) -> dict:
    """Wyciąga __NEXT_DATA__ z HTML strony Otodom."""
    patterns = [
        r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(\{.+?\})</script>',
        r'<script id="__NEXT_DATA__"[^>]*>(\{.+?\})</script>',
        r'"__NEXT_DATA__"[^=]*=\s*(\{.+?\});?\s*</script>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    logger.warning("[Otodom] Nie znaleziono __NEXT_DATA__ w HTML (len=%d)", len(html))
    return {}


# ---------------------------------------------------------------------------
# Field extractors — wielokrotne fallback ścieżki
# ---------------------------------------------------------------------------

def _extract_price(item: dict) -> int | None:
    """Wyciąga cenę z różnych możliwych ścieżek w JSON Otodom."""
    candidates = [
        # Nowa struktura
        item.get("totalPrice", {}),
        item.get("price", {}),
        # Płaskie wartości
        {"value": item.get("totalPrice")} if not isinstance(item.get("totalPrice"), dict) else None,
        {"value": item.get("price")} if not isinstance(item.get("price"), dict) else None,
    ]
    for c in candidates:
        if not c:
            continue
        if isinstance(c, dict):
            val = c.get("value") or c.get("amount") or c.get("regularPrice")
        else:
            val = c
        if val:
            try:
                price = int(float(str(val).replace(" ", "").replace(",", ".")))
                if 10_000 < price < 50_000_000:
                    return price
            except (ValueError, TypeError):
                continue

    # Ostatni fallback: szukaj w tytule/opisie
    text = (item.get("title") or "") + " " + (item.get("shortDescription") or "")
    price_match = re.search(r"([\d\s]{5,})\s*(?:zł|PLN)", text)
    if price_match:
        val = extract_price(price_match.group(1))
        if val and 10_000 < val < 50_000_000:
            return val
    return None


def _extract_area(item: dict) -> float | None:
    """Wyciąga metraż z różnych możliwych ścieżek."""
    candidates = [
        item.get("areaInSquareMeters"),
        item.get("area", {}).get("value") if isinstance(item.get("area"), dict) else item.get("area"),
        item.get("terrainAreaInSquareMeters"),
        item.get("usableArea"),
    ]
    for val in candidates:
        if val is not None:
            try:
                area = float(str(val).replace(",", "."))
                if 5.0 < area < 2000.0:
                    return area
            except (ValueError, TypeError):
                continue

    # Fallback: szukaj w tytule
    text = (item.get("title") or "") + " " + (item.get("shortDescription") or "")
    return extract_area_from_text(text)


def _extract_rooms(item: dict) -> str | None:
    """Wyciąga liczbę pokoi."""
    for key in ("roomsNumber", "rooms_number", "numberOfRooms"):
        val = item.get(key)
        if val is not None:
            # Może być string "THREE" lub liczba 3
            if isinstance(val, str):
                mapping = {
                    "ONE": "1", "TWO": "2", "THREE": "3",
                    "FOUR": "4", "FIVE": "5", "SIX": "6",
                }
                return mapping.get(val.upper(), val)
            return str(val)
    return None


def _extract_district(item: dict) -> str:
    """Wyciąga dzielnicę z obiektu lokalizacji."""
    location = item.get("location") or {}

    # Ścieżka 1: reverseGeocoding
    reverse = location.get("reverseGeocoding", {}).get("locations", [])
    for node in reverse:
        level = node.get("locationLevel", "")
        if level in ("district", "subregion"):
            name = node.get("name") or node.get("fullName")
            if name:
                return name

    # Ścieżka 2: adres strukturalny
    address = location.get("address", {})
    for key in ("district", "sublocality", "neighborhood"):
        val = address.get(key, {})
        if isinstance(val, dict):
            val = val.get("name")
        if val and val.lower() not in ("warszawa", "warsaw", "mazowieckie"):
            return val

    # Ścieżka 3: mapDetails
    map_det = location.get("mapDetails", {})
    district = map_det.get("district") or map_det.get("quarter")
    if district:
        return district

    return "Warszawa"


def _extract_url(item: dict) -> str:
    """Wyciąga pełny URL ogłoszenia."""
    # Ścieżka 1: slug
    slug = item.get("slug")
    if slug:
        return f"https://www.otodom.pl/pl/oferta/{slug}"

    # Ścieżka 2: href
    href = item.get("href") or item.get("url") or item.get("relativeUrl") or ""
    if href:
        if href.startswith("[lang]"):
            href = href.replace("[lang]", "")
        if href.startswith("/"):
            return f"https://www.otodom.pl{href}"
        if href.startswith("http"):
            return href

    return ""


def _extract_images(item: dict) -> list[str]:
    """Wyciąga URL-e zdjęć."""
    images_raw = item.get("images") or item.get("photos") or []
    urls = []
    if isinstance(images_raw, list):
        for img in images_raw:
            if isinstance(img, dict):
                url = (
                    img.get("large")
                    or img.get("medium")
                    or img.get("thumbnail")
                    or img.get("url")
                    or img.get("src")
                )
                if url:
                    urls.append(url)
            elif isinstance(img, str) and img.startswith("http"):
                urls.append(img)
    return urls[:8]


def _extract_floor(item: dict) -> tuple[int | None, int | None]:
    """Wyciąga numer piętra i liczbę pięter."""
    floor = None
    total = None

    # Ścieżka strukturalna
    for key in ("floor", "floorNumber", "floor_no"):
        val = item.get(key)
        if val is not None:
            try:
                floor = int(str(val).split("/")[0].replace("parter", "0"))
            except (ValueError, TypeError):
                pass
            break

    for key in ("totalFloors", "total_floors", "numberOfFloors"):
        val = item.get(key)
        if val is not None:
            try:
                total = int(val)
            except (ValueError, TypeError):
                pass
            break

    # Ścieżka w floorObject
    floor_obj = item.get("floorObject") or {}
    if isinstance(floor_obj, dict):
        if floor is None and floor_obj.get("floor") is not None:
            try:
                floor = int(floor_obj["floor"])
            except (ValueError, TypeError):
                pass
        if total is None and floor_obj.get("numberOfFloors") is not None:
            try:
                total = int(floor_obj["numberOfFloors"])
            except (ValueError, TypeError):
                pass

    return floor, total


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------

def normalize_listing(item: dict, source_url: str) -> dict | None:
    """Normalizuje pojedynczy rekord z Otodom JSON do ustandaryzowanego słownika."""
    price = _extract_price(item)
    area = _extract_area(item)

    url = _extract_url(item)
    
    listing = {
        "portal": "otodom",
        "title": (item.get("title") or item.get("shortDescription") or "")[:200],
        "price": price,
        "area": area,
        "district": _extract_district(item),
        "rooms": _extract_rooms(item),
        "price_per_m2": None, # Obliczy validate_listing lub my niżej
        "url": url,
    }

    # Wstępna walidacja przed budowaniem reszty obiektu
    if not validate_listing(listing):
        return None

    floor, total_floors = _extract_floor(item)

    # Condition / stan
    cond_raw = (
        item.get("condition")
        or item.get("propertyCondition")
        or ""
    )
    if isinstance(cond_raw, dict):
        cond_raw = cond_raw.get("value", "")
    condition_map = {
        "NEW": "nowy", "NEW_BUILDING": "nowy",
        "GOOD": "dobry", "VERY_GOOD": "dobry",
        "TO_RENOVATE": "remont", "FOR_RENOVATION": "remont",
        "MEDIUM": "sredni",
    }
    condition = condition_map.get(str(cond_raw).upper(), None)

    # Building type
    bt_raw = item.get("buildingType") or item.get("building_type") or ""
    if isinstance(bt_raw, dict):
        bt_raw = bt_raw.get("value", "")
    bt_map = {
        "BLOCK": "blok", "APARTMENT": "apartament",
        "TENEMENT": "kamienica", "HOUSE": "dom",
        "SEMI_DETACHED": "szeregowiec", "RIBBON": "szeregowiec",
    }
    building_type = bt_map.get(str(bt_raw).upper(), None)

    psm = item.get("pricePerSquareMeter", {})
    if isinstance(psm, dict):
        psm = psm.get("value")
    if not psm and area:
        psm = round(price / area, 2)

    return {
        "portal": "otodom",
        "title": (item.get("title") or item.get("shortDescription") or "")[:200],
        "price": price,
        "area": area,
        "district": _extract_district(item),
        "rooms": _extract_rooms(item),
        "price_per_m2": float(psm) if psm else None,
        "url": url,
        "source": source_url,
        "direct_offer": bool(item.get("isPrivateOwner") or item.get("advertType", "") == "PRIVATE"),
        "description": item.get("description") or item.get("shortDescription") or "",
        "images": _extract_images(item),
        "floor": floor,
        "total_floors": total_floors,
        "year_built": item.get("yearBuilt") or item.get("year_built"),
        "condition": condition,
        "building_type": building_type,
        "heating": item.get("heating") or item.get("heatingType"),
        "ownership": item.get("ownership") or item.get("propertyOwnership"),
        "raw_location": item.get("location") or {},
        "features": {},
    }


# ---------------------------------------------------------------------------
# Parser items list
# ---------------------------------------------------------------------------

def parse_otodom_items(payload: dict, source_url: str) -> list[dict]:
    """Wyciąga listę ofert z payload __NEXT_DATA__."""
    # Próba różnych ścieżek w JSON
    paths = [
        lambda p: p.get("props", {}).get("pageProps", {}).get("data", {}).get("searchAds", {}).get("items", []),
        lambda p: p.get("props", {}).get("pageProps", {}).get("listing", {}).get("listing", {}).get("ads", []),
        lambda p: p.get("props", {}).get("pageProps", {}).get("data", {}).get("searchAds", {}).get("promotedItems", []),
    ]

    items = []
    for path_fn in paths:
        try:
            result = path_fn(payload)
            if result and isinstance(result, list):
                items = result
                break
        except (AttributeError, TypeError):
            continue

    if not items:
        logger.warning("[Otodom] Brak items w payload dla %s", source_url)
        return []

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        listing = normalize_listing(item, source_url)
        if listing:
            normalized.append(listing)

    logger.info("[Otodom] %s → %d/%d ofert znormalizowanych", source_url, len(normalized), len(items))
    return normalized


# ---------------------------------------------------------------------------
# Public search function
# ---------------------------------------------------------------------------

def search(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=3,
    direct_only=False, district=None,
    query_url=None,
    **kwargs,
) -> list[dict]:
    all_listings = []

    if query_url:
        urls_to_fetch = [query_url]
    else:
        urls_to_fetch = [
            build_otodom_url(
                min_price=min_price, max_price=max_price,
                min_area=min_area, max_area=max_area,
                rooms=rooms, page=p,
                direct_only=direct_only, district=district,
            )
            for p in range(1, pages + 1)
        ]

    for url in urls_to_fetch:
        logger.info("[Otodom] Pobieranie: %s", url)
        html = fetch_html(url, portal="otodom")
        if not html:
            logger.warning("[Otodom] Pusta odpowiedź dla %s", url)
            break

        payload = extract_json_payload(html)
        if not payload:
            logger.warning("[Otodom] Brak payload dla %s", url)
            break

        page_listings = parse_otodom_items(payload, url)
        if not page_listings:
            logger.info("[Otodom] Brak ofert — koniec paginacji")
            break

        all_listings.extend(page_listings)

    return apply_filters(
        all_listings,
        min_price=min_price, max_price=max_price,
        min_area=min_area, max_area=max_area,
        rooms=rooms, direct_only=direct_only,
    )
