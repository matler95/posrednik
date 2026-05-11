import json
import re
from urllib.parse import quote_plus

from backend.scraper_utils import (
    apply_filters,
    build_query_string,
    fetch_html,
    normalize_rooms_value,
    room_matches,
)

OTODOM_BASE_URL = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/mazowieckie/warszawa/warszawa"


def available():
    return "otodom"


def build_otodom_url(
    min_price=None,
    max_price=None,
    min_area=None,
    max_area=None,
    rooms=None,
    page=1,
):
    params = {}
    if min_price is not None:
        params["search[filter_float_price:from]"] = str(min_price)
    if max_price is not None:
        params["search[filter_float_price:to]"] = str(max_price)
    if min_area is not None:
        params["search[filter_float_area:from]"] = str(min_area)
    if max_area is not None:
        params["search[filter_float_area:to]"] = str(max_area)
    if rooms:
        if isinstance(rooms, str) and "," in rooms:
            params["search[filter_enum_rooms_num]"] = rooms
        elif isinstance(rooms, str) and rooms.isdigit():
            params["search[filter_enum_rooms_num]"] = rooms
        elif isinstance(rooms, int):
            params["search[filter_enum_rooms_num]"] = str(rooms)
    if page and page > 1:
        params["page"] = str(page)

    if not params:
        return OTODOM_BASE_URL

    return f"{OTODOM_BASE_URL}?{build_query_string(params)}"


def extract_json_payload(html):
    patterns = [
        r'__NEXT_DATA__" type="application/json" crossorigin="anonymous">(\{.+?\})</script>',
        r'<script id="__NEXT_DATA__" type="application/json">(\{.+?\})</script>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.S)
        if match:
            return json.loads(match.group(1))

    raise ValueError("Nie można wyodrębnić danych z Otodom. Sprawdź URL lub strukturę strony.")


def extract_district(location):
    if not isinstance(location, dict):
        return "Warszawa"

    reverse = location.get("reverseGeocoding", {}).get("locations", [])
    for node in reverse:
        if node.get("locationLevel") == "district":
            return node.get("name") or node.get("fullName") or "Warszawa"

    address = location.get("address", {})
    city = address.get("city", {}).get("name")
    if city:
        return city

    return "Warszawa"


# backend/scrapers/otodom.py — tylko funkcja normalize_listing, reszta bez zmian

def normalize_listing(item, source_url):
    price_data = item.get("totalPrice") or item.get("priceFromPerSquareMeter") or {}
    price = price_data.get("value") if isinstance(price_data, dict) else None
    area = (
        item.get("areaInSquareMeters")
        or item.get("investmentUnitsAreaInSquareMeters")
        or item.get("terrainAreaInSquareMeters")
    )
    district = extract_district(item.get("location", {}))

    url = item.get("href", "")
    slug = item.get("slug")
    if slug:
        url = f"https://www.otodom.pl/pl/oferta/{slug}"
    elif url.startswith("[lang]"):
        url = url.replace("[lang]", "")
    if url.startswith("/"):
        url = f"https://www.otodom.pl{url}"

    # Wyciągnij zdjęcia
    images_raw = item.get("images", [])
    images = []
    if isinstance(images_raw, list):
        for img in images_raw:
            url_img = img.get("medium") or img.get("large") or img.get("thumbnail")
            if url_img:
                images.append(url_img)

    # Detekcja oferty bezpośredniej
    advert_type = item.get("advertType", "")
    direct_offer = str(advert_type).upper() == "PRIVATE"

    return {
        "portal": "otodom",
        "title": item.get("title") or item.get("shortDescription") or "Bez tytułu",
        "price": int(price) if isinstance(price, (int, float)) else None,
        "area": float(area) if isinstance(area, (int, float)) else None,
        "district": district,
        "rooms": item.get("roomsNumber") or item.get("roomsNumberLabel"),
        "price_per_m2": (
            item.get("pricePerSquareMeter", {}).get("value")
            if isinstance(item.get("pricePerSquareMeter"), dict)
            else None
        ),
        "url": url or source_url,
        "source": source_url,
        "direct_offer": direct_offer,
        "raw_location": item.get("location", {}),
        "description": item.get("shortDescription"),
        "images": images,
    }




def parse_otodom_items(payload, source_url):
    items = (
        payload.get("props", {})
        .get("pageProps", {})
        .get("data", {})
        .get("searchAds", {})
        .get("items", [])
    )
    return [normalize_listing(item, source_url) for item in items if item]


def search(
    query_url=None,
    min_price=None,
    max_price=None,
    min_area=None,
    max_area=None,
    rooms=None,
    pages=1,
    direct_only=False,
):
    listings = []
    if query_url:
        html = fetch_html(query_url)
        payload = extract_json_payload(html)
        listings.extend(parse_otodom_items(payload, query_url))
    else:
        for page in range(1, pages + 1):
            url = build_otodom_url(
                min_price=min_price,
                max_price=max_price,
                min_area=min_area,
                max_area=max_area,
                rooms=rooms,
                page=page,
            )
            html = fetch_html(url)
            payload = extract_json_payload(html)
            page_listings = parse_otodom_items(payload, url)
            if not page_listings:
                break
            listings.extend(page_listings)

    return apply_filters(
        listings,
        min_price=min_price,
        max_price=max_price,
        min_area=min_area,
        max_area=max_area,
        rooms=rooms,
        direct_only=direct_only,
    )
