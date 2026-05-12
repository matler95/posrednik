import logging
from backend.data.connection import get_conn

logger = logging.getLogger(__name__)

def _to_int(val) -> int | None:
    if val is None: return None
    try: return int(val)
    except (ValueError, TypeError): return None

def upsert_market_stats(stats: list[dict]):
    conn = get_conn()
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
    cur.close()
    conn.close()

def get_market_stats(district: str = None) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    if district:
        cur.execute("SELECT * FROM market_stats WHERE district = %s ORDER BY rooms NULLS FIRST", (district,))
    else:
        cur.execute("SELECT * FROM market_stats ORDER BY district, rooms NULLS FIRST")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows

def generate_market_stats():
    """Agreguje dane z listings i zapisuje w market_stats."""
    conn = get_conn()
    cur = conn.cursor()
    
    # 1. Statystyki per dzielnica
    cur.execute("""
        SELECT 
            district, 
            NULL as rooms, 
            NULL as condition,
            AVG(price_per_m2) as avg_price,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_per_m2) as median_price,
            COUNT(*) as sample_count
        FROM listings
        WHERE price_per_m2 > 0 AND district IS NOT NULL
        GROUP BY district
        HAVING COUNT(*) >= 3
    """)
    rows = cur.fetchall()
    
    stats = []
    for r in rows:
        stats.append({
            'district': r[0],
            'rooms': r[1],
            'condition': r[2],
            'avg': float(r[3]),
            'median': float(r[4]),
            'count': int(r[5])
        })
    
    upsert_market_stats(stats)
    logger.info("[Stats] Wygenerowano statystyki dla %d dzielnic.", len(stats))
    cur.close()
    conn.close()
