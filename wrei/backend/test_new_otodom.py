import httpx
import re
import json

url = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/mazowieckie/warszawa/warszawa?priceMax=430000&areaMax=40"
print(f"Testuję NOWY URL: {url}")
h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
r = httpx.get(url, headers=h, follow_redirects=True)

m_json = re.search(r'__NEXT_DATA__.*?(\{.+?\})</script>', r.text, re.S)
if m_json:
    data = json.loads(m_json.group(1))
    items = data.get("props", {}).get("pageProps", {}).get("data", {}).get("searchAds", {}).get("items", [])
    print(f"ZNALEZIONO OFERT: {len(items)}")
    for i, it in enumerate(items[:5]):
        price = it.get('totalPrice',{}).get('value')
        print(f"[{i}] {it.get('title')[:50]}... | CENA: {price} PLN")
else:
    print("Nie znaleziono danych JSON.")
