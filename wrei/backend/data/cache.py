import logging
from psycopg2.extras import Json
from backend.data.connection import get_conn

logger = logging.getLogger(__name__)

def get_checkpoint(job_key: str) -> dict | None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT data FROM job_checkpoints WHERE job_key = %s", (job_key,))
        row = cur.fetchone()
        return row[0] if row else None

def save_checkpoint(job_key: str, data: dict) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO job_checkpoints (job_key, data, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (job_key) DO UPDATE SET
                data = EXCLUDED.data,
                updated_at = NOW()
        """, (job_key, Json(data)))
        conn.commit()

def get_geocode_cache(invest_slugs: list[str]) -> dict[str, dict]:
    if not invest_slugs:
        return {}
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT invest_slug, district, lat, lng
            FROM geocode_cache
            WHERE invest_slug = ANY(%s)
        """, (invest_slugs,))
        return {
            row[0]: {"district": row[1], "lat": row[2], "lng": row[3]}
            for row in cur.fetchall()
        }

def save_geocode_cache(invest_slug: str, street_address: str, geo: dict) -> None:
    with get_conn() as conn:
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
