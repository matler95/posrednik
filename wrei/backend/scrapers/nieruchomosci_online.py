import re
import requests
from backend.scraper_utils import apply_filters

# Publiczne API — nie wymaga auth
NIERUCHOMOSCI_ONLINE_API = "https://www.nieruchomosci-online.pl/ajax/offers/search"


def available():
    return "nieruchomosci_online"


def build_api_params(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, page=1,
) -> dict:
    params = {
        "transaction": "1",       # 1 = sprzedaż
        "category": "1",          # 1 = mieszkanie
        "location[city]": "Warszawa",
        "location[province]": "mazowieckie",
        "page": str(page),
        "limit": "50",
        "sortBy": "newest",
    }
    if min_price:
        params["priceMin"] = str(min_price)
    if max_price:
        params["priceMax"] = str(max_price)
    if min_area:
        params["areaMin"] = str(min_area)
    if max_area:
        params["areaMax"] = str(max_area)
    if rooms:
        rooms_str = str(rooms).split("-")[0].split(",")[0].strip()
        if rooms_str.isdigit():
            params["rooms"] = rooms_str
    return params


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nieruchomosci-online.pl/",
    "X-Requested-With": "XMLHttpRequest",
}


def normalize_listing(item: dict) -> dict | None:
    try:
        price = item.get("price") or item.get("totalPrice")
        price = int(float(price)) if price else None

        area = item.get("area") or item.get("surfaceArea") or item.get("m2")
        area = float(area) if area else None

        rooms = item.get("rooms") or item.get("roomsNumber")

        # Lokalizacja
        district = (
            item.get("district")
            or item.get("districtName")
            or item.get("quarter")
            or "Warszawa"
        )

        url = item.get("url") or item.get("detailUrl") or item.get("link") or ""
        if url and not url.startswith("http"):
            url = f"https://www.nieruchomosci-online.pl{url}"

        title = item.get("title") or item.get("name") or f"Mieszkanie {district} {area}m²"

        # Bezpośredni — pole advertType lub ownerType
        advert_type = str(item.get("advertType") or item.get("ownerType") or "").lower()
        direct_offer = advert_type in ("private", "owner", "prywatne", "wlasciciel")

        # Zdjęcia
        photos = item.get("photos") or item.get("images") or []
        images = []
        for p in photos[:5]:
            if isinstance(p, dict):
                images.append(p.get("url") or p.get("src") or "")
            elif isinstance(p, str):
                images.append(p)
        images = [i for i in images if i]

        price_per_m2 = item.get("pricePerM2") or item.get("pricePerMeter")
        price_per_m2 = float(price_per_m2) if price_per_m2 else None

        if not price:
            return None

        return {
            "portal": "nieruchomosci_online",
            "title": title,
            "price": price,
            "area": area,
            "rooms": rooms,
            "district": district,
            "url": url,
            "direct_offer": direct_offer,
            "price_per_m2": price_per_m2,
            "source": "nieruchomosci_online",
            "images": images,
        }
    except Exception as e:
        print(f"[Nieruchomosci-online] Błąd normalizacji: {e}")
        return None


def search(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=1, direct_only=False,
    **kwargs,
) -> list[dict]:
    all_listings = []
    for page in range(1, pages + 1):
        params = build_api_params(
            min_price=min_price, max_price=max_price,
            min_area=min_area, max_area=max_area,
            rooms=rooms, page=page,
        )
        print(f"[Nieruchomosci-online] Strona {page}: {NIERUCHOMOSCI_ONLINE_API}")
        try:
            response = requests.get(
                NIERUCHOMOSCI_ONLINE_API,
                params=params,
                headers=HEADERS,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[Nieruchomosci-online] Błąd zapytania: {e}")
            break

        # Typowe struktury odpowiedzi API
        items = (
            data.get("offers")
            or data.get("items")
            or data.get("results")
            or data.get("data")
            or []
        )
        if isinstance(items, dict):
            items = items.get("items") or items.get("offers") or []

        listings = [n for item in items if (n := normalize_listing(item))]
        print(f"[Nieruchomosci-online] Znaleziono {len(listings)} ofert na stronie {page}")
        if not listings:
            # Debug
            print(f"[Nieruchomosci-online] Klucze odpowiedzi: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            break
        all_listings.extend(listings)

    return apply_filters(
        all_listings,
        min_price=min_price, max_price=max_price,
        min_area=min_area, max_area=max_area,
        rooms=rooms, direct_only=direct_only,
    )