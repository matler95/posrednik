from backend.scrapers.otodom import search
from backend.main import enrich_listings
from backend.db import save_listings
import json

print("1. Rozpoczynam pobieranie ofert do 430k z Otodom...")
listings = search(max_price=430000, max_area=45, pages=2)
print(f"Pobrano surowych: {len(listings)}")

if listings:
    print("2. Wzbogacam dane (RCN/Score)...")
    enriched = enrich_listings(listings, city_slug="warszawa")
    
    print("3. Zapisuję do bazy danych...")
    count = save_listings(enriched)
    print(f"ZAPISANO/ZAKTUALIZOWANO: {count} ofert.")
    
    # Sprawdźmy jedną konkretną ofertę w bazie po zapisie
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT title, price, area FROM listings WHERE price <= 430000 AND area <= 45 LIMIT 10")
    rows = cur.fetchall()
    print("\nOFERTY W BAZIE PO ZAPISIE (do 430k):")
    for r in rows:
        print(f"- {r[0]} | {r[1]} PLN | {r[2]} m2")
    cur.close(); conn.close()
else:
    print("Brak ofert do zapisu.")
