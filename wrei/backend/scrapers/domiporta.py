import json
import re
from backend.scraper_utils import apply_filters, fetch_html

DOMIPORTA_BASE_URL = "https://www.domiporta.pl/mieszkanie/sprzedam/mazowieckie/warszawa"


def available():
    return "domiporta"


def build_domiporta_url(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, page=1,
) -> str:
    url = DOMIPORTA_BASE_URL
    params = []
    if min_price:
        params.append(f"cenaOd={min_price}")
    if max_price:
        params.append(f"cenaDo={max_price}")
    if min_area:
        params.append(f"powierzchniaOd={min_area}")
    if max_area:
        params.append(f"powierzchniaDo={max_area}")
    if rooms:
        rooms_str = str(rooms).split("-")[0].split(",")[0].strip()
        if rooms_str.isdigit():
            params.append(f"liczbaPokoi={rooms_str}")
    if page > 1:
        params.append(f"PageIndex={page}")
    return f"{url}?{'&'.join(params)}" if params else url


def extract_json_payload(html: str) -> dict:
    patterns = [
        r'<script id="__NEXT_DATA__"[^>]*>(\{.+?\})</script>',
        r'__NEXT_DATA__[^=]*=\s*(\{.+?\});',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return {}


def normalize_listing(item: dict) -> dict | None:
    """
    Domiporta __NEXT_DATA__ — klucze zweryfikować po pierwszym uruchomieniu.
    Typowe pola: Price, Area, RoomsNumber, Location, Title, Url, IsPrivate
    """
    try:
        price = item.get("Price") or item.get("price") or item.get("totalPrice")
        if isinstance(price, dict):
            price = price.get("value") or price.get("Value")
        price = int(float(price)) if price else None

        area = item.get("Area") or item.get("area") or item.get("surfaceArea")
        area = float(area) if area else None

        rooms = item.get("RoomsNumber") or item.get("roomsNumber") or item.get("rooms")

        # Lokalizacja
        location = item.get("Location") or item.get("location") or {}
        district = "Warszawa"
        if isinstance(location, dict):
            district = (
                location.get("DistrictName")
                or location.get("districtName")
                or location.get("district")
                or location.get("CityName")
                or "Warszawa"
            )

        # URL
        url = item.get("Url") or item.get("url") or item.get("detailsUrl") or ""
        if url and not url.startswith("http"):
            url = f"https://www.domiporta.pl{url}"

        title = item.get("Title") or item.get("title") or item.get("Name") or "Bez tytułu"

        # Bezpośredni
        direct_offer = bool(
            item.get("IsPrivate")
            or item.get("isPrivate")
            or item.get("advertType", "").upper() == "PRIVATE"
        )

        # Zdjęcia
        photos = item.get("Photos") or item.get("photos") or item.get("images") or []
        images = []
        for p in photos[:5]:
            if isinstance(p, dict):
                img_url = p.get("Url") or p.get("url") or p.get("src") or ""
                if img_url:
                    images.append(img_url)
            elif isinstance(p, str):
                images.append(p)

        price_per_m2 = item.get("PricePerMeter") or item.get("pricePerMeter")
        price_per_m2 = float(price_per_m2) if price_per_m2 else None

        if not price:
            return None

        return {
            "portal": "domiporta",
            "title": title,
            "price": price,
            "area": area,
            "rooms": rooms,
            "district": district,
            "url": url,
            "direct_offer": direct_offer,
            "price_per_m2": price_per_m2,
            "source": "domiporta",
            "images": images,
            "raw_location": location,
        }
    except Exception as e:
        print(f"[Domiporta] Błąd normalizacji: {e}")
        return None


def parse_items(payload: dict) -> list[dict]:
    """
    Próbuje wyciągnąć listę ogłoszeń z __NEXT_DATA__ Domiporta.
    Ścieżka może wymagać korekty — loguj payload[:500] jeśli brak wyników.
    """
    # Próba kilku typowych ścieżek
    candidates = [
        payload.get("props", {}).get("pageProps", {}).get("listings", []),
        payload.get("props", {}).get("pageProps", {}).get("offers", []),
        payload.get("props", {}).get("pageProps", {}).get("data", {}).get("items", []),
        payload.get("props", {}).get("pageProps", {}).get("initialData", {}).get("items", []),
        payload.get("props", {}).get("pageProps", {}).get("searchResults", {}).get("items", []),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    # Debug pomocniczy
    page_props = payload.get("props", {}).get("pageProps", {})
    print(f"[Domiporta] Dostępne klucze pageProps: {list(page_props.keys())}")
    return []


def search(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=1, direct_only=False,
    **kwargs,
) -> list[dict]:
    all_listings = []
    for page in range(1, pages + 1):
        url = build_domiporta_url(
            min_price=min_price, max_price=max_price,
            min_area=min_area, max_area=max_area,
            rooms=rooms, page=page,
        )
        print(f"[Domiporta] Strona {page}: {url}")
        html = fetch_html(url)
        if not html:
            break
        payload = extract_json_payload(html)
        if not payload:
            print("[Domiporta] Brak __NEXT_DATA__ — sprawdź czy strona nie blokuje scrapera")
            break
        items = parse_items(payload)
        listings = [n for item in items if (n := normalize_listing(item))]
        print(f"[Domiporta] Znaleziono {len(listings)} ofert na stronie {page}")
        if not listings:
            break
        all_listings.extend(listings)

    return apply_filters(
        all_listings,
        min_price=min_price, max_price=max_price,
        min_area=min_area, max_area=max_area,
        rooms=rooms, direct_only=direct_only,
    )