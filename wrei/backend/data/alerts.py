import logging
from backend.data.connection import get_conn

logger = logging.getLogger(__name__)

def create_price_alert(listing_id: int, alert_type: str, old_value: float = None, new_value: float = None) -> None:
    """Records a triggered alert in the price_alerts table."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO price_alerts (listing_id, alert_type, old_value, new_value, triggered_at)
        VALUES (%s, %s, %s, %s, NOW())
    """, (listing_id, alert_type, old_value, new_value))
    conn.commit()
    cur.close()
    conn.close()

def get_alerts(limit: int = 50) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.*, l.title, l.url, l.price, l.area, l.district, l.score, l.images
        FROM price_alerts a
        JOIN listings l ON a.listing_id = l.id
        ORDER BY a.triggered_at DESC
        LIMIT %s
    """, (limit,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows
