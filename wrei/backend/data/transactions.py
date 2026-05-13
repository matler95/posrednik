import logging
from psycopg2.extras import execute_values
from backend.data.connection import get_conn

logger = logging.getLogger(__name__)

def save_transaction_prices(transactions: list[dict]) -> int:
    if not transactions:
        return 0

    with get_conn() as conn:
        cur = conn.cursor()

        seen_ids = set()
        records = []
        for t in transactions:
            rcn_id = t.get("sale_rcn_id")
            if rcn_id and rcn_id not in seen_ids and t.get("amount_sqm"):
                seen_ids.add(rcn_id)
                records.append((
                    rcn_id,
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
                ))

        if not records:
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
        logger.info("[DB] Zapisano %d transakcji RCN.", saved)
        return saved

def update_transaction_district(invest_slug: str, district: str) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE transaction_prices
            SET district = %s
            WHERE invest_slug = %s AND district IS NULL
        """, (district, invest_slug))
        conn.commit()

def get_transactions_without_district(limit: int = 200) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT invest_slug, street_address, city_slug
            FROM transaction_prices
            WHERE district IS NULL AND invest_slug IS NOT NULL
            LIMIT %s
        """, (limit,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
