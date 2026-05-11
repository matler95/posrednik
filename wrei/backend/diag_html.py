import re
import json

try:
    with open("backend/debug_raw.html", "r") as f:
        html = f.read()
    
    # Szukamy liczby ofert
    m = re.search(r'"totalAds":(\d+)', html)
    total = m.group(1) if m else "nieznana"
    print(f"OTODOM TOTAL ADS: {total}")
    
    # Szukamy czy są jakiekolwiek przedmioty w JSONie
    m_json = re.search(r'__NEXT_DATA__.*?(\{.+?\})</script>', html, re.S)
    if m_json:
        data = json.loads(m_json.group(1))
        items = data.get("props", {}).get("pageProps", {}).get("data", {}).get("searchAds", {}).get("items", [])
        print(f"LICZBA OFERT NA PIERWSZEJ STRONIE: {len(items)}")
        for i, it in enumerate(items[:3]):
            print(f"[{i}] {it.get('title')} | {it.get('totalPrice',{}).get('value')} PLN")
    else:
        print("Nie znaleziono bloku JSON.")
except Exception as e:
    print(f"BŁĄD: {e}")
