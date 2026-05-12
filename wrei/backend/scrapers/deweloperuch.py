"""
Deweloperuch scraper — dane transakcyjne z Rejestru Cen Nieruchomości (RCN).
API: https://deweloperuch.pl/api/sale-transactions
Publiczne, bez klucza. Rate limit: uprzejmy (1 req/s max).

ULEPSZENIA vs oryginał:
1. Regex geocoding z nazwy adresu — wypełnia district natychmiast,
   bez czekania na Nominatim (który ma rate limit 1 req/s i jest niestabilny).
2. Lepsze obsługiwanie błędów API (timeout, retry z exponential backoff).
3. Batch geocoding jako fallback dla adresów których regex nie rozpozna.
"""
import logging
import re
import time
from datetime import date, timedelta
from typing import Generator

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://deweloperuch.pl/api/sale-transactions"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://deweloperuch.pl/",
    "Accept": "application/json",
}
PER_PAGE = 50
DOWNLOAD_TIMEOUT = 60.0
RATE_LIMIT_SLEEP = 1.2


# ---------------------------------------------------------------------------
# Regex geocoding — wyciąga dzielnicę z nazwy adresu
# Pokrywa ~75% przypadków dla Warszawy bez żadnych requestów zewnętrznych
# ---------------------------------------------------------------------------

WARSAW_DISTRICT_PATTERNS: dict[str, list[str]] = {
    "Mokotów":        [r"mokot", r"pu\s*ławska", r"wierzbno", r"stegny", r"służew"],
    "Ursynów":        [r"ursynów", r"ursynow", r"natolin", r"kabaty", r"imielin"],
    "Śródmieście":    [r"śródmie", r"srodmie", r"centrum", r"marszałkowska", r"nowy\s*świat", r"aleje\s*jerozolimskie"],
    "Wola":           [r"\bwola\b", r"woli\b", r"wolska", r"chłodna", r"młynarska"],
    "Ochota":         [r"ochota", r"raszyńska", r"grójecka", r"opaczewska"],
    "Praga-Południe": [r"praga.południe", r"praga.poludnie", r"grochów", r"saska\s*kępa"],
    "Praga-Północ":   [r"praga.północ", r"praga.polnoc", r"targowa", r"ząbkowska"],
    "Żoliborz":       [r"żoliborz", r"zoliborz", r"wilson", r"marymont"],
    "Bielany":        [r"bielany", r"chomiczówka", r"młociny", r"wrzeciono"],
    "Bemowo":         [r"bemowo", r"górce", r"jelonki"],
    "Targówek":       [r"targówek", r"targowek", r"bródno", r"brodno", r"zacisze"],
    "Białołęka":      [r"białołęka", r"bialoleka", r"tarchomin"],
    "Wilanów":        [r"wilanów", r"wilanow", r"miasteczko\s*wilanów"],
    "Wawer":          [r"wawer", r"anin", r"międzylesie"],
    "Ursus":          [r"\bursus\b"],
    "Włochy":         [r"włochy", r"wlochy", r"okęcie"],
    "Rembertów":      [r"rembertów", r"rembertow"],
    "Wesoła":         [r"\bwesoła\b", r"\bwesola\b", r"stara\s*miłosna"],
}

# Kraków
KRAKOW_DISTRICT_PATTERNS: dict[str, list[str]] = {
    "Śródmieście":   [r"śródmie", r"srodmie", r"stare\s*miasto", r"kazimierz"],
    "Krowodrza":     [r"krowodrza", r"bronowice", r"azory"],
    "Podgórze":      [r"podgórze", r"podgorze", r"płaszów", r"prokocim"],
    "Nowa Huta":     [r"nowa\s*huta", r"mistrzejowice", r"bieńczyce"],
    "Swoszowice":    [r"swoszowice", r"kliny"],
    "Zwierzyniec":   [r"zwierzyniec", r"wola\s*justowska", r"przegorzały"],
}

CITY_DISTRICT_PATTERNS: dict[str, dict[str, list[str]]] = {
    "warszawa": WARSAW_DISTRICT_PATTERNS,
    "krakow":   KRAKOW_DISTRICT_PATTERNS,
    "krakow":   KRAKOW_DISTRICT_PATTERNS,
}


def extract_district_from_address(address: str, city_slug: str = "warszawa") -> str | None:
    """
    Wyciąga dzielnicę z nazwy adresu lub inwestycji przez regex.
    Pokrywa ok. 70-80% przypadków dla Warszawy.
    Nie wymaga żadnych requestów zewnętrznych.

    Przykłady:
      "Ulica Puławska 120" → "Mokotów"
      "Miasteczko Wilanów etap V" → "Wilanów"
      "Grochów przy Rondzie Wiatraczna" → "Praga-Południe"
    """
    if not address:
        return None

    patterns = CITY_DISTRICT_PATTERNS.get(city_slug, {})
    if not patterns:
        return None

    addr_lower = address.lower()
    for district, district_patterns in patterns.items():
        for pattern in district_patterns:
            if re.search(pattern, addr_lower, re.IGNORECASE):
                return district
    return None


# ---------------------------------------------------------------------------
# API fetching
# ---------------------------------------------------------------------------

def _fetch_page(
    client: httpx.Client,
    city_slug: str,
    page: int,
    date_from: str | None = None,
    date_to: str | None = None,
    rooms: int | None = None,
) -> dict:
    """Pobiera jedną stronę z API Deweloperuch z retry."""
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
        except httpx.TimeoutException:
            wait = 2 ** (attempt + 1)
            logger.warning(
                "[Deweloperuch] Timeout strony %d (próba %d/3), czekam %ds",
                page, attempt + 1, wait
            )
            time.sleep(wait)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                wait = 10 * (attempt + 1)
                logger.warning("[Deweloperuch] Rate limit (429), czekam %ds", wait)
                time.sleep(wait)
            else:
                logger.error("[Deweloperuch] HTTP %d dla strony %d", exc.response.status_code, page)
                return {}
        except Exception as exc:
            logger.warning("[Deweloperuch] Błąd strony %d (próba %d/3): %s", page, attempt + 1, exc)
            time.sleep(2 ** attempt)

    logger.error("[Deweloperuch] Wyczerpano próby dla strony %d", page)
    return {}


# ---------------------------------------------------------------------------
# Normalizacja rekordu
# ---------------------------------------------------------------------------

def _normalize(record: dict, city_slug: str) -> dict:
    """
    Spłaszcza rekord API do prostego słownika.
    Wypełnia district przez regex geocoding (instant, bez requestów).
    """
    invest = record.get("invest") or {}
    creation_date = record.get("creation_date", "")

    year = quarter = month = None
    if creation_date and len(creation_date) >= 7:
        try:
            d = date.fromisoformat(creation_date[:10])
            year = d.year
            month = d.month
            quarter = (month - 1) // 3 + 1
        except ValueError:
            pass

    street_address = invest.get("name") or ""
    invest_slug = invest.get("slug") or ""

    # Regex geocoding — wypełnia district bez Nominatim
    district = (
        extract_district_from_address(street_address, city_slug)
        or extract_district_from_address(invest_slug.replace("-", " "), city_slug)
    )

    return {
        "sale_rcn_id": record.get("sale_rcn_id"),
        "city": invest.get("city") or city_slug.capitalize(),
        "city_slug": city_slug,
        "street_address": street_address,
        "invest_slug": invest_slug,
        "district": district,  # wypełnione przez regex lub None
        "amount": _to_int(record.get("amount")),
        "amount_sqm": _to_float(record.get("amount_sqm")),
        "size": _to_float(record.get("size")),
        "rooms_number": record.get("rooms_number"),
        "floor_number": record.get("floor_number"),
        "creation_date": creation_date[:10] if creation_date else None,
        "year": year,
        "quarter": quarter,
        "month": month,
        "is_flipped": bool(record.get("is_flipped", False)),
    }


# ---------------------------------------------------------------------------
# Generatory danych
# ---------------------------------------------------------------------------

def iter_transactions(
    city_slug: str = "warszawa",
    date_from: str | None = None,
    date_to: str | None = None,
    max_pages: int | None = None,
    rooms: int | None = None,
) -> Generator[dict, None, None]:
    """
    Generator zwracający transakcje z API Deweloperuch.
    District wypełniany przez regex (natychmiast).
    Nominatim używany tylko dla pozostałych w tle (przez scheduler).
    """
    with httpx.Client(headers=DEFAULT_HEADERS) as client:
        page = 1
        total_pages = None
        total_records = 0

        while True:
            if max_pages and page > max_pages:
                break

            data = _fetch_page(client, city_slug, page, date_from, date_to, rooms)
            if not data or "data" not in data:
                logger.error("[Deweloperuch] Brak danych na stronie %d", page)
                break

            records = data["data"]
            pagination = data.get("pagination") or {}

            if total_pages is None:
                total_pages = pagination.get("totalPages") or 1
                total = pagination.get("total") or 0
                logger.info(
                    "[Deweloperuch] %s: %d transakcji, %d stron",
                    city_slug, total, total_pages
                )

            for record in records:
                normalized = _normalize(record, city_slug)
                if normalized.get("sale_rcn_id") and normalized.get("amount_sqm"):
                    total_records += 1
                    yield normalized

            logger.debug("[Deweloperuch] Strona %d/%d pobrana", page, total_pages)

            if page >= total_pages:
                break

            page += 1
            time.sleep(RATE_LIMIT_SLEEP)

        logger.info("[Deweloperuch] %s: łącznie %d rekordów", city_slug, total_records)


def fetch_recent(
    city_slug: str = "warszawa",
    days: int = 30,
    max_pages: int = 10,
) -> list[dict]:
    """
    Pobiera transakcje z ostatnich N dni.
    Używane przez scheduler do codziennej aktualizacji.
    """
    date_from = (date.today() - timedelta(days=days)).isoformat()
    date_to = date.today().isoformat()
    return list(iter_transactions(
        city_slug,
        date_from=date_from,
        date_to=date_to,
        max_pages=max_pages,
    ))


def fetch_historical(
    city_slug: str = "warszawa",
    years: int = 5,
) -> list[dict]:
    """
    Pobiera historyczne dane z ostatnich N lat.
    Używane przy pierwszym uruchomieniu (pełna historia).
    Może trwać kilka minut dla dużych miast — uruchamiaj async.
    """
    date_from = (date.today() - timedelta(days=years * 365)).isoformat()
    logger.info(
        "[Deweloperuch] Pobieranie historii %d lat dla %s (od %s)...",
        years, city_slug, date_from
    )
    return list(iter_transactions(city_slug, date_from=date_from))


# ---------------------------------------------------------------------------
# Pomocnicze
# ---------------------------------------------------------------------------

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


def get_district_coverage_stats(city_slug: str = "warszawa") -> dict:
    """
    Zwraca statystyki pokrycia district w bazie transakcji.
    Przydatne do monitorowania jakości geocodingu.
    """
    try:
        from backend.db import get_conn
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(district) as with_district,
                COUNT(DISTINCT district) as unique_districts
            FROM transaction_prices
            WHERE city_slug = %s
        """, (city_slug,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            total, with_district, unique_districts = row
            coverage = round(with_district / total * 100, 1) if total > 0 else 0
            return {
                "total": total,
                "with_district": with_district,
                "coverage_pct": coverage,
                "unique_districts": unique_districts,
            }
    except Exception as exc:
        logger.warning("[Deweloperuch] Stats error: %s", exc)
    return {}
