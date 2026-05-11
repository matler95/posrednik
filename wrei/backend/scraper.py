"""
scraper.py — główny entry point scrapowania.
NAPRAWKA: enrich_listings wywoływane PRZED save_listings.
"""
import logging

from backend.scrapers import PORTAL_SCRAPERS, AVAILABLE_PORTALS
from backend.scraper_utils import deduplicate_listings

logger = logging.getLogger(__name__)


def available_portals():
    return AVAILABLE_PORTALS.copy()


def normalize_portals(portals):
    if portals is None:
        return [p.lower() for p in AVAILABLE_PORTALS]
    if isinstance(portals, str):
        result = [p.strip().lower() for p in portals.split(",") if p.strip()]
        return result or [p.lower() for p in AVAILABLE_PORTALS]
    return [p.strip().lower() for p in portals if isinstance(p, str) and p.strip()]


def search(
    city_slug="warszawa",
    portals=None,
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=3,
    direct_only=False, districts=None,
) -> list[dict]:
    """
    Scrapuje oferty ze wszystkich podanych portali.
    Zwraca surowe (nie wzbogacone) oferty — enrichment robi wywołujący.
    """
    selected_portals = normalize_portals(portals)
    all_listings = []

    # Jeśli brak dzielnic = skanuj całe miasto (jedna iteracja z district=None)
    districts_to_scan = districts if districts else [None]

    for portal_name in selected_portals:
        scraper_fn = PORTAL_SCRAPERS.get(portal_name)
        if not scraper_fn:
            logger.warning("[Scraper] Nieznany portal: %s", portal_name)
            continue

        for district in districts_to_scan:
            try:
                dist_label = district or "CAŁE MIASTO"
                logger.info("[Scraper] %s | %s | %s", portal_name.upper(), city_slug.upper(), dist_label)

                listings = scraper_fn(
                    min_price=min_price,
                    max_price=max_price,
                    min_area=min_area,
                    max_area=max_area,
                    rooms=rooms,
                    pages=pages,
                    direct_only=direct_only,
                    district=district,
                )

                # Oznacz city_slug
                for l in listings:
                    l["city_slug"] = city_slug

                logger.info("[Scraper] %s (%s): %d ofert", portal_name.upper(), dist_label, len(listings))
                all_listings.extend(listings)

            except Exception as e:
                logger.error("[Scraper] Błąd %s/%s: %s", portal_name, district or "all", e, exc_info=True)
                continue

    deduped = deduplicate_listings(all_listings)
    logger.info("[Scraper] Łącznie po deduplicji: %d ofert", len(deduped))
    return deduped


def search_and_enrich(
    city_slug="warszawa",
    portals=None,
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=3,
    direct_only=False, districts=None,
) -> list[dict]:
    """
    Scrapuje I wzbogaca oferty (RCN benchmark, scoring, NLP).
    Używać zamiast search() gdy potrzebny pełny pipeline.
    """
    from backend.analysis import enrich_listings

    raw = search(
        city_slug=city_slug,
        portals=portals,
        min_price=min_price,
        max_price=max_price,
        min_area=min_area,
        max_area=max_area,
        rooms=rooms,
        pages=pages,
        direct_only=direct_only,
        districts=districts,
    )

    if not raw:
        return []

    logger.info("[Scraper] Wzbogacam %d ofert (city_slug=%s)...", len(raw), city_slug)
    enriched = enrich_listings(raw, city_slug=city_slug)
    logger.info("[Scraper] Wzbogacono %d ofert", len(enriched))
    return enriched
