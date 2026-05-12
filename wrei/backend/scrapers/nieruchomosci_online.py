# backend/scrapers/nieruchomosci_online.py
import json, re, logging
from bs4 import BeautifulSoup
from backend.scraper_utils import apply_filters, fetch_html, validate_listing

logger = logging.getLogger(__name__)

NO_BASE = "https://www.nieruchomosci-online.pl/szukaj.html"

def available():
    return "nieruchomosci_online"

def build_no_url(min_price=None, max_price=None, min_area=None, max_area=None,
                  rooms=None, page=1) -> str:
    # Portal używa hash-based filtrów: /szukaj.html#mieszkania-na-sprzedaz;...
    # Ale GET params też działają
    params = [
        "2",        # typ: mieszkanie
        "1",        # transakcja: sprzedaz
    ]
    qs_parts = [f"p={page}"]
    if min_price: qs_parts.append(f"price_from={min_price}")
    if max_price: qs_parts.append(f"price_to={max_price}")
    if min_area:  qs_parts.append(f"area_from={min_area}")
    if max_area:  qs_parts.append(f"area_to={max_area}")
    if rooms:
        r = str(rooms).split(",")[0].strip()
        if r.isdigit(): qs_parts.append(f"rooms_from={r}&rooms_to={r}")
    return f"{NO_BASE}?{'&'.join(qs_parts)}"

def _extract_from_window_state(html: str) -> list[dict]:
    """Portal często wstrzykuje dane jako window.__PRELOADED_STATE__ lub podobne."""
    patterns = [
        r'window\.__PRELOADED_STATE__\s*=\s*(\{.+?\});',
        r'window\.__STATE__\s*=\s*(\{.+?\});',
        r'window\.__INITIAL_DATA__\s*=\s*(\{.+?\});',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.S)
        if m:
            try:
                data = json.loads(m.group(1))
                # Szukaj ofert w strukturze
                offers = (data.get("offers") or data.get("listings") or
                          data.get("search", {}).get("results") or [])
                if offers:
                    return offers
            except Exception:
                pass
    return []

def _parse_no_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    listings = []

    # N-Online używa różnych klas w zależności od wersji layoutu
    cards = (
        soup.select("article.offer-box") or
        soup.select("div.listing-item") or
        soup.select("[class*='offer'][class*='item']") or
        soup.select("li[id^='offer']") or
        soup.select("div[data-offer-id]")
    )

    if not cards:
        logger.warning("[N-Online] Brak kart ofert — HTML layout nieznany")
        logger.debug("[N-Online] Tytuł strony: %s", soup.title.string if soup.title else "brak")
        return []

    for card in cards:
        try:
            link = card.select_one("a[href*='/oferta/'], a[href*='/offer/']")
            if not link:
                link = card.select_one("a[href]")
            url = link["href"] if link else ""
            if url and not url.startswith("http"):
                url = f"https://www.nieruchomosci-online.pl{url}"

            title_el = card.select_one("h2, h3, [class*='title']")
            title = title_el.get_text(strip=True) if title_el else "Bez tytułu"

            price_el = card.select_one("[class*='price']")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price = None
            digits = re.sub(r"[^\d]", "", price_text)
            if digits and 10_000 <= int(digits) <= 100_000_000:
                price = int(digits)

            area = None
            area_m = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", card.get_text())
            if area_m:
                area = float(area_m.group(1).replace(",", "."))

            rooms = None
            rooms_m = re.search(r"(\d)\s*pok", card.get_text(), re.I)
            if rooms_m:
                rooms = rooms_m.group(1)

            district = None
            loc_el = card.select_one("[class*='location'], [class*='address'], [class*='place']")
            if loc_el:
                loc_text = loc_el.get_text(strip=True)
                district = loc_text.replace("Warszawa", "").replace(",", "").strip() or None

            images = []
            for img in card.select("img")[:4]:
                src = img.get("data-src") or img.get("data-lazy") or img.get("src") or ""
                if src and src.startswith("http") and "placeholder" not in src:
                    images.append(src)

            card_text_lower = card.get_text().lower()
            direct_offer = any(k in card_text_lower for k in [
                "prywatne", "właściciel", "wlasciciel", "bez pośrednika", "bez posrednika"
            ])

            listing = {
                "portal": "nieruchomosci_online",
                "title": title[:200],
                "price": price,
                "area": area,
                "rooms": rooms,
                "district": district,
                "url": url,
                "direct_offer": direct_offer,
                "images": images,
                "source": "nieruchomosci_online",
            }
            if validate_listing(listing):
                listings.append(listing)

        except Exception as e:
            logger.debug("[N-Online] Błąd karty: %s", e)
            continue

    return listings

def search(min_price=None, max_price=None, min_area=None, max_area=None,
           rooms=None, pages=1, direct_only=False, **kwargs) -> list[dict]:
    all_listings = []
    for page in range(1, pages + 1):
        url = build_no_url(min_price, max_price, min_area, max_area, rooms, page)
        logger.info("[N-Online] Strona %d: %s", page, url)
        html = fetch_html(url, portal="nieruchomosci_online")
        if not html:
            break

        items = _extract_from_window_state(html)
        if items:
            listings = []
            for item in items:
                # Normalizuj strukturę window.__STATE__
                price = item.get("price") or item.get("totalPrice")
                area  = item.get("area") or item.get("m2")
                listing = {
                    "portal": "nieruchomosci_online",
                    "title": item.get("title") or item.get("name") or "",
                    "price": int(float(price)) if price else None,
                    "area": float(area) if area else None,
                    "rooms": str(item.get("rooms") or ""),
                    "district": item.get("district") or item.get("quarter") or None,
                    "url": item.get("url") or item.get("link") or "",
                    "direct_offer": str(item.get("advertType", "")).lower() in ("private", "owner"),
                    "images": item.get("photos") or item.get("images") or [],
                    "source": "nieruchomosci_online",
                }
                if validate_listing(listing):
                    listings.append(listing)
            logger.info("[N-Online] window.__STATE__: %d ofert", len(listings))
        else:
            listings = _parse_no_html(html)
            logger.info("[N-Online] HTML: %d ofert", len(listings))

        if not listings:
            break
        all_listings.extend(listings)

    return apply_filters(all_listings, min_price=min_price, max_price=max_price,
                         min_area=min_area, max_area=max_area, rooms=rooms,
                         direct_only=direct_only)