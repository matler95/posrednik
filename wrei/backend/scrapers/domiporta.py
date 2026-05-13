# backend/scrapers/domiporta.py
import json, re, logging
from bs4 import BeautifulSoup
from backend.scraper_utils import apply_filters, fetch_html, validate_listing

logger = logging.getLogger(__name__)
DOMIPORTA_BASE_URL = "https://www.domiporta.pl/mieszkanie/sprzedam/mazowieckie/warszawa"

def available():
    return "domiporta"

def build_domiporta_url(min_price=None, max_price=None, min_area=None,
                         max_area=None, rooms=None, page=1) -> str:
    params = []
    if min_price: params.append(f"cenaOd={min_price}")
    if max_price: params.append(f"cenaDo={max_price}")
    if min_area:  params.append(f"powierzchniaOd={min_area}")
    if max_area:  params.append(f"powierzchniaDo={max_area}")
    if rooms:
        r = str(rooms).split("-")[0].split(",")[0].strip()
        if r.isdigit(): params.append(f"liczbaPokoi={r}")
    if page > 1: params.append(f"PageIndex={page}")
    qs = "&".join(params)
    return f"{DOMIPORTA_BASE_URL}?{qs}" if qs else DOMIPORTA_BASE_URL

def _try_next_data(html: str) -> list[dict]:
    """Próba wyciągnięcia z __NEXT_DATA__ — działa jeśli Domiporta go dodaje."""
    try:
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if not m:
            return []
        payload = json.loads(m.group(1))
        pp = payload.get("props", {}).get("pageProps", {})
        for key in ("listings", "offers", "items"):
            if items := pp.get(key):
                return items
            # zagłębione
            for sub in pp.values():
                if isinstance(sub, dict):
                    if items := sub.get(key) or sub.get("items"):
                        return items
    except Exception:
        pass
    return []

def _parse_html_cards(html: str) -> list[dict]:
    """Fallback: parsowanie kart HTML przez BeautifulSoup."""
    soup = BeautifulSoup(html, "lxml")
    listings = []

    # Domiporta używa <article class="sneaky-link ..."> lub <li class="listing-item">
    cards = (
        soup.select("article.sneaky-link") or
        soup.select("li.listing-item") or
        soup.select("[class*='listing'][class*='item']") or
        soup.select("article[data-id]") or
        soup.select("div.offer-item")
    )

    if not cards:
        logger.warning("[Domiporta] Nie znaleziono kart ogłoszeń — sprawdź selektory")
        # Debug: wylistuj klasy article/li żeby znaleźć właściwy selektor
        for tag in soup.find_all(["article", "li"])[:5]:
            logger.debug("[Domiporta] Tag: %s class=%s", tag.name, tag.get("class"))
        return []

    for card in cards:
        try:
            # URL
            link = card.select_one("a[href*='/mieszkanie/']") or card.select_one("a[href]")
            url = link["href"] if link else ""
            if url and not url.startswith("http"):
                url = f"https://www.domiporta.pl{url}"

            # Tytuł
            title_el = card.select_one("h2, h3, [class*='title'], [class*='name']")
            title = title_el.get_text(strip=True) if title_el else "Bez tytułu"

            # Cena — szukaj liczby z PLN/zł
            price_el = card.select_one("[class*='price'], [class*='cena']")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price = None
            if price_text:
                digits = re.sub(r"[^\d]", "", price_text)
                if digits and 10_000 <= int(digits) <= 100_000_000:
                    price = int(digits)

            # Metraż
            area = None
            area_m = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", card.get_text())
            if area_m:
                area = float(area_m.group(1).replace(",", "."))

            # Pokoje
            rooms_m = re.search(r"(\d)\s*pok", card.get_text(), re.I)
            rooms = rooms_m.group(1) if rooms_m else None

            # Dzielnica — z breadcrumb lub danych karty
            district = None
            loc_el = card.select_one("[class*='location'], [class*='district'], [class*='address']")
            if loc_el:
                loc_text = loc_el.get_text(strip=True)
                # Usuń "Warszawa" żeby zostało samo nazwa dzielnicy
                district = loc_text.replace("Warszawa", "").replace(",", "").strip() or None

            # Bezpośrednia — szukaj "prywatne" lub "właściciel"
            card_text = card.get_text().lower()
            direct_offer = any(k in card_text for k in ["prywatne", "właściciel", "wlasciciel", "bez pośrednika"])

            # Zdjęcia
            images = []
            for img in card.select("img[src], img[data-src]")[:4]:
                src = img.get("data-src") or img.get("src") or ""
                if src and "placeholder" not in src.lower():
                    images.append(src)

            # Cena za m²
            psm = None
            psm_m = re.search(r"(\d[\d\s]+)\s*zł/m", card.get_text())
            if psm_m:
                psm_digits = re.sub(r"\D", "", psm_m.group(1))
                psm = float(psm_digits) if psm_digits else None

            listing = {
                "portal": "domiporta",
                "title": title[:200],
                "price": price,
                "area": area,
                "rooms": rooms,
                "district": district,
                "url": url,
                "direct_offer": direct_offer,
                "price_per_m2": psm,
                "images": images,
                "source": "domiporta",
            }

            if validate_listing(listing):
                listings.append(listing)

        except Exception as e:
            logger.debug("[Domiporta] Błąd parsowania karty: %s", e)
            continue

    return listings

def normalize_listing(item: dict) -> dict | None:
    """Normalizuje rekord z JSON Domiporta."""
    try:
        url = item.get("url") or item.get("relativeUrl")
        if url and not url.startswith("http"):
            url = f"https://www.domiporta.pl{url}"
        
        listing = {
            "portal": "domiporta",
            "title": (item.get("title") or item.get("name") or "Bez tytułu")[:200],
            "price": item.get("price") or item.get("totalPrice"),
            "area": item.get("area") or item.get("squareMeters"),
            "rooms": str(item.get("rooms") or item.get("roomCount") or ""),
            "district": item.get("district") or item.get("location", {}).get("district"),
            "url": url,
            "direct_offer": bool(item.get("isPrivate") or item.get("isDirect")),
            "price_per_m2": item.get("pricePerSquareMeter"),
            "images": [img.get("url") for img in item.get("images", []) if isinstance(img, dict)] or item.get("photos", []),
            "source": "domiporta",
        }
        from backend.scraper_utils import validate_listing
        if validate_listing(listing):
            return listing
    except Exception:
        pass
    return None

def search(min_price=None, max_price=None, min_area=None, max_area=None,
           rooms=None, pages=1, direct_only=False, **kwargs) -> list[dict]:
    all_listings = []
    for page in range(1, pages + 1):
        url = build_domiporta_url(min_price, max_price, min_area, max_area, rooms, page)
        logger.info("[Domiporta] Strona %d: %s", page, url)
        html = fetch_html(url, portal="domiporta")
        if not html:
            break

        # Próba 1: __NEXT_DATA__
        items = _try_next_data(html)
        if items:
            listings = [n for i in items if (n := normalize_listing(i))]
            logger.info("[Domiporta] __NEXT_DATA__: %d ofert", len(listings))
        else:
            # Próba 2: HTML parsing
            listings = _parse_html_cards(html)
            logger.info("[Domiporta] HTML: %d ofert", len(listings))

        if not listings:
            break
        all_listings.extend(listings)

    return apply_filters(all_listings, min_price=min_price, max_price=max_price,
                         min_area=min_area, max_area=max_area, rooms=rooms,
                         direct_only=direct_only)