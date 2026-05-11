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


WARSAW_DISTRICTS = [
    "Bemowo", "Białołęka", "Bielany", "Mokotów", "Ochota", "Praga-Południe", 
    "Praga-Północ", "Rembertów", "Śródmieście", "Targówek", "Ursus", 
    "Ursynów", "Wawer", "Wesoła", "Wilanów", "Włochy", "Wola", "Żoliborz"
]

def search(
    city_slug="warszawa",
    portals=None,
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=1, direct_only=False,
    districts=None
):
    selected_portals = normalize_portals(portals)
    all_listings = []
    
    districts_to_scan = districts if districts else [None]
    
    for portal in selected_portals:
        scraper = PORTAL_SCRAPERS.get(portal)
        if not scraper: continue
        
        for district in districts_to_scan:
            try:
                dist_label = district.upper() if district else "CAŁE MIASTO"
                print(f"[HUNTER] Skanuję {portal.upper()} | Lokalizacja: {city_slug.upper()} ({dist_label})...")
                listings = scraper(
                    min_price=min_price,
                    max_price=max_price,
                    min_area=min_area,
                    max_area=max_area,
                    rooms=rooms,
                    pages=pages,
                    direct_only=direct_only,
                    district=district
                )
                if listings:
                    print(f"[HUNTER] {portal.upper()} ({dist_label}): Znaleziono {len(listings)} ofert")
                    all_listings.extend(listings)
            except Exception as e:
                print(f"[ERR] {portal} {dist_label} błąd: {e}")
                continue

    return deduplicate_listings(all_listings)



