import re
from bs4 import BeautifulSoup
from backend.scraper_utils import apply_filters, build_query_string, fetch_html

GRATKA_BASE_URL = "https://gratka.pl/nieruchomosci/mieszkania/warszawa"


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

    # Gratka often uses article tags for offers
    cards = soup.find_all("article")
    for card in cards:
        try:
            # URL i Tytuł
            link = card.find("a", href=re.compile(r"/nieruchomosci/"))
            if not link: continue
            url = link["href"]
            if url.startswith("/"): url = f"https://gratka.pl{url}"
            title = link.get_text(strip=True)

            # Cena
            price_elem = card.find(class_=re.compile(r"price|cena"))
            price_text = price_elem.get_text(strip=True) if price_elem else ""
            price = extract_price(price_text)

            # Metraż
            area = extract_area(card.get_text())

            if price:
                listings.append({
                    "portal": "gratka",
                    "title": title,
                    "price": price,
                    "area": area,
                    "district": "Warszawa",
                    "url": url,
                    "source": "gratka",
                })
        except:
            continue

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
        html = fetch_html(url)
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