from backend.scraper_utils import validate_listing
import re
from bs4 import BeautifulSoup
from backend.scraper_utils import apply_filters, build_query_string, fetch_html
from backend.http_client import fetch_html_with_session
import logging

GRATKA_BASE_URL = "https://gratka.pl/nieruchomosci/mieszkania/warszawa"

logger = logging.getLogger(__name__)

def available():
    return "gratka"


def build_gratka_url(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, direct_only=False, page=1,
) -> str:
    params = {}
    if min_price is not None:
        params["cena-od"] = str(min_price)
    if max_price is not None:
        params["cena-do"] = str(max_price)
    if min_area is not None:
        params["powierzchnia-od"] = str(min_area)
    if max_area is not None:
        params["powierzchnia-do"] = str(max_area)
    if rooms:
        # Gratka: liczba-pokoi=2 lub liczba-pokoi=3
        rooms_str = str(rooms).split("-")[0].split(",")[0].strip()
        if rooms_str.isdigit():
            params["liczba-pokoi"] = rooms_str
    if page > 1:
        params["page"] = str(page)
    if not params:
        return GRATKA_BASE_URL
    return f"{GRATKA_BASE_URL}?{build_query_string(params)}"


def extract_price(text: str) -> int | None:
    text = text.replace("\xa0", "").replace(" ", "").replace("zł", "").strip()
    if any(x in text.lower() for x in ["negocj", "zapytaj", "dowyceny"]):
        return None
    match = re.search(r"(\d+)", text.replace(" ", ""))
    if match:
        return int(re.sub(r"\D", "", text))
    return None


def extract_area(text: str) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", text, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def extract_listings_from_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    listings = []

    # Gratka: karty mają data-id lub data-listing-id
    cards = (
        soup.select("article[data-listing-id]") or
        soup.select("article[data-id]") or
        soup.select("div[class*='listing-item']") or
        soup.select("article.offer")
    )

    for card in cards:
        try:
            link = card.select_one("a[href*='/nieruchomosci/']")
            if not link: continue
            url = link["href"]
            if not url.startswith("http"):
                url = f"https://gratka.pl{url}"

            title_el = card.select_one("h2, h3, [class*='title']")
            title = title_el.get_text(strip=True) if title_el else "Bez tytułu"

            # Cena: szukaj span z atrybutem data lub klasą price
            price_el = (card.select_one("[data-price]") or
                       card.select_one("[class*='price']"))
            price = None
            if price_el:
                raw = price_el.get("data-price") or price_el.get_text(strip=True)
                digits = re.sub(r"[^\d]", "", raw)
                if digits and 10_000 <= int(digits) <= 100_000_000:
                    price = int(digits)

            area = None
            area_m = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", card.get_text())
            if area_m:
                area = float(area_m.group(1).replace(",", "."))

            listing = {
                "portal": "gratka",
                "title": title[:200],
                "price": price,
                "area": area,
                "district": None,
                "url": url,
                "source": "gratka",
            }
            if validate_listing(listing):
                listings.append(listing)
        except Exception as e:
            logger.debug("[Gratka] Błąd karty: %s", e)

    if not listings:
        logger.warning("[Gratka] 0 ofert — możliwy 403 lub zmiana struktury HTML")
        for art in soup.find_all("article")[:3]:
            logger.debug("[Gratka] Klasy article: %s", art.get("class"))

    return listings


def search(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=1, direct_only=False,
    district=None, **kwargs,
) -> list[dict]:
    all_listings = []
    for page in range(1, pages + 1):
        url = build_gratka_url(
            min_price=min_price, max_price=max_price,
            min_area=min_area, max_area=max_area,
            rooms=rooms, direct_only=direct_only, page=page,
        )
        print(f"[Gratka] Strona {page}: {url}")
        html = fetch_html_with_session(
            url,
            homepage_url="https://www.gratka.pl",  # lub gratka.pl
            portal="gratka",
)

        if not html:
            break
        listings = extract_listings_from_html(html)
        print(f"[Gratka] Znaleziono {len(listings)} ofert na stronie {page}")
        if not listings:
            break
        all_listings.extend(listings)

    return apply_filters(
        all_listings,
        min_price=min_price, max_price=max_price,
        min_area=min_area, max_area=max_area,
        rooms=rooms, direct_only=direct_only,
    )