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

OLX_BASE_URL = "https://www.olx.pl/nieruchomosci/mieszkania/warszawa"


def available():
    return "olx"


def build_olx_url(
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
        params["search[filter_float_price:from]"] = str(min_price)
    if max_price is not None:
        params["search[filter_float_price:to]"] = str(max_price)
    if min_area is not None:
        params["search[filter_float_m:from]"] = str(min_area)
    if max_area is not None:
        params["search[filter_float_m:to]"] = str(max_area)
    if rooms:
        rooms_normalized = normalize_rooms_value(rooms)
        if rooms_normalized:
            params["search[filter_enum_rooms][0]"] = rooms_normalized
    if direct_only:
        params["search[filter_enum_advertiser_type][0]"] = "private"
    if page and page > 1:
        params["page"] = str(page)

    if not params:
        return OLX_BASE_URL

    return f"{OLX_BASE_URL}?{build_query_string(params)}"


def normalize_rooms_value(rooms):
    if not rooms:
        return None
    if isinstance(rooms, int):
        rooms = str(rooms)
    if rooms == "1":
        return "one"
    elif rooms == "2":
        return "two"
    elif rooms == "3":
        return "three"
    elif rooms == "4":
        return "four"
    elif rooms == "5":
        return "five"
    elif rooms == "6":
        return "six"
    elif rooms == "7":
        return "seven"
    elif rooms == "8":
        return "eight"
    elif rooms == "9":
        return "nine"
    elif rooms == "10":
        return "ten"
    return None


def extract_listings_from_html(html):
    soup = BeautifulSoup(html, "lxml")
    listings = []

    # OLX listings are in divs with data-cy="l-card"
    cards = soup.find_all("div", {"data-cy": "l-card"})
    for card in cards:
        try:
            # Title from img alt
            img = card.find("img")
            title = img['alt'] if img and 'alt' in img.attrs else "Bez tytułu"

            # Price
            price_elem = card.find("p", {"data-testid": "ad-price"})
            price_text = price_elem.get_text(strip=True) if price_elem else ""
            price = extract_price(price_text)

            # Location and date
            location_elem = card.find("p", {"data-testid": "location-date"})
            district = "Warszawa"
            if location_elem:
                location_text = location_elem.get_text(strip=True)
                # Extract district from location
                district_match = re.search(r"(.+?),", location_text)
                if district_match:
                    district = district_match.group(1).strip()

            # Extract rooms from title
            rooms = None
            rooms_match = re.search(r"(\d+)\s*pok", title, re.I)
            if rooms_match:
                rooms = int(rooms_match.group(1))

            # Area - not always available in list, set to None
            area = None

            # URL
            link_elem = card.find("a", href=True)
            url = link_elem["href"] if link_elem else ""
            if url.startswith("/"):
                url = f"https://www.olx.pl{url}"

            # Direct offer - check for "Oferta prywatna"
            direct_offer = "oferta prywatna" in card.get_text().lower()

            if price:
                listings.append({
                    "title": title,
                    "price": price,
                    "area": area,
                    "rooms": rooms,
                    "district": district,
                    "url": url,
                    "direct_offer": direct_offer,
                    "source": "olx",
                })
        except Exception as e:
            print(f"Error parsing OLX listing: {e}")
            continue

    return listings


def extract_price(price_text):
    # Remove "zł" and spaces, handle "do negocjacji"
    price_text = price_text.replace("zł", "").replace(" ", "").strip()
    if "doniegocjacji" in price_text.lower() or "dowyceny" in price_text.lower():
        return None
    # Extract number
    match = re.search(r"(\d+(?:,\d+)*)", price_text)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def search(
    min_price=None,
    max_price=None,
    min_area=None,
    max_area=None,
    rooms=None,
    pages=1,
    direct_only=False,
):
    all_listings = []
    for page in range(1, pages + 1):
        url = build_olx_url(
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
            rooms=rooms,
            direct_only=direct_only,
            page=page,
        )
        print(f"Fetching OLX page {page}: {url}")
        html = fetch_html(url)
        if not html:
            break
        listings = extract_listings_from_html(html)
        if not listings:
            break
        all_listings.extend(listings)

    # Apply additional filters if needed
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
