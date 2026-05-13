import asyncio
import logging
from fastapi import APIRouter, Query
from backend.db import get_conn, save_transaction_prices

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/market", tags=["market"])

@router.get("/trend")
async def market_trend(
    city_slug: str = Query("warszawa"),
    district: str = Query(None),
):
    from backend.market.trend_analyzer import get_quarterly_trend, compute_cagr, get_offer_vs_transaction_gap
    return {
        "quarterly_trend": get_quarterly_trend(city_slug, district),
        "cagr_5y": compute_cagr(city_slug, district),
        "offer_vs_transaction_gap": get_offer_vs_transaction_gap(city_slug, district),
    }

@router.get("/districts")
async def market_districts(city_slug: str = Query("warszawa")):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            tp.district,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tp.amount_sqm) AS rcn_median,
            COUNT(tp.id) AS rcn_count,
            AVG(l.price_per_m2) AS offer_avg,
            COUNT(l.id) AS offer_count
        FROM transaction_prices tp
        FULL OUTER JOIN listings l ON l.district = tp.district AND l.city_slug = %s
        WHERE tp.city_slug = %s
          AND tp.district IS NOT NULL
          AND tp.amount_sqm > 1000
        GROUP BY tp.district
        ORDER BY rcn_median DESC NULLS LAST
        LIMIT 20
    """, (city_slug, city_slug))
    rows = cur.fetchall()

    if not rows:
        cur.execute("""
            SELECT district, median_price_per_m2, avg_price_per_m2, sample_count
            FROM market_stats
            WHERE district IS NOT NULL AND rooms IS NULL AND condition IS NULL
            ORDER BY median_price_per_m2 DESC NULLS LAST
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "district": r[0],
                "rcn_median": r[1],
                "offer_avg": r[2],
                "rcn_count": r[3],
                "offer_count": r[3],
                "count": r[3],
                "median": r[1],
                "avg": r[2],
            }
            for r in rows if r[0]
        ]

    cur.close()
    conn.close()
    return [
        {
            "district": r[0],
            "rcn_median": float(r[1]) if r[1] else None,
            "rcn_count": r[2],
            "offer_avg": float(r[3]) if r[3] else None,
            "offer_count": r[4],
            "median": float(r[1]) if r[1] else None,
            "avg": float(r[3]) if r[3] else None,
            "count": r[2],
        }
        for r in rows if r[0]
    ]

@router.get("/rcn-benchmark")
async def rcn_benchmark(
    city_slug: str = Query("warszawa"),
    district: str = Query(None),
    rooms: int = Query(None),
):
    from backend.market.trend_analyzer import get_rcn_benchmark
    return {"benchmark_sqm": get_rcn_benchmark(city_slug, district=district, rooms=rooms)}

from backend.api.schemas import MarketStatsRequestSchema

@router.post("/ingest")
async def market_ingest(city_slug: str = "warszawa", days: int = 30):
    from arq import create_pool
    from arq.connections import RedisSettings
    import os

    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    redis = await create_pool(RedisSettings(host=REDIS_HOST))
    # We use years=0 as a flag for recent ingest
    await redis.enqueue_job('import_rcn_history_task', city_slug, round(days/365, 3))
    await redis.close()
    
    return {"status": "queued", "city_slug": city_slug, "days": days}

@router.post("/ingest-history")
async def market_ingest_history(city_slug: str = "warszawa", years: int = 5):
    from arq import create_pool
    from arq.connections import RedisSettings
    import os

    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    redis = await create_pool(RedisSettings(host=REDIS_HOST))
    await redis.enqueue_job('import_rcn_history_task', city_slug, years)
    await redis.close()
    
    return {"status": "queued", "city_slug": city_slug, "years": years}

@router.post("/generate-stats")
async def market_generate_stats(req: MarketStatsRequestSchema):
    from backend.db import generate_market_stats
    # In production this should be a background task
    asyncio.create_task(asyncio.to_thread(generate_market_stats))
    return {"status": "started", "city_slug": req.city_slug}

@router.get("/rcn-stats")
async def rcn_stats(city_slug: str = Query("warszawa")):
    from backend.scrapers.deweloperuch import get_district_coverage_stats
    return get_district_coverage_stats(city_slug)

@router.post("/geocode-missing")
async def geocode_missing(city_slug: str = Query("warszawa"), limit: int = Query(100)):
    from backend.scrapers.deweloperuch import batch_geocode_missing
    async def _task():
        updated = batch_geocode_missing(city_slug, limit=limit)
        logger.info("[GeoFill] Zaktualizowano %d rekordów", updated)
    asyncio.create_task(_task())
    return {"status": "started", "city_slug": city_slug, "limit": limit}
