# backend/scrapers/olx.py

import re
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from backend.scraper_utils import (
    apply_filters, 
    build_query_string, 
    fetch_html,
    extract_price,
    extract_area_from_text
)


OLX_BASE_URL = "https://www.olx.pl/nieruchomosci/mieszkania/warszawa"


def available():
    return "olx"


def normalize_rooms_value(rooms):
    if not rooms:
        return None
    if isinstance(rooms, int):
        rooms = str(rooms)
    mapping = {"1": "one", "2": "two", "3": "three", "4": "four",
               "5": "five", "6": "six", "7": "seven", "8": "eight",
               "9": "nine", "10": "ten"}
    return mapping.get(rooms)


def extract_area_from_text(text: str) -> float | None:
    """Wyciąga metraż z tytułu lub opisu, np. '55m²', '55 m2', '55,5 m²'"""
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", text, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def extract_price(price_text: str) -> int | None:
    price_text = price_text.replace("zł", "").replace("\xa0", "").replace(" ", "").strip()
    if any(x in price_text.lower() for x in ["doniegocjacji", "dowyceny", "zapytaj"]):
        return None
    match = re.search(r"(\d+(?:\s?\d+)*)", price_text.replace(" ", ""))
    if match:
        return int(re.sub(r"\D", "", match.group(1)))
    return None


def extract_listings_from_html(html: str) -> list[dict]:
    listings = []
    
    # Metoda 1: Szukanie JSONa (najdokładniejsza)
    import json
    try:
        match = re.search(r'window\.__PRERENDERED_STATE__\s*=\s*"(.*?)";', html)
        if match:
            raw_data = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
            data = json.loads(raw_data)
            # Ścieżka do ofert w JSON OLX:
            items = data.get("adview", {}).get("ads", []) or data.get("listing", {}).get("listing", {}).get("ads", [])
            for item in items:
                try:
                    price = extract_price(str(item.get("price", {}).get("value", 0)))
                    if not price: continue
                    listings.append({
                        "portal": "olx",
                        "title": item.get("title", "Mieszkanie"),
                        "price": price,
                        "area": extract_area_from_text(item.get("title", "")),
                        "district": "Warszawa",
                        "url": item.get("url", ""),
                        "source": "olx"
                    })
                except: continue
            if listings: return listings
    except: pass

    # Metoda 2: Agresywny Regex (jeśli JSON zawiedzie)
    # Szukamy linków do ofert: /d/oferta/...
    links = re.findall(r'href="(https://www.olx.pl/d/oferta/[^"]+)"', html)
    for url in set(links):
        listings.append({
            "portal": "olx",
            "title": "Mieszkanie OLX",
            "price": 0, # Zostanie uzupełnione przez AI z opisu jeśli trzeba
            "area": 0,
            "district": "Warszawa",
            "url": url,
            "source": "olx"
        })
    
    return listings





def build_olx_url(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, direct_only=False, page=1,
    district=None
) -> str:
    # Slugify district
    dist_slug = district.lower().replace("ł", "l").replace("ó", "o").replace("ś", "s").replace("ź", "z").replace("ż", "z").replace("ć", "c").replace("ń", "n").replace(" ", "-") if district else None
    
    base = "https://www.olx.pl/nieruchomosci/mieszkania/warszawa"
    if dist_slug:
        base = f"https://www.olx.pl/nieruchomosci/mieszkania/warszawa/{dist_slug}/"
    
    params = {}
    if min_price is not None: params["search[filter_float_price:from]"] = str(min_price)
    if max_price is not None: params["search[filter_float_price:to]"] = str(max_price)
    if min_area is not None: params["search[filter_float_m:from]"] = str(min_area)
    if max_area is not None: params["search[filter_float_m:to]"] = str(max_area)

    if rooms:
        normalized = normalize_rooms_value(str(rooms))
        if normalized:
            params["search[filter_enum_rooms][0]"] = normalized
    if direct_only:
        params["search[filter_enum_advertiser_type][0]"] = "private"
    if page > 1:
        params["page"] = str(page)

    if not params:
        return OLX_BASE_URL
    return f"{OLX_BASE_URL}?{build_query_string(params)}"


def search(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=1, direct_only=False,
    district=None,
    **kwargs,  # query_url ignorowany dla OLX
) -> list[dict]:
    all_listings = []
    for page in range(1, pages + 1):
        url = build_olx_url(
            min_price=min_price, max_price=max_price,
            min_area=min_area, max_area=max_area,
            rooms=rooms, direct_only=direct_only, page=page,
            district=district
        )

        print(f"[OLX] Strona {page}: {url}")
        html = fetch_html(url)
        if not html:
            break
        page_listings = extract_listings_from_html(html)
        if not page_listings:
            break
            
        # Zapisujemy wszystko co pobralismy, nie filtrujemy agresywnie na tym etapie
        all_listings.extend(page_listings)

    return apply_filters(
        all_listings,
        min_price=min_price, max_price=max_price,
        min_area=min_area, max_area=max_area,
        rooms=rooms, direct_only=direct_only,
    )
