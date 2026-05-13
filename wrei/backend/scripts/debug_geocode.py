import sys
import os
import re
import unicodedata

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.db import get_conn
from backend.scrapers.deweloperuch import WARSAW_DISTRICT_PATTERNS, _strip_accents

def debug_geocode():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT street_address, invest_slug FROM transaction_prices WHERE district IS NULL LIMIT 5")
    rows = cur.fetchall()
    
    compiled_patterns = {
        district: [re.compile(p, re.IGNORECASE) for p in patterns]
        for district, patterns in WARSAW_DISTRICT_PATTERNS.items()
    }
    
    for street, slug in rows:
        text = f"{street or ''} {slug or ''}"
        norm = _strip_accents(text)
        print(f"Oryginał: '{text}'")
        print(f"Znormalizowany: '{norm}'")
        
        matches = []
        for dist, regexes in compiled_patterns.items():
            for r in regexes:
                if r.search(norm):
                    matches.append(dist)
        
        print(f"Dopasowania: {matches}")
        print("-" * 20)

if __name__ == "__main__":
    debug_geocode()
