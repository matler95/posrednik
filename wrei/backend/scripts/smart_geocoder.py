import sys
import os
import time
import httpx

# Importy backendu
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from backend.db import get_conn

def geocode_address(address: str):
    """Odpytuje Nominatim o dzielnicę dla adresu w Warszawie."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{address}, Warszawa, Polska",
        "format": "json",
        "addressdetails": 1,
        "limit": 1
    }
    headers = {"User-Agent": "WREI_Geocode_Bot/1.0 (mateusz@example.com)"}
    
    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                addr = data[0].get("address", {})
                # Szukamy dzielnicy w różnych polach Nominatim
                district = addr.get("suburb") or addr.get("neighbourhood") or addr.get("city_district")
                return district
        elif resp.status_code == 429:
            print("Rate limit hit! Sleeping longer...")
            time.sleep(10)
    except Exception as e:
        print(f"Błąd sieci: {e}")
    return None

def smart_geocode():
    print("--- Rozpoczynam INTELIGENTNE GEOKODOWANIE (Nominatim) ---")
    conn = get_conn()
    cur = conn.cursor()
    
    # Pobieramy unikalne adresy bez dzielnicy
    cur.execute("""
        SELECT street_address, COUNT(*) as cnt 
        FROM transaction_prices 
        WHERE district IS NULL AND city_slug = 'warszawa' 
        GROUP BY street_address 
        ORDER BY cnt DESC
    """)
    addresses = cur.fetchall()
    total_to_fix = sum(a[1] for a in addresses)
    print(f"Znaleziono {len(addresses)} unikalnych adresów (łącznie {total_to_fix} rekordów).")
    
    processed = 0
    updated_records = 0
    
    for addr_text, count in addresses:
        if not addr_text or len(addr_text) < 5:
            continue
            
        district = geocode_address(addr_text)
        processed += 1
        
        if district:
            # Mapujemy nazwy Nominatim na standardowe dzielnice Warszawy (proste uproszczenie)
            district = district.replace("dzielnica ", "").strip()
            
            cur.execute("UPDATE transaction_prices SET district = %s WHERE street_address = %s AND district IS NULL", (district, addr_text))
            conn.commit()
            updated_records += count
            print(f"[{processed}/{len(addresses)}] OK: {addr_text} -> {district} (+{count} rekordów)")
        else:
            print(f"[{processed}/{len(addresses)}] Brak wyników dla: {addr_text}")
        
        # Obowiązkowy sleep dla Nominatim (min. 1 sekunda)
        time.sleep(1.2)

    cur.close()
    conn.close()
    print("--- Zakończono geokodowanie. ---")

if __name__ == "__main__":
    smart_geocode()
