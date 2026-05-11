# backend/scrapers/olx.py

import re
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from backend.scraper_utils import apply_filters, build_query_string, fetch_html

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
    soup = BeautifulSoup(html, "lxml")
    listings = []

    cards = soup.find_all("div", {"data-cy": "l-card"})
    for card in cards:
        try:
            # Tytuł
            title_elem = card.find("h4") or card.find("h3")
            title = title_elem.get_text(strip=True) if title_elem else ""
            if not title:
                img = card.find("img")
                title = img["alt"] if img and "alt" in img.attrs else "Bez tytułu"

            # Cena
            price_elem = card.find("p", {"data-testid": "ad-price"})
            price_text = price_elem.get_text(strip=True) if price_elem else ""
            price = extract_price(price_text)

            # Metraż — z tytułu
            area = extract_area_from_text(title)

            # Jeśli nie w tytule — szukaj w parametrach karty
            if area is None:
                params_text = card.get_text(" ", strip=True)
                area = extract_area_from_text(params_text)

            # Dzielnica
            location_elem = card.find("p", {"data-testid": "location-date"})
            district = "Warszawa"
            if location_elem:
                location_text = location_elem.get_text(strip=True)
                district_match = re.match(r"^([^,\-–]+)", location_text)
                if district_match:
                    district = district_match.group(1).strip()

            # Pokoje z tytułu
            rooms = None
            rooms_match = re.search(r"(\d+)\s*pok", title, re.IGNORECASE)
            if rooms_match:
                rooms = int(rooms_match.group(1))

            # URL
            link_elem = card.find("a", href=True)
            url = link_elem["href"] if link_elem else ""
            if url.startswith("/"):
                url = f"https://www.olx.pl{url}"

            # Oferta bezpośrednia
            card_text = card.get_text().lower()
            direct_offer = "oferta prywatna" in card_text

            if price:
                listings.append({
                    "portal": "olx",        # BUG FIX — brakowało
                    "title": title,
                    "price": price,
                    "area": area,           # BUG FIX — teraz wyciągamy
                    "rooms": rooms,
                    "district": district,
                    "url": url,
                    "direct_offer": direct_offer,
                    "source": "olx",
                })
        except Exception as e:
            print(f"[OLX] Błąd parsowania karty: {e}")
            continue

    return listings


def build_olx_url(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, direct_only=False, page=1,
) -> str:
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
    **kwargs,  # query_url ignorowany dla OLX
) -> list[dict]:
    all_listings = []
    for page in range(1, pages + 1):
        url = build_olx_url(
            min_price=min_price, max_price=max_price,
            min_area=min_area, max_area=max_area,
            rooms=rooms, direct_only=direct_only, page=page,
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
