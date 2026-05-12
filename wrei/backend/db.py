"""
db.py — Database access layer.

NAPRAWKI:
- Dodano save_listing_score() — było importowane w hunt_manager ale nie istniało
- Poprawiono serializację datetime w get_hunt_listings
- Dodano get_rcn_district_stats dla dashboardu
"""
import logging
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_values
from psycopg2.extras import register_default_jsonb

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_conn():
    conn = psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "wrei"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
    )
    register_default_jsonb(conn)  # JSONB → dict automatycznie
    return conn


# ---------------------------------------------------------------------------
# Init / migrations
# ---------------------------------------------------------------------------

def init_db():
    """Uruchamia migracje przy starcie aplikacji."""
    migrations_dir = Path(__file__).parent / "migrations"
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()

    if migrations_dir.exists():
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            cur.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (sql_file.name,))
            if cur.fetchone():
                continue
            logger.info("[DB] Aplykuję migrację: %s", sql_file.name)
            sql = sql_file.read_text(encoding="utf-8")
            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)", (sql_file.name,)
            )
            conn.commit()
            logger.info("[DB] Migracja %s zakończona", sql_file.name)

    _register_portals(cur, conn)
    cur.close()
    conn.close()
    logger.info("[DB] init_db zakończony")


def _register_portals(cur, conn):
    try:
        from backend.scrapers import AVAILABLE_PORTALS
        for portal in AVAILABLE_PORTALS:
            cur.execute("""
                INSERT INTO portals (name) VALUES (%s)
                ON CONFLICT (name) DO NOTHING
            """, (portal,))
        conn.commit()
    except Exception as e:
        logger.warning("[DB] _register_portals error: %s", e)


# ---------------------------------------------------------------------------
# Scrape runs
# ---------------------------------------------------------------------------

def record_scrape_run(
    portal, pages, direct_only, status, listings_count,
    query_url=None, error_message=None,
) -> int:
    conn = get_conn()
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
    cur.close()
    conn.close()
    return run_id


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

def save_listings(listings: list[dict]):
    if not listings:
        return 0

    conn = get_conn()
    cur = conn.cursor()

    unique_listings = {}
    for l in listings:
        if l.get("url"):
            unique_listings[l["url"]] = l

    records = []
    for l in unique_listings.values():
        records.append((
            l.get("portal"),
            l.get("title"),
            l.get("price"),
            l.get("area"),
            l.get("district"),
            str(l.get("rooms")) if l.get("rooms") is not None else None,
            l.get("url"),
            l.get("price_per_m2"),
            l.get("estimated_value"),
            l.get("score"),
            bool(l.get("direct_offer", False)),
            l.get("source"),
            l.get("description"),
            Json(l.get("images") or []),
            Json(l.get("features") or {}),
            l.get("floor"),
            l.get("total_floors"),
            l.get("year_built"),
            l.get("heating"),
            l.get("condition"),
            l.get("building_type"),
            l.get("ownership"),
            Json(l.get("raw_location") or {}),
            l.get("rcn_benchmark"),
            l.get("transaction_gap"),
            l.get("cagr_5y"),
            l.get("text_score"),
            l.get("photo_score"),
            l.get("city_slug", "warszawa"),
            l.get("lat"),
            l.get("lng"),
        ))

    execute_values(cur, """
        INSERT INTO listings (
            portal, title, price, area, district, rooms, url,
            price_per_m2, estimated_value, score, direct_offer, source,
            description, images, features, floor, total_floors, year_built,
            heating, condition, building_type, ownership, raw_location,
            rcn_benchmark, transaction_gap, cagr_5y, text_score, photo_score,
            city_slug, lat, lng
        ) VALUES %s
        ON CONFLICT (url) DO UPDATE SET
            portal          = EXCLUDED.portal,
            title           = EXCLUDED.title,
            price           = EXCLUDED.price,
            area            = EXCLUDED.area,
            district        = EXCLUDED.district,
            rooms           = EXCLUDED.rooms,
            price_per_m2    = EXCLUDED.price_per_m2,
            estimated_value = EXCLUDED.estimated_value,
            score           = EXCLUDED.score,
            direct_offer    = EXCLUDED.direct_offer,
            source          = EXCLUDED.source,
            description     = EXCLUDED.description,
            images          = EXCLUDED.images,
            features        = EXCLUDED.features,
            floor           = EXCLUDED.floor,
            total_floors    = EXCLUDED.total_floors,
            year_built      = EXCLUDED.year_built,
            heating         = EXCLUDED.heating,
            condition       = EXCLUDED.condition,
            building_type   = EXCLUDED.building_type,
            ownership       = EXCLUDED.ownership,
            raw_location    = EXCLUDED.raw_location,
            rcn_benchmark   = EXCLUDED.rcn_benchmark,
            transaction_gap = EXCLUDED.transaction_gap,
            cagr_5y         = EXCLUDED.cagr_5y,
            text_score      = EXCLUDED.text_score,
            photo_score     = EXCLUDED.photo_score,
            city_slug       = EXCLUDED.city_slug,
            lat             = EXCLUDED.lat,
            lng             = EXCLUDED.lng,
            days_on_market  = EXTRACT(DAY FROM NOW() - listings.first_seen)::INT,
            updated_at      = NOW()
    """, records)

    saved = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    try:
        save_listing_history(list(unique_listings.values()))
    except Exception as e:
        logger.warning("[DB] Nie udało się zapisać listing_history: %s", e)

    return saved


def save_llm_analysis(url: str, analysis: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE listings
        SET llm_analysis = %s, updated_at = NOW()
        WHERE url = %s
    """, (Json(analysis) if analysis else None, url))
    conn.commit()
    cur.close()
    conn.close()


def save_listing_score(listing_id: int, score: float, text_score: float = None) -> None:
    """
    NOWA FUNKCJA — aktualizuje score i text_score po analizie LLM.
    Była importowana w hunt_manager ale nie istniała w db.py.
    """
    conn = get_conn()
    cur = conn.cursor()
    if text_score is not None:
        cur.execute("""
            UPDATE listings
            SET score = %s, text_score = %s, updated_at = NOW()
            WHERE id = %s
        """, (score, text_score, listing_id))
    else:
        cur.execute("""
            UPDATE listings
            SET score = %s, updated_at = NOW()
            WHERE id = %s
        """, (score, listing_id))
    conn.commit()
    cur.close()
    conn.close()


def save_hunt_config(config_dict: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO hunt_config (id, config, updated_at)
        VALUES (1, %s, NOW())
        ON CONFLICT (id) DO UPDATE SET
            config = EXCLUDED.config,
            updated_at = NOW()
    """, (Json(config_dict),))
    conn.commit()
    cur.close()
    conn.close()


def get_hunt_config() -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT config FROM hunt_config WHERE id = 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and row[0]:
        return row[0]
    return {}


def get_hunt_listings(limit: int = 100, offset: int = 0) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        WITH cfg AS (SELECT config FROM hunt_config WHERE id = 1)
        SELECT l.* FROM listings l, cfg
        WHERE
            l.price <= COALESCE((cfg.config->>'max_price')::int, 2147483647)
            AND l.price >= COALESCE((cfg.config->>'min_price')::int, 0)
            AND l.area <= COALESCE((cfg.config->>'max_area')::numeric, 999999)
            AND l.area >= COALESCE((cfg.config->>'min_area')::numeric, 0)
            AND (
                jsonb_array_length(cfg.config->'districts') = 0
                OR l.district = ANY(ARRAY(SELECT jsonb_array_elements_text(cfg.config->'districts')))
            )
            AND (
                jsonb_array_length(cfg.config->'rooms') = 0
                OR l.rooms = ANY(ARRAY(SELECT jsonb_array_elements_text(cfg.config->'rooms')))
            )
            AND (
                (cfg.config->>'direct_only')::boolean = FALSE
                OR l.direct_offer = TRUE
            )
        ORDER BY l.score DESC NULLS LAST, l.created_at DESC
        LIMIT %s OFFSET %s
    """, (limit, offset))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def get_listing_by_id(listing_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM listings WHERE id = %s", (listing_id,))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(zip(cols, row)) if row else None


def get_listings_for_llm_analysis(limit: int = 10) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        WITH cfg AS (SELECT config FROM hunt_config WHERE id = 1)
        SELECT l.* FROM listings l, cfg
        WHERE l.llm_analysis IS NULL
          AND l.price <= COALESCE((cfg.config->>'max_price')::int, 9999999)
          AND l.price >= COALESCE((cfg.config->>'min_price')::int, 0)
          AND l.area <= COALESCE((cfg.config->>'max_area')::numeric, 9999)
          AND l.area >= COALESCE((cfg.config->>'min_area')::numeric, 0)
        ORDER BY
            l.score DESC NULLS LAST
        LIMIT %s
    """, (limit,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def save_listing_history(listings: list[dict]):
    if not listings:
        return

    conn = get_conn()
    cur = conn.cursor()

    records = [(
        l.get("url"),
        l.get("portal"),
        l.get("price"),
        l.get("area"),
        l.get("price_per_m2"),
        l.get("score"),
        l.get("district"),
        _to_int(l.get("rooms")),
        l.get("condition"),
        l.get("building_type"),
        l.get("floor"),
        l.get("year_built"),
    ) for l in listings]

    execute_values(cur, """
        INSERT INTO listing_history
            (listing_url, portal, price, area, price_per_m2, score,
             district, rooms, condition, building_type, floor, year_built)
        VALUES %s
    """, records)

    conn.commit()
    cur.close()
    conn.close()


def _to_int(val) -> int | None:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Market stats
# ---------------------------------------------------------------------------

def upsert_market_stats(stats: list[dict]):
    if not stats:
        return

    conn = get_conn()
    cur = conn.cursor()

    for s in stats:
        cur.execute("""
            INSERT INTO market_stats
                (district, rooms, condition, avg_price_per_m2, median_price_per_m2,
                 p25_price_per_m2, p75_price_per_m2, sample_count, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (district, rooms, condition) DO UPDATE SET
                avg_price_per_m2    = EXCLUDED.avg_price_per_m2,
                median_price_per_m2 = EXCLUDED.median_price_per_m2,
                p25_price_per_m2    = EXCLUDED.p25_price_per_m2,
                p75_price_per_m2    = EXCLUDED.p75_price_per_m2,
                sample_count        = EXCLUDED.sample_count,
                updated_at          = NOW()
        """, (
            s["district"], s.get("rooms"), s.get("condition"),
            s["avg"], s["median"], s["p25"], s["p75"], s["count"],
        ))

    conn.commit()
    cur.close()
    conn.close()


def get_market_stats(district: str = None) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    if district:
        cur.execute(
            "SELECT * FROM market_stats WHERE district = %s ORDER BY rooms, condition",
            (district,)
        )
    else:
        cur.execute("SELECT * FROM market_stats ORDER BY district, rooms, condition")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def generate_market_stats():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COALESCE(district, 'Warszawa') as district,
            CAST(rooms AS integer) as parsed_rooms,
            condition,
            AVG(price_per_m2) as avg_price,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_per_m2) as median_price,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY price_per_m2) as p25_price,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY price_per_m2) as p75_price,
            COUNT(*) as sample_count
        FROM listings
        WHERE price_per_m2 IS NOT NULL AND rooms ~ '^[0-9]+$'
        GROUP BY 1, 2, 3
        HAVING COUNT(*) >= 5
    """)
    rows = cur.fetchall()

    stats_to_upsert = []
    for row in rows:
        stats_to_upsert.append({
            "district": row[0],
            "rooms": _to_int(row[1]),
            "condition": row[2],
            "avg": float(row[3]) if row[3] else None,
            "median": float(row[4]) if row[4] else None,
            "p25": float(row[5]) if row[5] else None,
            "p75": float(row[6]) if row[6] else None,
            "count": int(row[7])
        })
    cur.close()
    conn.close()

    if stats_to_upsert:
        upsert_market_stats(stats_to_upsert)
        logger.info("[DB] Zaktualizowano market_stats dla %d grup.", len(stats_to_upsert))


# ---------------------------------------------------------------------------
# Queries dla dashboardu
# ---------------------------------------------------------------------------

def get_listings(
    limit: int = 100, offset: int = 0,
    min_score: float = None, portal: str = None,
    district: str = None, direct_only: bool = False,
    min_price: int = None, max_price: int = None,
    min_area: float = None, max_area: float = None,
) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()

    where = ["1=1"]
    params = []
    if min_score is not None:
        where.append("score >= %s")
        params.append(min_score)
    if portal:
        where.append("portal = %s")
        params.append(portal)
    if district:
        where.append("district = %s")
        params.append(district)
    if direct_only:
        where.append("direct_offer = TRUE")
    if min_price:
        where.append("price >= %s")
        params.append(min_price)
    if max_price:
        where.append("price <= %s")
        params.append(max_price)
    if min_area:
        where.append("area >= %s")
        params.append(min_area)
    if max_area:
        where.append("area <= %s")
        params.append(max_area)

    params.extend([limit, offset])
    cur.execute(f"""
        SELECT * FROM listings
        WHERE {" AND ".join(where)}
        ORDER BY score DESC NULLS LAST, created_at DESC
        LIMIT %s OFFSET %s
    """, params)

    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def get_listing_price_history(url: str) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT price, price_per_m2, score, recorded_at
        FROM listing_history
        WHERE listing_url = %s
        ORDER BY recorded_at
    """, (url,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Transaction prices (Deweloperuch / RCN)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Geocode cache
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Photo analysis queue
# ---------------------------------------------------------------------------

def get_listings_for_photo_analysis(limit: int = 3) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, url, images, title, district, price, area, rooms
        FROM listings
        WHERE photo_analysis IS NULL
          AND images IS NOT NULL
          AND jsonb_array_length(images) > 0
          AND score > 0.08
        ORDER BY score DESC NULLS LAST
        LIMIT %s
    """, (limit,))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def save_photo_analysis(listing_id: int, analysis: dict) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE listings
        SET photo_analysis = %s, updated_at = NOW()
        WHERE id = %s
    """, (Json(analysis) if analysis else None, listing_id))
    conn.commit()
    cur.close()
    conn.close()