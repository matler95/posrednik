import sys
import os
import re
import unicodedata

# Dodajemy katalog nadrzędny do path, aby móc importować moduły backendu
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.db import get_conn
from backend.scrapers.deweloperuch import WARSAW_DISTRICT_PATTERNS, _strip_accents

def turbo_geocode():
    print("--- Rozpoczynam TURBO GEOKODOWANIE ---")
    
    conn = get_conn()
    cur = conn.cursor()
    
    # Pobieramy rekordy bez dzielnicy
    cur.execute("SELECT id, street_address, invest_slug FROM transaction_prices WHERE district IS NULL AND city_slug = 'warszawa'")
    pending = cur.fetchall()
    print(f"Znaleziono {len(pending)} rekordów do geokodowania.")
    
    updated = 0
    updates = []
    
    # Przygotowujemy kompilowane regexy
    compiled_patterns = {
        district: [re.compile(p, re.IGNORECASE) for p in patterns]
        for district, patterns in WARSAW_DISTRICT_PATTERNS.items()
    }
    
    for row_id, street, slug in pending:
        text_to_check = f"{street or ''} {slug or ''}"
        text_normalized = _strip_accents(text_to_check)
        
        found_district = None
        for district, regexes in compiled_patterns.items():
            if any(r.search(text_normalized) for r in regexes):
                found_district = district
                break
        
        if found_district:
            updates.append((found_district, row_id))
            updated += 1
            
        # Wykonujemy batch update co 1000 rekordów
        if len(updates) >= 1000:
            cur.executemany("UPDATE transaction_prices SET district = %s WHERE id = %s", updates)
            conn.commit()
            updates = []
            print(f"Postęp: {updated}/{len(pending)}...")

    # Końcówka batcha
    if updates:
        cur.executemany("UPDATE transaction_prices SET district = %s WHERE id = %s", updates)
        conn.commit()

    cur.close()
    conn.close()
    print(f"--- ZAKOŃCZONO. Zaktualizowano {updated} rekordów. ---")

if __name__ == "__main__":
    turbo_geocode()
