import logging
from backend.data.connection import get_conn

logger = logging.getLogger(__name__)

def get_geocode_cache(invest_slugs: list[str]) -> dict[str, dict]:
    if not invest_slugs:
        return {}
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT invest_slug, district, lat, lng
        FROM geocode_cache
        WHERE invest_slug = ANY(%s)
    """, (invest_slugs,))
    result = {
        row[0]: {"district": row[1], "lat": row[2], "lng": row[3]}
        for row in cur.fetchall()
    }
    cur.close()
    conn.close()
    return result

def save_geocode_cache(invest_slug: str, street_address: str, geo: dict) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO geocode_cache (invest_slug, street_address, district, lat, lng)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (invest_slug) DO UPDATE SET
            district   = EXCLUDED.district,
            lat        = EXCLUDED.lat,
            lng        = EXCLUDED.lng,
            cached_at  = NOW()
    """, (
        invest_slug,
        street_address,
        geo.get("district"),
        geo.get("lat"),
        geo.get("lng"),
    ))
    conn.commit()
    cur.close()
    conn.close()
