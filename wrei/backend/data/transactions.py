import logging
from psycopg2.extras import execute_values
from backend.data.connection import get_conn

logger = logging.getLogger(__name__)

def save_transaction_prices(transactions: list[dict]) -> int:
    if not transactions:
        return 0

    conn = get_conn()
    cur = conn.cursor()

    records = [
        (
            t["sale_rcn_id"],
            t["city"],
            t["city_slug"],
            t.get("street_address"),
            t.get("invest_slug"),
            t.get("district"),
            t.get("amount"),
            t.get("amount_sqm"),
            t.get("size"),
            t.get("rooms_number"),
            t.get("floor_number"),
            t.get("creation_date"),
            t.get("year"),
            t.get("quarter"),
            t.get("month"),
            bool(t.get("is_flipped", False)),
        )
        for t in transactions
        if t.get("sale_rcn_id") and t.get("amount_sqm")
    ]

    if not records:
        cur.close()
        conn.close()
        return 0

    execute_values(cur, """
        INSERT INTO transaction_prices
            (sale_rcn_id, city, city_slug, street_address, invest_slug,
             district, amount, amount_sqm, size, rooms_number, floor_number,
             creation_date, year, quarter, month, is_flipped)
        VALUES %s
        ON CONFLICT (sale_rcn_id) DO UPDATE SET
            district       = COALESCE(EXCLUDED.district, transaction_prices.district),
            street_address = COALESCE(EXCLUDED.street_address, transaction_prices.street_address),
            scraped_at     = NOW()
    """, records)

    saved = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    logger.info("[DB] Zapisano %d transakcji RCN.", saved)
    return saved

def update_transaction_district(invest_slug: str, district: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE transaction_prices
        SET district = %s
        WHERE invest_slug = %s AND district IS NULL
    """, (district, invest_slug))
    conn.commit()
    cur.close()
    conn.close()

def get_transactions_without_district(limit: int = 200) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT invest_slug, street_address, city_slug
        FROM transaction_prices
        WHERE district IS NULL AND invest_slug IS NOT NULL
        LIMIT %s
    """, (limit,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows
