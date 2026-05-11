import json
import re
from urllib.parse import quote_plus

from backend.scraper_utils import (
    apply_filters,
    build_query_string,
    fetch_html,
    normalize_rooms_value,
    room_matches,
    extract_price,
    extract_area_from_text
)


OTODOM_BASE_URL = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie"


def available():
    return "otodom"


def build_otodom_url(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, page=1,
    direct_only=False, district=None
) -> str:
    
    base = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/mazowieckie/warszawa/warszawa"
    query = []
    if max_price: query.append(f"priceMax={max_price}")
    if min_price: query.append(f"priceMin={min_price}")
    if max_area: query.append(f"areaMax={max_area}")
    if min_area: query.append(f"areaMin={min_area}")
    if page > 1: query.append(f"page={page}")
    
    # KLUCZ: Jeśli mamy dzielnicę, szukamy jej w wynikach (lub po prostu skanujemy więcej stron)
    # Dodajemy ownerType, aby odświeżyć wyniki
    query.append("ownerTypeSingleSelect=ALL")
    query.append("viewType=listing")
    
    url = f"{base}?{'&'.join(query)}"
    return url




def extract_json_payload(html):
    patterns = [
        r'__NEXT_DATA__" type="application/json" crossorigin="anonymous">(\{.+?\})</script>',
        r'<script id="__NEXT_DATA__" type="application/json">(\{.+?\})</script>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                continue

    print(f"[ERR] Otodom: Payload extraction failed. HTML length: {len(html)}")
    return {}



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
    direct_offer = item.get("isPrivateOwner", False)


    # Ekstremalnie tolerancyjne wyciąganie ceny
    price = None
    price_obj = item.get("totalPrice") or item.get("price") or {}
    if isinstance(price_obj, dict):
        price = price_obj.get("value")
    elif isinstance(price_obj, (int, float)):
        price = price_obj

    # Jeśli wciąż brak ceny (częste w przetargach), szukaj w innych polach
    if not price:
        # Przetargi często mają cenę w shortDescription lub tytule
        price_match = re.search(r"([\d\s]{5,})\s*zł", item.get("title", "") + " " + (item.get("shortDescription") or ""))
        if price_match:
            price = extract_price(price_match.group(1))

    area = item.get("area", {}).get("value") if isinstance(item.get("area"), dict) else item.get("area")
    
    # Obsługa Przetargów - jeśli brak metrażu w polu area, szukaj w tytule
    if not area:
        area = extract_area_from_text(item.get("title", "") + " " + (item.get("shortDescription") or ""))

    # URL
    url = item.get("url") or item.get("relativeUrl") or ""
    if url.startswith("/"): url = f"https://www.otodom.pl{url}"




    return {
        "portal": "otodom",
        "title": item.get("title") or item.get("shortDescription") or "Bez tytułu",
        "price": int(price) if price else None,
        "area": float(area) if area else None,
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
    }

def parse_otodom_items(payload, source_url):

    items = (

        payload.get("props", {})
        .get("pageProps", {})
        .get("data", {})
        .get("searchAds", {})
        .get("items", [])
    )
    # Filtrujemy tylko rzeczywiste oferty z ceną i metrażem
    valid_items = []
    for it in items:
        if it and it.get("totalPrice") and it.get("area"):
             norm = normalize_listing(it, source_url)
             if norm.get("price") and norm.get("area"):
                 valid_items.append(norm)
    return valid_items



def search(
    query_url=None,
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=1, direct_only=False,
    district=None
):
    listings = []
    if query_url:
        html = fetch_html(query_url)
        payload = extract_json_payload(html)
        listings.extend(parse_otodom_items(payload, query_url))
    else:
        # Skanujemy strony
        for page in range(1, pages + 1):
            url = build_otodom_url(
                min_price=min_price, max_price=max_price,
                min_area=min_area, max_area=max_area,
                rooms=rooms, page=page,
                direct_only=direct_only, district=district
            )
            print(f"[OTODOM] Pobieram stronę {page} dla {district or 'Warszawa'}: {url}")
            html = fetch_html(url, portal="otodom")
            if not html: 
                print(f"[ERR] Otodom: Pusta odpowiedź na stronie {page}")
                break
            payload = extract_json_payload(html)
            page_listings = parse_otodom_items(payload, url)
            if not page_listings:
                print(f"[INFO] Otodom: Brak ofert na stronie {page}")
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
