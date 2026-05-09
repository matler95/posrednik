import logging
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_values

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_conn():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "wrei"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
    )


# ---------------------------------------------------------------------------
# Init / migrations
# ---------------------------------------------------------------------------

def init_db():
    """Uruchamia migracje przy starcie aplikacji."""
    migrations_dir = Path(__file__).parent / "migrations"
    conn = get_conn()
    cur = conn.cursor()

    # Tabela śledząca wykonane migracje
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
    else:
        # Fallback — inline schema jeśli brak katalogu migrations
        _create_schema_inline(cur)
        conn.commit()

    # Zarejestruj dostępne portale
    _register_portals(cur, conn)

    cur.close()
    conn.close()
    logger.info("[DB] init_db zakończony")


def _create_schema_inline(cur):
    """Minimalny schemat inline — fallback gdy brak plików migracji."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id SERIAL PRIMARY KEY, portal TEXT, title TEXT, price INT,
            area FLOAT, district TEXT, rooms TEXT, url TEXT UNIQUE,
            price_per_m2 FLOAT, estimated_value FLOAT, score FLOAT,
            direct_offer BOOLEAN DEFAULT FALSE, source TEXT, description TEXT,
            images JSONB DEFAULT '[]', features JSONB DEFAULT '{}',
            floor INT, total_floors INT, year_built INT, heating TEXT,
            condition TEXT, building_type TEXT, ownership TEXT,
            raw_location JSONB DEFAULT '{}', llm_analysis JSONB,
            photo_analysis JSONB, first_seen TIMESTAMP DEFAULT NOW(),
            days_on_market INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS listing_history (
            id SERIAL PRIMARY KEY, listing_url TEXT, portal TEXT, price INT,
            area FLOAT, price_per_m2 FLOAT, score FLOAT, district TEXT,
            rooms INT, condition TEXT, building_type TEXT, floor INT,
            year_built INT, recorded_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS scrape_runs (
            id SERIAL PRIMARY KEY, portal TEXT, pages INT,
            direct_only BOOLEAN, query_url TEXT, status TEXT,
            listings_count INT DEFAULT 0, error_message TEXT,
            started_at TIMESTAMP DEFAULT NOW(), finished_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS market_stats (
            id SERIAL PRIMARY KEY, district TEXT NOT NULL, rooms INT,
            condition TEXT, avg_price_per_m2 FLOAT, median_price_per_m2 FLOAT,
            p25_price_per_m2 FLOAT, p75_price_per_m2 FLOAT,
            sample_count INT DEFAULT 0, updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (district, rooms, condition)
        );
        CREATE TABLE IF NOT EXISTS portals (
            name TEXT PRIMARY KEY, enabled BOOLEAN DEFAULT TRUE,
            last_scraped TIMESTAMP, listings_last_run INT DEFAULT 0,
            error_rate FLOAT DEFAULT 0.0, created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id SERIAL PRIMARY KEY, name TEXT, expression TEXT,
            enabled BOOLEAN DEFAULT TRUE,
            channels JSONB DEFAULT '{"telegram": true}',
            last_triggered TIMESTAMP, trigger_count INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS watchlist (
            id SERIAL PRIMARY KEY, name TEXT NOT NULL, filters JSONB NOT NULL,
            alert_threshold FLOAT DEFAULT 0.15,
            channels JSONB DEFAULT '{"telegram": true}',
            active BOOLEAN DEFAULT TRUE, last_checked TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_listings_score      ON listings(score DESC);
        CREATE INDEX IF NOT EXISTS idx_listings_district   ON listings(district);
        CREATE INDEX IF NOT EXISTS idx_listings_created_at ON listings(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_listing_history_url ON listing_history(listing_url);
        CREATE INDEX IF NOT EXISTS idx_market_stats_lookup ON market_stats(district, rooms, condition);
    """)


def _register_portals(cur, conn):
    from backend.scrapers import AVAILABLE_PORTALS
    for portal in AVAILABLE_PORTALS:
        cur.execute("""
            INSERT INTO portals (name) VALUES (%s)
            ON CONFLICT (name) DO NOTHING
        """, (portal,))
    conn.commit()


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

    # Aktualizuj portal stats
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

    records = []
    for l in listings:
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
        ))

    execute_values(cur, """
        INSERT INTO listings (
            portal, title, price, area, district, rooms, url,
            price_per_m2, estimated_value, score, direct_offer, source,
            description, images, features, floor, total_floors, year_built,
            heating, condition, building_type, ownership, raw_location
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
            days_on_market  = EXTRACT(DAY FROM NOW() - listings.first_seen)::INT,
            updated_at      = NOW()
    """, records)

    saved = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    
    # Faza 2: Snapshot do historii
    try:
        save_listing_history(listings)
    except Exception as e:
        logger.warning(f"Nie udalo sie zapisac listing_history: {e}")
        
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


def get_listings_for_llm_analysis(limit: int = 10) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    # Analizujemy tylko oferty, ktore MOGĄ byc ciekawe (np. score > 0.08) i nie mają analizy
    cur.execute("""
        SELECT * FROM listings
        WHERE llm_analysis IS NULL AND score > 0.08
        ORDER BY score DESC NULLS LAST, created_at DESC
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
    """
    stats = [{"district": ..., "rooms": ..., "condition": ...,
               "avg": ..., "median": ..., "p25": ..., "p75": ..., "count": ...}]
    """
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
    """
    Agreguje aktualne oferty (listings) do tabeli market_stats.
    """
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
        logger.info(f"[DB] Zaktualizowano market_stats dla {len(stats_to_upsert)} grup.")



# ---------------------------------------------------------------------------
# Queries dla dashboardu
# ---------------------------------------------------------------------------

def get_listings(
    limit: int = 100, offset: int = 0,
    min_score: float = None, portal: str = None,
    district: str = None, direct_only: bool = False,
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