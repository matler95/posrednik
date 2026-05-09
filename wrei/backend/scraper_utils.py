import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def build_query_string(params):
    return "&".join(
        f"{quote_plus(key, safe='')}={quote_plus(value, safe='')}" for key, value in params.items()
    )


def fetch_html(url):
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.text


def normalize_rooms_value(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        mapping = {
            "ONE": 1,
            "TWO": 2,
            "THREE": 3,
            "FOUR": 4,
            "FIVE": 5,
            "SIX": 6,
        }
        if value.isdigit():
            return int(value)
        return mapping.get(value.upper())
    return None


def room_matches(query, listing_rooms):
    if query is None or query == "":
        return True
    normalized = normalize_rooms_value(listing_rooms)
    if normalized is None:
        return False
    query = str(query).strip()
    if "," in query:
        choices = [int(part) for part in query.split(",") if part.strip().isdigit()]
        return normalized in choices
    if "-" in query:
        parts = [part.strip() for part in query.split("-")]
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]) <= normalized <= int(parts[1])
    if query.isdigit():
        return normalized == int(query)
    return False


def apply_filters(listings, min_price=None, max_price=None, min_area=None, max_area=None, rooms=None, direct_only=False):
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


def deduplicate_listings(listings):
    seen = set()
    unique = []
    for listing in listings:
        url = listing.get("url")
        key = url or listing.get("title")
        if key in seen:
            continue
        seen.add(key)
        unique.append(listing)
    return unique
