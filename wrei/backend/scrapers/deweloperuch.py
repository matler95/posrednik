"""
Deweloperuch scraper — dane transakcyjne z Rejestru Cen Nieruchomości (RCN).
API: https://deweloperuch.pl/api/sale-transactions
Publiczne, bez klucza. Rate limit: uprzejmy (1 req/s max).
"""
import logging
import time
from datetime import date, timedelta
from typing import Generator

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://deweloperuch.pl/api/sale-transactions"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://deweloperuch.pl/",
    "Accept": "application/json",
}
PER_PAGE = 50  # mniejszy batch dla stabilności
DOWNLOAD_TIMEOUT = 60.0 # dłuzszy timeout dla wolnego API
RATE_LIMIT_SLEEP = 1.2  # sekundy między requestami



def _fetch_page(
    client: httpx.Client,
    city_slug: str,
    page: int,
    date_from: str | None = None,
    date_to: str | None = None,
    rooms: int | None = None,
) -> dict:
    """Pobiera jedną stronę wyników z API."""
    params: dict = {
        "page": page,
        "perPage": PER_PAGE,
        "sortBy": "creation_date",
        "sortOrder": "desc",
        "filterCitySlug": city_slug,
        "type": "mieszkalna",
    }
    if date_from:
        params["filterDateFrom"] = date_from
    if date_to:
        params["filterDateTo"] = date_to
    if rooms:
        params["filterRooms"] = rooms

    for attempt in range(3):
        try:
            resp = client.get(BASE_URL, params=params, timeout=DOWNLOAD_TIMEOUT)
            resp.raise_for_status()
            return resp.json()

        except (httpx.HTTPError, Exception) as exc:
            wait = 2 ** attempt
            logger.warning("[Deweloperuch] Błąd strony %d (próba %d/3): %s — czekam %ds",
                           page, attempt + 1, exc, wait)
            time.sleep(wait)
    return {}


def iter_transactions(
    city_slug: str = "warszawa",
    date_from: str | None = None,
    date_to: str | None = None,
    max_pages: int | None = None,
    rooms: int | None = None,
) -> Generator[dict, None, None]:
    """
    Generator zwracający transakcje z API Deweloperuch.
    Każdy element to pojedyncza transakcja (jeden akt notarialny).

    Parametry:
        city_slug: np. 'warszawa', 'krakow', 'wroclaw'
        date_from: 'YYYY-MM-DD' — brak = od początku bazy (~2010)
        date_to:   'YYYY-MM-DD' — brak = dzisiaj
        max_pages: limit stron (None = wszystkie)
        rooms:     filtr liczby pokoi (None = wszystkie)
    """
    with httpx.Client(headers=DEFAULT_HEADERS) as client:
        page = 1
        total_pages = None

        while True:
            if max_pages and page > max_pages:
                break

            data = _fetch_page(client, city_slug, page, date_from, date_to, rooms)
            if not data or "data" not in data:
                logger.error("[Deweloperuch] Brak danych na stronie %d", page)
                break

            records = data["data"]
            pagination = data.get("pagination", {})

            if total_pages is None:
                total_pages = pagination.get("totalPages", 1)
                total = pagination.get("total", 0)
                logger.info(
                    "[Deweloperuch] %s: %d transakcji, %d stron",
                    city_slug, total, total_pages
                )

            for record in records:
                yield _normalize(record, city_slug)

            if page >= total_pages:
                break

            page += 1
            time.sleep(RATE_LIMIT_SLEEP)


def _normalize(record: dict, city_slug: str) -> dict:
    """
    Spłaszcza rekord API do prostego słownika.
    Wydziela adres ulicy z invest.name dla geocodingu.
    """
    invest = record.get("invest") or {}
    creation_date = record.get("creation_date", "")

    # Parsowanie roku/kwartału/miesiąca
    year = quarter = month = None
    if creation_date and len(creation_date) >= 7:
        try:
            d = date.fromisoformat(creation_date)
            year = d.year
            month = d.month
            quarter = (month - 1) // 3 + 1
        except ValueError:
            pass

    return {
        "sale_rcn_id": record.get("sale_rcn_id"),
        "city": invest.get("city", city_slug.capitalize()),
        "city_slug": city_slug,
        "street_address": invest.get("name"),       # np. "Ulica Sarmacka 27"
        "invest_slug": invest.get("slug"),            # np. "ulica-sarmacka-27-warszawa"
        "amount": _to_int(record.get("amount")),
        "amount_sqm": _to_float(record.get("amount_sqm")),
        "size": _to_float(record.get("size")),
        "rooms_number": record.get("rooms_number"),
        "floor_number": record.get("floor_number"),
        "creation_date": creation_date,
        "year": year,
        "quarter": quarter,
        "month": month,
        "is_flipped": record.get("is_flipped", False),
    }


def _to_int(val) -> int | None:
    try:
        return int(float(val)) if val is not None else None
    except (ValueError, TypeError):
        return None


def _to_float(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def fetch_recent(city_slug: str = "warszawa", days: int = 30, max_pages: int = 10):
    """
    Pobiera transakcje z ostatnich N dni. Używane przez scheduler do aktualizacji.
    """
    date_from = (date.today() - timedelta(days=days)).isoformat()
    date_to = date.today().isoformat()
    return list(iter_transactions(city_slug, date_from=date_from, date_to=date_to,
                                  max_pages=max_pages))


def fetch_historical(city_slug: str = "warszawa", years: int = 5):
    """
    Pobiera historyczne dane z ostatnich N lat.
    Używane przy pierwszym uruchomieniu (pełna historia).
    Może trwać kilka minut dla dużych miast.
    """
    date_from = (date.today() - timedelta(days=years * 365)).isoformat()
    return list(iter_transactions(city_slug, date_from=date_from))
