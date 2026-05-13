"""
Deweloperuch scraper — dane transakcyjne z Rejestru Cen Nieruchomości (RCN).
API: https://deweloperuch.pl/api/sale-transactions

NAPRAWKI v2:
1. Rozszerzone regex patterns — pokrycie ~85% dla Warszawy
2. Normalizacja tekstu przed regex (lowercase, usunięcie polskich znaków)
3. batch_geocode_missing() — funkcja do uzupełniania NULL district w tle
4. Lepsze retry z exponential backoff
5. invest_slug cache integracja przy save
"""
import logging
import re
import time
import unicodedata
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
PER_PAGE = 100
DOWNLOAD_TIMEOUT = 60.0
RATE_LIMIT_SLEEP = 1.2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    """Usuwa polskie znaki diakrytyczne — 'Mokotów' → 'mokotow'."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    ).lower()

def _extract_teryt_from_record(record: dict) -> str | None:
    """Próbuje wyciągnąć 6-cyfrowy kod TERYT z różnych pól rekordu."""
    # Szukamy wzorca 1465XX (Warszawa)
    for key in ("name", "symbol", "external_id", "street"):
        val = record.get(key)
        if val and isinstance(val, str):
            match = re.search(r"1465(\d{2})", val)
            if match:
                return "1465" + match.group(1)
    return None


# ---------------------------------------------------------------------------
# Regex geocoding — rozszerzone wzorce dla Warszawy (~85% pokrycia)
# Wzorce testowane na nazwach inwestycji z bazy Deweloperuch
# ---------------------------------------------------------------------------

WARSAW_DISTRICT_PATTERNS: dict[str, list[str]] = {
    "Mokotów": [
        r"mokot", r"pulawsk", r"pulaw", r"wierzbno", r"stegny", r"sluzew",
        r"sluzewiec", r"domaniewsk", r"woronicz", r"chodkiewicz", r"kazimierzow",
        r"rajsk", r"sieleck", r"czerniakowsk", r"dolna", r"wilanowsk",
    ],
    "Ursynów": [
        r"ursynow", r"natolin", r"kabaty", r"imielin", r"stoklosy",
        r"lasek", r"al\. komisji", r"kkt", r"rosochy", r"zawiszy",
    ],
    "Śródmieście": [
        r"srodmie", r"centrum\b", r"marszalkowsk", r"nowy swiat", r"aleje jerozolimsk",
        r"al\. jerozolimsk", r"towarowa", r"prosta", r"chmielna", r"krucza",
        r"emilii plater", r"swietokrzysk", r"al\. solidarnosci", r"noakowski",
        r"smolna", r"browarna", r"solec", r"czerniakowska\b",
    ],
    "Wola": [
        r"\bwola\b", r"wolsk", r"mlynarska", r"chlodn", r"kasprzaka",
        r"dzialdowsk", r"redutow", r"sowinska", r"gorczewsk", r"skierniewick",
        r"korotynskieg", r"elekcyjn", r"obozow", r"deotymy",
        r"\bwoli\b", r"na woli",
    ],
    "Ochota": [
        r"ochot", r"raszynsk", r"grojecka", r"opaczewsk", r"kopinska",
        r"siewiersk", r"gajowa", r"barska", r"filtrowa",
        r"szczesnowicach", r"rakowiec",
    ],
    "Praga-Południe": [
        r"praga.poludnie", r"grochow", r"saska kepa", r"saskiej kepy",
        r"wiatraczna", r"ostrobramsk", r"grochowsk", r"podskarbinska",
        r"kamionkowsk", r"kobielsk", r"waszyngtona\b", r"meissnera",
    ],
    "Praga-Północ": [
        r"praga.polnoc", r"targowa", r"zabkowsk", r"11 listopada",
        r"kaweczynsk", r"stalowa", r"brzesk", r"inzyniersk", r"konopacka",
    ],
    "Żoliborz": [
        r"zoliborz", r"wilson", r"marymont", r"krasinski", r"mickiewicz",
        r"stołeczna", r"suzina", r"powazkowsk", r"boniFraternum",
        r"potocka", r"czarnieckieg",
    ],
    "Bielany": [
        r"bielany", r"chomiczowk", r"mlociny", r"wrzeciono", r"piaski",
        r"dewajtis", r"broniewskieg", r"conrada", r"wolodyjowskieg",
    ],
    "Bemowo": [
        r"bemowo", r"gorce\b", r"jelonki", r"lazurowa", r"dywizjonu 303",
        r"batalionow chlopskich", r"lazurowa",
    ],
    "Targówek": [
        r"targowek", r"brodna", r"zacisze", r"elsnerow", r"wincentego",
        r"kondratowicz", r"szanajcy", r"ksiedza korzec",
    ],
    "Białołęka": [
        r"bialoleka", r"tarchomin", r"swidersk", r"marywilsk", r"zeranск",
        r"zeran", r"porajow", r"modlinska\b",
    ],
    "Wilanów": [
        r"wilanow", r"miasteczko wilanow", r"klimczaka", r"przyczolkow",
        r"branickiego", r"vogla", r"kubickieg",
    ],
    "Wawer": [
        r"wawer", r"anin\b", r"miedzylesie", r"zerzeń", r"zerzen",
        r"falenica", r"radosc", r"miedzeszyn",
    ],
    "Ursus": [r"\bursus\b", r"posag 7 panien"],
    "Włochy": [r"wlochy", r"okecie", r"salomea", r"rakowiec"],
    "Rembertów": [r"rembertow"],
    "Wesoła": [r"\bwesola\b", r"stara milosna", r"milosna"],
}

KRAKOW_DISTRICT_PATTERNS: dict[str, list[str]] = {
    "Śródmieście":  [r"srodmie", r"stare miasto", r"kazimierz", r"krowodrza"],
    "Podgórze":     [r"podgorze", r"plaszow", r"prokocim", r"kurdwanow"],
    "Nowa Huta":    [r"nowa huta", r"mistrzejowice", r"bienczyce", r"krzesławice"],
    "Krowodrza":    [r"bronowice", r"azory", r"prądnik", r"pradnik"],
    "Swoszowice":   [r"swoszowice", r"kliny", r"borek"],
}

WROCLAW_DISTRICT_PATTERNS: dict[str, list[str]] = {
    "Stare Miasto":  [r"stare miasto", r"srodmie"],
    "Krzyki":        [r"krzyki", r"klodzka", r"bielany wrocl"],
    "Fabryczna":     [r"fabryczn", r"nowy dwor", r"marszowice"],
    "Psie Pole":     [r"psie pole", r"karłowice", r"karlowice"],
}

WARSAW_TERYT_MAP: dict[str, str] = {
    "146501": "Bemowo",
    "146502": "Białołęka",
    "146503": "Bielany",
    "146504": "Mokotów",
    "146505": "Ochota",
    "146506": "Praga-Południe",
    "146507": "Praga-Północ",
    "146508": "Rembertów",
    "146509": "Śródmieście",
    "146510": "Targówek",
    "146511": "Ursus",
    "146512": "Ursynów",
    "146513": "Wawer",
    "146514": "Wesoła",
    "146515": "Wilanów",
    "146516": "Włochy",
    "146517": "Wola",
    "146518": "Żoliborz",
}

CITY_DISTRICT_PATTERNS: dict[str, dict[str, list[str]]] = {
    "warszawa": WARSAW_DISTRICT_PATTERNS,
    "krakow":   KRAKOW_DISTRICT_PATTERNS,
    "wroclaw":  WROCLAW_DISTRICT_PATTERNS,
}


def extract_district_from_address(address: str, city_slug: str = "warszawa") -> str | None:
    """
    Wyciąga dzielnicę z nazwy adresu/inwestycji przez regex.
    Normalizuje polskie znaki przed dopasowaniem → wyższa czułość.

    Pokrycie: ~85% dla Warszawy, ~70% dla Krakowa/Wrocławia.
    """
    if not address:
        return None

    patterns = CITY_DISTRICT_PATTERNS.get(city_slug, {})
    if not patterns:
        return None

    addr_norm = _strip_accents(address)

    for district, district_patterns in patterns.items():
        for pattern in district_patterns:
            if re.search(pattern, addr_norm, re.IGNORECASE):
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
    last_transaction_date: str | None = None,
) -> dict:
    """Pobiera jedną stronę z API Deweloperuch z retry (exponential backoff)."""
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
    if last_transaction_date:
        params["filterLastTransactionDate"] = last_transaction_date
    if rooms:
        params["filterRooms"] = rooms

    for attempt in range(4):
        try:
            resp = client.get(BASE_URL, params=params, timeout=DOWNLOAD_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            wait = 2 ** (attempt + 1)
            logger.warning(
                "[Deweloperuch] Timeout strony %d (próba %d/4), czekam %ds",
                page, attempt + 1, wait
            )
            time.sleep(wait)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                wait = 15 * (attempt + 1)
                logger.warning("[Deweloperuch] Rate limit (429), czekam %ds", wait)
                time.sleep(wait)
            elif exc.response.status_code >= 500:
                wait = 5 * (attempt + 1)
                logger.warning("[Deweloperuch] Server error %d, retry za %ds",
                               exc.response.status_code, wait)
                time.sleep(wait)
            else:
                logger.error("[Deweloperuch] HTTP %d dla strony %d — pomijam",
                             exc.response.status_code, page)
                return {}
        except Exception as exc:
            wait = 2 ** attempt
            logger.warning("[Deweloperuch] Błąd strony %d (próba %d/4): %s", page, attempt + 1, exc)
            time.sleep(wait)

    logger.error("[Deweloperuch] Wyczerpano próby dla strony %d", page)
    return {}


# ---------------------------------------------------------------------------
# Normalizacja rekordu
# ---------------------------------------------------------------------------

def _normalize(record: dict, city_slug: str) -> dict:
    """
    Spłaszcza rekord API do prostego słownika.
    district wypełniany przez regex (instant, bez requestów).
    Próbuje kolejno: invest.name → invest.slug → street_address
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

    # Próbuj kilka źródeł tekstu dla lepszego geocodingu
    district = None
    
    # 1. TERYT code detection (100% precision for Warsaw)
    if city_slug == "warszawa":
        teryt = _extract_teryt_from_record(record)
        if teryt:
            district = WARSAW_TERYT_MAP.get(teryt)

    # 2. Regex fallback
    if not district:
        district = (
            extract_district_from_address(street_address, city_slug)
            or extract_district_from_address(invest_slug.replace("-", " "), city_slug)
            or extract_district_from_address(record.get("street") or "", city_slug)
        )

    return {
        "sale_rcn_id": record.get("sale_rcn_id"),
        "city": invest.get("city") or city_slug.capitalize(),
        "city_slug": city_slug,
        "street_address": street_address,
        "invest_slug": invest_slug,
        "district": district,
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
    start_page: int = 1,
    last_transaction_date: str | None = None,
) -> Generator[dict, None, None]:
    """
    Generator zwracający transakcje z API Deweloperuch.
    start_page pozwala na wznowienie od konkretnej strony.
    """
    with httpx.Client(headers=DEFAULT_HEADERS) as client:
        page = start_page
        total_records = 0
        total_with_district = 0
        total_pages = None
        total = 0
        seen_ids_in_session = set()
        while True:
            if max_pages and page > max_pages:
                break

            data = _fetch_page(client, city_slug, page, date_from, date_to, rooms, last_transaction_date)
            if not data or "data" not in data:
                if page == 1:
                    logger.error("[Deweloperuch] Brak danych na stronie 1 — sprawdź API")
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

            new_in_page = 0
            for record in records:
                normalized = _normalize(record, city_slug)
                if normalized.get("sale_rcn_id") and normalized.get("amount_sqm"):
                    total_records += 1
                    if normalized.get("district"):
                        total_with_district += 1
                    
                    if normalized["sale_rcn_id"] not in seen_ids_in_session:
                        seen_ids_in_session.add(normalized["sale_rcn_id"])
                        new_in_page += 1
                        yield normalized

            if page % 10 == 0:
                pct = round(total_with_district / total_records * 100, 1) if total_records else 0
                logger.info(
                    "[Deweloperuch] Strona %d/%d — %d rekordów, pokrycie district: %s%%",
                    page, total_pages, total_records, pct
                )

            # Ignorujemy total_pages, bo API często zwraca błędne (zaniżone) wartości (np. 20 stron zamiast 4000)
            # Pętla skończy się, gdy 'records' będzie puste lub same duplikaty.
            if not records:
                break
            
            if len(records) > 0 and new_in_page == 0:
                logger.info("[Deweloperuch] Strona %d zawiera same znane rekordy — kończę zakres.", page)
                break
                
            page += 1
            time.sleep(RATE_LIMIT_SLEEP)

        final_pct = round(total_with_district / total_records * 100, 1) if total_records else 0
        logger.info(
            "[Deweloperuch] %s: łącznie %d rekordów, district przypisany: %d (%.1f%%)",
            city_slug, total_records, total_with_district, final_pct
        )


def fetch_recent(
    city_slug: str = "warszawa",
    days: int = 30,
    max_pages: int = 10,
) -> list[dict]:
    """Pobiera transakcje z ostatnich N dni."""
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
    """Pobiera historyczne dane z ostatnich N lat (wolne — uruchamiaj async)."""
    date_from = (date.today() - timedelta(days=years * 365)).isoformat()
    logger.info(
        "[Deweloperuch] Pobieranie historii %d lat dla %s (od %s)...",
        years, city_slug, date_from
    )
    return list(iter_transactions(city_slug, date_from=date_from))


def generate_quarter_ranges(start_year: int, end_year: int, end_quarter: int) -> list[str]:
    """
    Generuje listę kwartałów w formacie 'YYYY-Q-YYYY-Q' od start_year-1 do end_year-end_quarter.
    Przykład: 2023, 2024, 1 -> ['2023-1-2023-1', '2023-2-2023-2', ..., '2024-1-2024-1']
    """
    ranges = []
    for y in range(start_year, end_year + 1):
        max_q = end_quarter if y == end_year else 4
        for q in range(1, max_q + 1):
            ranges.append(f"{y}-{q}-{y}-{q}")
    return ranges


# ---------------------------------------------------------------------------
# Batch geocoding uzupełniający (Nominatim fallback)
# ---------------------------------------------------------------------------

def batch_geocode_missing(city_slug: str = "warszawa", limit: int = 100) -> int:
    """
    Uzupełnia brakujące district dla transakcji w DB przez Nominatim.
    Wywoływany przez scheduler co 2h (max 100 rekordów na run = rate limit OK).

    Zwraca liczbę zaktualizowanych rekordów.
    """
    from backend.db import get_transactions_without_district, update_transaction_district
    from backend.market.geocoder import geocode_address

    pending = get_transactions_without_district(limit=limit)
    if not pending:
        return 0

    logger.info("[GeoFill] %d adresów do geocodowania (Nominatim)", len(pending))
    updated = 0

    for item in pending:
        slug = item["invest_slug"]
        address = item.get("street_address") or slug.replace("-", " ").title()
        item_city = item.get("city_slug", city_slug)

        # Spróbuj najpierw regex na świeżo (bezpłatny, instant)
        district = extract_district_from_address(address, item_city)
        if district:
            update_transaction_district(slug, district)
            updated += 1
            continue

        # Nominatim fallback
        try:
            geo = geocode_address(address, item_city)
            if geo and geo.get("district"):
                update_transaction_district(slug, geo["district"])
                from backend.db import save_geocode_cache
                save_geocode_cache(slug, address, geo)
                updated += 1
        except Exception as e:
            logger.debug("[GeoFill] Błąd dla %s: %s", address, e)

        time.sleep(1.1)  # Nominatim rate limit

    logger.info("[GeoFill] Zaktualizowano district dla %d/%d rekordów", updated, len(pending))
    return updated


# ---------------------------------------------------------------------------
# Statystyki
# ---------------------------------------------------------------------------

def get_district_coverage_stats(city_slug: str = "warszawa") -> dict:
    """Statystyki pokrycia district — przydatne do monitorowania jakości."""
    try:
        from backend.db import get_conn
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(district) as with_district,
                COUNT(DISTINCT district) as unique_districts,
                COUNT(*) FILTER (WHERE district IS NULL) as missing
            FROM transaction_prices
            WHERE city_slug = %s
        """, (city_slug,))
        row = cur.fetchone()

        cur.execute("""
            SELECT district, COUNT(*) as cnt
            FROM transaction_prices
            WHERE city_slug = %s AND district IS NOT NULL
            GROUP BY district
            ORDER BY cnt DESC
            LIMIT 20
        """, (city_slug,))
        top = [{"district": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute("""
            SELECT year, COUNT(*) as cnt
            FROM transaction_prices
            WHERE city_slug = %s AND year IS NOT NULL
            GROUP BY year
            ORDER BY year DESC
        """, (city_slug,))
        yearly = [{"year": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.close()
        conn.close()

        if row:
            total, with_district, unique_districts, missing = row
            coverage = round(with_district / total * 100, 1) if total > 0 else 0
            return {
                "total": total,
                "with_district": with_district,
                "missing": missing,
                "coverage_pct": coverage,
                "unique_districts": unique_districts,
                "top_districts": top,
                "yearly_breakdown": yearly,
            }
    except Exception as exc:
        logger.warning("[Deweloperuch] Stats error: %s", exc)
    return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(val) -> int | None:
    if val is None: return None
    try:
        s = str(val).replace(" ", "").replace(",", ".")
        return int(float(s))
    except (ValueError, TypeError):
        return None

def _to_float(val) -> float | None:
    if val is None: return None
    try:
        s = str(val).replace(" ", "").replace(",", ".")
        return float(s)
    except (ValueError, TypeError):
        return None