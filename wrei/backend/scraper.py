from backend.scrapers import PORTAL_SCRAPERS, AVAILABLE_PORTALS
from backend.scraper_utils import deduplicate_listings


def available_portals():
    return AVAILABLE_PORTALS.copy()


def normalize_portals(portals):
    if portals is None:
        return [portal.lower() for portal in AVAILABLE_PORTALS]
    if isinstance(portals, str):
        result = [portal.strip().lower() for portal in portals.split(",") if portal.strip()]
        return result or [portal.lower() for portal in AVAILABLE_PORTALS]
    return [portal.strip().lower() for portal in portals if isinstance(portal, str) and portal.strip()]


def search(
    query_url=None,
    portals=None,
    min_price=None,
    max_price=None,
    min_area=None,
    max_area=None,
    rooms=None,
    pages=1,
    direct_only=False,
):
    selected_portals = normalize_portals(portals)
    if query_url and len(selected_portals) != 1:
        raise ValueError("query_url może być użyte tylko z jednym portalu.")

    listings = []
    for portal in selected_portals:
        scraper = PORTAL_SCRAPERS.get(portal)
        if not scraper:
            continue

        if query_url:
            listings.extend(
                scraper(
                    query_url=query_url,
                    min_price=min_price,
                    max_price=max_price,
                    min_area=min_area,
                    max_area=max_area,
                    rooms=rooms,
                    pages=pages,
                    direct_only=direct_only,
                )
            )
        else:
            listings.extend(
                scraper(
                    min_price=min_price,
                    max_price=max_price,
                    min_area=min_area,
                    max_area=max_area,
                    rooms=rooms,
                    pages=pages,
                    direct_only=direct_only,
                )
            )

    return deduplicate_listings(listings)
