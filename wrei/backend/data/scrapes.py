import logging
from backend.data.connection import get_conn

logger = logging.getLogger(__name__)

def record_scrape_run(
    portal, pages, direct_only, status, listings_count,
    query_url=None, error_message=None,
) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO scrape_runs
                (portal, pages, direct_only, query_url, status, listings_count, error_message, finished_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING id
        """, (portal, pages, direct_only, query_url, status, listings_count, error_message))
        run_id = cur.fetchone()[0]

        if status == "completed":
            cur.execute("""
                UPDATE portals
                SET last_scraped = NOW(), listings_last_run = %s, error_rate = 0.0
                WHERE name = %s
            """, (listings_count, portal))
        elif status == "failed":
            cur.execute("""
                UPDATE portals
                SET error_rate = LEAST(error_rate + 0.1, 1.0)
                WHERE name = %s
            """, (portal,))

        conn.commit()
        return run_id
