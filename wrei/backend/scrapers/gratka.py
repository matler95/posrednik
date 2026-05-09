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

    # Gratka używa <article class="offer-item"> lub <article class="listing__item">
    # UWAGA: może wymagać korekty selektora po pierwszym uruchomieniu
    cards = soup.find_all("article", class_=re.compile(r"offer-item|listing__item|article-offer"))
    if not cards:
        # fallback — szukaj po data-id
        cards = soup.find_all("article", attrs={"data-id": True})
    if not cards:
        cards = soup.find_all("div", class_=re.compile(r"offer-item|listing__item"))

    for card in cards:
        try:
            # Tytuł
            title_elem = (
                card.find("h2", class_=re.compile(r"title|name|heading"))
                or card.find("h3", class_=re.compile(r"title|name|heading"))
                or card.find("a", class_=re.compile(r"title|name"))
            )
            title = title_elem.get_text(strip=True) if title_elem else "Bez tytułu"

            # URL
            link = card.find("a", href=re.compile(r"/nieruchomosci/"))
            url = link["href"] if link else ""
            if url.startswith("/"):
                url = f"https://gratka.pl{url}"

            # Cena
            price_elem = card.find(class_=re.compile(r"price|cena"))
            price = extract_price(price_elem.get_text(strip=True)) if price_elem else None

            # Metraż
            area = None
            params_elem = card.find(class_=re.compile(r"params|details|features|parameters"))
            if params_elem:
                area = extract_area(params_elem.get_text())
            if area is None:
                area = extract_area(card.get_text())

            # Pokoje
            rooms_val = None
            card_text = card.get_text()
            rooms_match = re.search(r"(\d+)\s*pok", card_text, re.IGNORECASE)
            if rooms_match:
                rooms_val = int(rooms_match.group(1))

            # Dzielnica z lokalizacji
            location_elem = card.find(class_=re.compile(r"location|address|place|lokalizacja"))
            district = "Warszawa"
            if location_elem:
                loc_text = location_elem.get_text(strip=True)
                # "Warszawa, Mokotów" → "Mokotów"
                parts = re.split(r"[,–\-]", loc_text)
                if len(parts) >= 2:
                    district = parts[-1].strip()
                elif parts:
                    district = parts[0].strip()

            # Bezpośredni — brak słów agencja/biuro + sprawdzenie tytułu
            text_lower = card_text.lower()
            direct_offer = (
                "bezpośrednio" in text_lower
                or "właściciel" in text_lower
                or "prywatny" in text_lower
            ) and not any(x in text_lower for x in ["biuro", "agencja", "pośrednik"])

            # Zdjęcia
            images = [img["src"] for img in card.find_all("img", src=True)
                      if "logo" not in img.get("src", "").lower()][:5]

            if price:
                listings.append({
                    "portal": "gratka",
                    "title": title,
                    "price": price,
                    "area": area,
                    "rooms": rooms_val,
                    "district": district,
                    "url": url,
                    "direct_offer": direct_offer,
                    "source": "gratka",
                    "images": images,
                })
        except Exception as e:
            print(f"[Gratka] Błąd parsowania karty: {e}")
            continue

    return listings


def search(
    min_price=None, max_price=None,
    min_area=None, max_area=None,
    rooms=None, pages=1, direct_only=False,
    **kwargs,
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