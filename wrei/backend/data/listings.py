import logging
from datetime import datetime
from psycopg2.extras import Json, execute_values
from backend.data.connection import get_conn

logger = logging.getLogger(__name__)

def _to_int(val) -> int | None:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None

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
            l.get("preliminary_score"),
        ))

    execute_values(cur, """
        INSERT INTO listings (
            portal, title, price, area, district, rooms, url,
            price_per_m2, estimated_value, score, direct_offer, source,
            description, images, features, floor, total_floors, year_built,
            heating, condition, building_type, ownership, raw_location,
            rcn_benchmark, transaction_gap, cagr_5y, text_score, photo_score,
            city_slug, lat, lng, preliminary_score
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
            preliminary_score = EXCLUDED.preliminary_score,
            score_version   = CASE WHEN listings.price != EXCLUDED.price OR listings.score != EXCLUDED.score THEN listings.score_version + 1 ELSE listings.score_version END,
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
    """, (Json(analysis), url))
    conn.commit()
    cur.close()
    conn.close()

def save_listing_score(listing_id: int, score: float, text_score: float = None) -> None:
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

def get_hunt_listings(limit: int = 100, offset: int = 0) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        WITH cfg AS (SELECT config FROM hunt_config WHERE id = 1)
        SELECT l.* FROM listings l, cfg
        WHERE l.score IS NOT NULL
            AND l.price <= COALESCE((cfg.config->>'max_price')::int, 9999999)
            AND l.price >= COALESCE((cfg.config->>'min_price')::int, 0)
            AND l.area <= COALESCE((cfg.config->>'max_area')::numeric, 999999)
            AND l.area >= COALESCE((cfg.config->>'min_area')::numeric, 0)
            AND (
                jsonb_array_length(cfg.config->'districts') = 0
                OR l.district = ANY(ARRAY(SELECT jsonb_array_elements_text(cfg.config->'districts')))
            )
            AND (
                jsonb_array_length(cfg.config->'rooms') = 0
                OR l.rooms::TEXT = ANY(ARRAY(SELECT jsonb_array_elements_text(cfg.config->'rooms')))
            )
            AND (
                (cfg.config->>'direct_only')::boolean = FALSE
                OR l.direct_offer = TRUE
            )
        ORDER BY l.score DESC NULLS LAST, l.created_at DESC
        LIMIT %s OFFSET %s
    """, (limit, offset))
    
    cols = [d[0] for d in cur.description]
    rows = []
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        rows.append(d)
        
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
          AND (l.llm_error_count IS NULL OR l.llm_error_count < 3)
          AND l.price <= COALESCE((cfg.config->>'max_price')::int, 9999999)
          AND l.price >= COALESCE((cfg.config->>'min_price')::int, 0)
        ORDER BY
            CASE 
                WHEN l.score >= 0.3 THEN 1
                WHEN l.score >= 0.15 THEN 2
                ELSE 3
            END,
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
    cur.execute(f\"\"\"
        SELECT * FROM listings
        WHERE {" AND ".join(where)}
        ORDER BY score DESC NULLS LAST, created_at DESC
        LIMIT %s OFFSET %s
    \"\"\", params)
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

def get_new_listings(hours: int = 24, limit: int = 50) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f\"\"\"
        SELECT * FROM listings
        WHERE created_at >= NOW() - interval '%s hours'
        ORDER BY preliminary_score DESC NULLS LAST, created_at DESC
        LIMIT %s
    \"\"\", (hours, limit))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows

def increment_llm_error_count(listing_id: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE listings
        SET llm_error_count = llm_error_count + 1, updated_at = NOW()
        WHERE id = %s
    """, (listing_id,))
    conn.commit()
    cur.close()
    conn.close()
