import json
import httpx
import re
from backend.scrapers.otodom import extract_json_payload, normalize_listing

url = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/mazowieckie/warszawa/warszawa?search%5Bfilter_float_price%3Ato%5D=430000"
print(f"Pobieram: {url}")
resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"})
payload = extract_json_payload(resp.text)

items = payload.get("props", {}).get("pageProps", {}).get("data", {}).get("searchAds", {}).get("items", [])
print(f"Surowych ofert w JSON: {len(items)}")

for i, item in enumerate(items[:5]):
    norm = normalize_listing(item, url)
    print(f"[{i}] Tytuł: {norm['title'][:30]} | Cena: {norm['price']} | Metraż: {norm['area']}")
