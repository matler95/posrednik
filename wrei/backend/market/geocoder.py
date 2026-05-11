"""
Geocoder — zamienia adres ulicy na dzielnicę Warszawy (lub innego miasta).
Używa Nominatim (OpenStreetMap) + lokalny cache w tabeli geocode_cache.
Rate limit Nominatim: 1 req/s (polityka użytkowania).
"""
import logging
import time

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {
    "User-Agent": "WREI-RealEstateAnalyzer/1.0 (contact: wrei@localhost)",
    "Accept-Language": "pl",
}
RATE_LIMIT_SLEEP = 1.1  # Nominatim: max 1 req/s

# Mapa city_slug → pełna nazwa dla Nominatim
CITY_NAMES = {
    "warszawa": "Warsaw",
    "krakow": "Kraków",
    "wroclaw": "Wrocław",
    "poznan": "Poznań",
    "gdansk": "Gdańsk",
    "gdynia": "Gdynia",
    "katowice": "Katowice",
    "lodz": "Łódź",
}


def geocode_address(street_address: str, city_slug: str = "warszawa") -> dict | None:
    """
    Geocoduje adres ulicy przez Nominatim.
    Zwraca słownik z kluczami: district, lat, lng.

    Dzielnicę wyciąga z pola address.suburb / city_district / neighbourhood.
    Dla Warszawy nominatim zwraca np. "Mokotów", "Śródmieście", "Wilanów".
    """
    city_en = CITY_NAMES.get(city_slug, city_slug.capitalize())
    query = f"{street_address}, {city_en}, Poland"

    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "addressdetails": 1, "limit": 1},
            headers=NOMINATIM_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
    except Exception as exc:
        logger.warning("[Geocoder] Błąd dla '%s': %s", query, exc)
        return None

    if not results:
        logger.debug("[Geocoder] Brak wyników dla: %s", query)
        return None

    best = results[0]
    addr = best.get("address", {})

    # Nominatim zwraca różne klucze w zależności od miasta
    district = (
        addr.get("suburb")
        or addr.get("city_district")
        or addr.get("neighbourhood")
        or addr.get("borough")
        or addr.get("district")
    )

    return {
        "district": district,
        "lat": float(best.get("lat", 0)),
        "lng": float(best.get("lon", 0)),
    }


def batch_geocode(
    items: list[dict],
    city_slug: str = "warszawa",
    sleep_s: float = RATE_LIMIT_SLEEP,
) -> dict[str, dict]:
    """
    Geocoduje listę unikalnych adresów.
    items: lista słowników z kluczami 'invest_slug' i 'street_address'
    Zwraca słownik {invest_slug: {district, lat, lng}}.
    """
    from backend.db import get_geocode_cache, save_geocode_cache

    # Pobierz cache z DB
    cached = get_geocode_cache([i["invest_slug"] for i in items if i.get("invest_slug")])
    results = dict(cached)

    to_geocode = [i for i in items if i.get("invest_slug") and i["invest_slug"] not in results]
    logger.info("[Geocoder] %d adresów do geocodowania (cache: %d)", len(to_geocode), len(results))

    for item in to_geocode:
        slug = item["invest_slug"]
        address = item.get("street_address") or slug.replace("-", " ").title()

        geo = geocode_address(address, city_slug)
        if geo:
            results[slug] = geo
            save_geocode_cache(slug, address, geo)
            logger.debug("[Geocoder] %s → %s", address, geo.get("district"))
        else:
            results[slug] = {"district": None, "lat": None, "lng": None}

        time.sleep(sleep_s)

    return results
