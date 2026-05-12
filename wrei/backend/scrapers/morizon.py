import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from backend.scraper_utils import (
    apply_filters,
    build_query_string,
    fetch_html,
    normalize_rooms_value,
    room_matches,
)

MORIZON_BASE_URL = "https://www.morizon.pl/mieszkania/warszawa"


def available():
    return "morizon"


def build_morizon_url(
    min_price=None,
    max_price=None,
    min_area=None,
    max_area=None,
    rooms=None,
    direct_only=False,
    page=1,
):
    params = {}
    if min_price is not None:
        params["ps[price_from]"] = str(min_price)
    if max_price is not None:
        params["ps[price_to]"] = str(max_price)
    if min_area is not None:
        params["ps[living_area_from]"] = str(min_area)
    if max_area is not None:
        params["ps[living_area_to]"] = str(max_area)
    if rooms:
        rooms_normalized = normalize_rooms_value(rooms)
        if rooms_normalized:
            params["ps[rooms_number][]"] = str(rooms_normalized)
    # Morizon doesn't have direct filter, assume all are direct or skip
    if page and page > 1:
        params["page"] = str(page)

    if not params:
        return MORIZON_BASE_URL

    return f"{MORIZON_BASE_URL}?{build_query_string(params)}"


def extract_listings_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    listings = []

    # Morizon listings are often in <section> or <article> with specific classes
    properties = soup.find_all(["section", "article"], class_=re.compile(r"Box"))
    if not properties:
        # Fallback to older search
        properties = soup.select("div[class*='property']")

    for prop in properties:
        try:
            # Title
            title_elem = prop.find(["h2", "h3"])
            title = title_elem.get_text(strip=True) if title_elem else "Bez tytułu"

            # Price
            price_elem = prop.find("p", class_=re.compile(r"Price")) or prop.find("span", class_="price")
            price_text = price_elem.get_text(strip=True) if price_elem else ""
            price = extract_price(price_text)

            # Area
            area_text = prop.get_text(" ", strip=True)
            area = None
            area_match = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", area_text)
            if area_match:
                area = float(area_match.group(1).replace(",", "."))

            # URL
            link_elem = prop.find("a", href=True)
            url = link_elem["href"] if link_elem else ""
            if url.startswith("/"):
                url = f"https://www.morizon.pl{url}"

            if price:
                listings.append({
                    "title": title,
                    "price": price,
                    "area": area,
                    "district": "Warszawa", # Fallback
                    "url": url,
                    "source": "morizon",
                    "portal": "morizon",
                })
        except Exception as e:
            continue

    return listings



def extract_price(price_text):
    price_text = price_text.replace("zł", "").replace(" ", "").strip()
    if "do negocjacji" in price_text.lower() or "cena do ustalenia" in price_text.lower():
        return None
    match = re.search(r"(\d+(?:,\d+)*)", price_text)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def search(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=1, direct_only=False,
    district=None, **kwargs
):

    all_listings = []
    for page in range(1, pages + 1):
        url = build_morizon_url(
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
            rooms=rooms,
            direct_only=direct_only,
            page=page,
        )
        print(f"Fetching Morizon page {page}: {url}")
        html = fetch_html(url)
        if not html:
            break
        listings = extract_listings_from_html(html)
        if not listings:
            break
        all_listings.extend(listings)

    filtered = apply_filters(
        all_listings,
        min_price=min_price,
        max_price=max_price,
        min_area=min_area,
        max_area=max_area,
        rooms=rooms,
        direct_only=direct_only,
    )
    return filtered
