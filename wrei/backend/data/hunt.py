import logging
import json
from psycopg2.extras import Json
from backend.data.connection import get_conn

logger = logging.getLogger(__name__)

def save_hunt_config(config_dict: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM hunt_config")
    cur.execute("INSERT INTO hunt_config (config) VALUES (%s)", (Json(config_dict),))
    conn.commit()
    cur.close()
    conn.close()

def get_hunt_config() -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT config FROM hunt_config LIMIT 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return row[0]
    return {
        "min_price": 300000,
        "max_price": 800000,
        "min_area": 30,
        "max_area": 60,
        "rooms": ["2", "3"],
        "districts": [],
        "portals": ["otodom", "olx"],
        "direct_only": False,
        "min_score_alert": 0.25
    }

def save_hunt_job(job_id: str, status: str, config: dict, 
                  total_scraped: int = 0, total_saved: int = 0, 
                  total_ai: int = 0, error: str = None, portals_counts: dict = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO hunt_jobs (id, status, config, total_scraped, total_saved, total_ai_analyzed, error, portals_counts, started_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (id) DO UPDATE SET
            status = EXCLUDED.status,
            total_scraped = EXCLUDED.total_scraped,
            total_saved = EXCLUDED.total_saved,
            total_ai_analyzed = EXCLUDED.total_ai_analyzed,
            error = EXCLUDED.error,
            portals_counts = EXCLUDED.portals_counts,
            finished_at = CASE WHEN EXCLUDED.status IN ('done', 'error') THEN NOW() ELSE hunt_jobs.finished_at END
    """, (job_id, status, Json(config), total_scraped, total_saved, total_ai, error, Json(portals_counts or {})))
    conn.commit()
    cur.close()
    conn.close()

def get_hunt_job(job_id: str) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM hunt_jobs WHERE id = %s", (job_id,))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(zip(cols, row)) if row else None
