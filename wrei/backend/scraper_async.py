"""
Async Scraper Engine — równoległe pobieranie ofert ze wszystkich portali.
Każdy portal uruchamiany jako osobny asyncio task, wyniki agregowane po zakończeniu.

NAPRAWKI v2:
- city_slug przekazywany do każdej oferty (był gubiony)
- Lepsza obsługa wyjątków per-portal (nie crashuje całego joba)
- Deduplikacja po URL zachowuje najnowszą wersję
- Logowanie postępu per-portal
"""
import asyncio
import logging
import random
import time
from typing import Callable

import httpx

from backend.scraper_utils import deduplicate_listings

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

PORTAL_DELAYS = {
    "otodom": 1.2,
    "olx": 1.0,
    "morizon": 2.0,
    "gratka": 2.0,
    "domiporta": 1.5,
    "nieruchomosci_online": 1.0,
}


async def fetch_html_async(url: str, client: httpx.AsyncClient, portal: str = "default") -> str:
    """Async HTML fetch z retry i rotacją UA."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.7",
        "DNT": "1",
    }
    delay = PORTAL_DELAYS.get(portal, 1.5)

    for attempt in range(3):
        try:
            resp = await client.get(url, headers=headers, timeout=20.0, follow_redirects=True)
            if resp.status_code in (429, 503, 502):
                wait = delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning("[%s] status %d, czekam %.1fs", portal, resp.status_code, wait)
                await asyncio.sleep(wait)
                continue
            if resp.status_code in (403, 404):
                logger.warning("[%s] %d dla %s", portal, resp.status_code, url)
                return ""
            resp.raise_for_status()
            await asyncio.sleep(delay)
            return resp.text
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as e:
            wait = delay * (2 ** attempt)
            logger.warning("[%s] timeout/err (próba %d/3): %s — czekam %.1fs", portal, attempt + 1, e, wait)
            await asyncio.sleep(wait)
        except Exception as e:
            logger.error("[%s] nieoczekiwany błąd %s: %s", portal, url, e)
            return ""

    logger.error("[%s] wyczerpano próby dla: %s", portal, url)
    return ""


async def _run_portal_async(
    portal_name: str,
    scraper_fn: Callable,
    params: dict,
    city_slug: str,
    progress_cb: Callable | None = None,
) -> list[dict]:
    loop = asyncio.get_event_loop()
    SCRAPER_TIMEOUT = 120  # 2 minuty max per portal
    try:
        logger.info("[Hunt] Start: %s / %s", portal_name, city_slug)
        t0 = time.time()
        
        future = loop.run_in_executor(None, lambda: scraper_fn(**params))
        results = await asyncio.wait_for(future, timeout=SCRAPER_TIMEOUT)
        
        elapsed = time.time() - t0
        for listing in results:
            if not listing.get("city_slug"):
                listing["city_slug"] = city_slug
        
        logger.info("[Hunt] %s: %d ofert w %.1fs", portal_name, len(results), elapsed)
        if progress_cb:
            await progress_cb(portal_name, len(results))
        return results
        
    except asyncio.TimeoutError:
        logger.error("[Hunt] TIMEOUT %s po %ds — pomijam portal", portal_name, SCRAPER_TIMEOUT)
        if progress_cb:
            await progress_cb(portal_name, 0)
        return []
    except Exception as e:
        logger.error("[Hunt] Błąd portalu %s: %s", portal_name, e)
        if progress_cb:
            await progress_cb(portal_name, 0)
        return []


async def run_hunt_async(
    config: dict,
    progress_cb: Callable | None = None,
) -> list[dict]:
    """
    Główna funkcja scrapowania — uruchamia wszystkie portale równolegle.

    config keys: portals, pages, min_price, max_price, min_area, max_area,
                 rooms, districts, direct_only, city_slug

    progress_cb: async callable(portal_name, count) — wywoływana po każdym portalu.
    """
    from backend.scrapers import PORTAL_SCRAPERS

    city_slug = config.get("city_slug") or "warszawa"
    portals = config.get("portals") or list(PORTAL_SCRAPERS.keys())
    if isinstance(portals, str):
        portals = [p.strip() for p in portals.split(",") if p.strip()]

    pages = int(config.get("pages", 3))
    districts = config.get("districts") or [None]
    if isinstance(districts, list) and len(districts) == 0:
        districts = [None]

    scraper_params_base = {
        "min_price": config.get("min_price"),
        "max_price": config.get("max_price"),
        "min_area": config.get("min_area"),
        "max_area": config.get("max_area"),
        "rooms": config.get("rooms") or None,
        "pages": pages,
        "direct_only": bool(config.get("direct_only", False)),
    }

    tasks = []
    for portal_name in portals:
        scraper_fn = PORTAL_SCRAPERS.get(portal_name)
        if not scraper_fn:
            logger.warning("[Hunt] Nieznany portal: %s", portal_name)
            continue
        for district in districts:
            params = {**scraper_params_base, "district": district}
            tasks.append(
                _run_portal_async(portal_name, scraper_fn, params, city_slug, progress_cb)
            )

    if not tasks:
        logger.warning("[Hunt] Brak tasków do uruchomienia — sprawdź listę portali")
        return []

    logger.info("[Hunt] Uruchamiam %d tasków równolegle", len(tasks))
    results_nested = await asyncio.gather(*tasks, return_exceptions=True)

    all_listings = []
    for i, result in enumerate(results_nested):
        if isinstance(result, list):
            all_listings.extend(result)
        elif isinstance(result, Exception):
            logger.error("[Hunt] Task %d exception: %s", i, result)

    deduped = deduplicate_listings(all_listings)
    logger.info("[Hunt] Łącznie: %d unikalnych ofert (przed deduplikacją: %d)", len(deduped), len(all_listings))
    return deduped