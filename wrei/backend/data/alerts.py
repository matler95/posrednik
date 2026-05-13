import logging
from psycopg2.extras import Json
from backend.data.connection import get_conn

logger = logging.getLogger(__name__)

def create_price_alert(listing_id: int, alert_type: str, old_value: float = None, new_value: float = None) -> None:
    """Records a triggered alert in the price_alerts table."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO price_alerts (listing_id, alert_type, old_value, new_value, triggered_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (listing_id, alert_type, old_value, new_value))
        conn.commit()

def get_alerts(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT a.*, l.title, l.url, l.price, l.area, l.district, l.score, l.images
            FROM price_alerts a
            JOIN listings l ON a.listing_id = l.id
            ORDER BY a.triggered_at DESC
            LIMIT %s
        """, (limit,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def get_watchlist(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM watchlist ORDER BY id LIMIT %s", (limit,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def create_watchlist_item(data: dict) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO watchlist (name, condition_expr, min_score, city_slug, filters, channels, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data.get("name"),
            data.get("condition_expr", ""),
            data.get("min_score", 0.15),
            data.get("city_slug", "warszawa"),
            Json(data.get("filters", {})),
            Json(data.get("channels", {})),
            data.get("active", True),
        ))
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id

def delete_watchlist_item(item_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM watchlist WHERE id = %s", (item_id,))
        conn.commit()
        return cur.rowcount > 0
