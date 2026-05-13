import logging
from backend.data.connection import get_conn

logger = logging.getLogger(__name__)

def _to_int(val) -> int | None:
    if val is None: return None
    try: return int(val)
    except (ValueError, TypeError): return None

def upsert_market_stats(stats: list[dict]):
    with get_conn() as conn:
        cur = conn.cursor()
        for s in stats:
            cur.execute("""
                INSERT INTO market_stats (district, rooms, condition, avg_price_per_m2, median_price_per_m2, sample_count, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (district, rooms, condition) DO UPDATE SET
                    avg_price_per_m2 = EXCLUDED.avg_price_per_m2,
                    median_price_per_m2 = EXCLUDED.median_price_per_m2,
                    sample_count = EXCLUDED.sample_count,
                    updated_at = NOW()
            """, (s['district'], s.get('rooms'), s.get('condition'), s['avg'], s['median'], s['count']))
        conn.commit()

def get_market_stats(district: str = None) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        if district:
            cur.execute("SELECT * FROM market_stats WHERE district = %s ORDER BY rooms NULLS FIRST", (district,))
        else:
            cur.execute("SELECT * FROM market_stats ORDER BY district, rooms NULLS FIRST")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def generate_market_stats():
    """
    Agreguje dane rynkowe, priorytetyzując ceny transakcyjne (RCN) nad ofertowymi.
    Zapisuje wyniki w tabeli market_stats.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        
        # 1. Pobieramy statystyki z transakcji RCN (prawdziwe ceny sprzedaży)
        # Bierzemy dane z ostatnich 5 lat dla lepszego pokrycia dzielnic
        cur.execute("""
            SELECT 
                district, 
                NULL as rooms, 
                AVG(amount_sqm) as avg_price,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amount_sqm) as median_price,
                COUNT(*) as sample_count
            FROM transaction_prices
            WHERE amount_sqm > 2000 
              AND district IS NOT NULL
              AND creation_date > NOW() - INTERVAL '5 years'
            GROUP BY district
            HAVING COUNT(*) >= 5
        """)
        rcn_rows = cur.fetchall()
        
        stats = []
        seen_districts = set()
        
        for r in rcn_rows:
            district = r[0]
            stats.append({
                'district': district,
                'rooms': None,
                'condition': None,
                'avg': float(r[2]),
                'median': float(r[3]),
                'count': int(r[4])
            })
            seen_districts.add(district)
        
        # 2. Dla dzielnic, których NIE MA w RCN, robimy fallback do cen ofertowych (listings)
        cur.execute("""
            SELECT 
                district, 
                AVG(price_per_m2) as avg_price,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_per_m2) as median_price,
                COUNT(*) as sample_count
            FROM listings
            WHERE price_per_m2 > 0 AND district IS NOT NULL
            GROUP BY district
            HAVING COUNT(*) >= 3
        """)
        listing_rows = cur.fetchall()
        
        for r in listing_rows:
            district = r[0]
            if district not in seen_districts:
                stats.append({
                    'district': district,
                    'rooms': None,
                    'condition': None,
                    'avg': float(r[1]),
                    'median': float(r[2]),
                    'count': int(r[3])
                })
        
        upsert_market_stats(stats)
        logger.info("[Stats] Zaktualizowano statystyki rynkowe (%d dzielnic). RCN: %d", len(stats), len(seen_districts))
