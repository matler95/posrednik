from backend.scrapers.otodom import build_otodom_url, search
import httpx

url = build_otodom_url(max_price=430000, min_price=300000, max_area=45, min_area=30)
print(f"Testowany URL: {url}")

resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
print(f"Status odpowiedzi: {resp.status_code}")
if "searchAds" in resp.text:
    print("Znaleziono 'searchAds' w HTML.")
else:
    print("Nie znaleziono 'searchAds' w HTML (prawdopodobnie blokada lub inny format).")

results = search(max_price=430000, min_price=300000, max_area=45, min_area=30, pages=1)
print(f"Liczba wynikowych ofert: {len(results)}")
