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

@router.post("/ingest")
async def market_ingest(city_slug: str = Query("warszawa"), days: int = Query(30)):
    from backend.scrapers.deweloperuch import fetch_recent
    async def _task():
        data = fetch_recent(city_slug, days=days)
        saved = save_transaction_prices(data)
        logger.info("[Ingest] Zapisano %d transakcji dla %s", saved, city_slug)
    asyncio.create_task(_task())
    return {"status": "started", "city_slug": city_slug, "days": days}

@router.post("/ingest-history")
async def market_ingest_history(city_slug: str = Query("warszawa"), years: int = Query(5)):
    from backend.scrapers.deweloperuch import fetch_historical
    async def _task():
        data = fetch_historical(city_slug, years=years)
        saved = save_transaction_prices(data)
        logger.info("[Ingest-history] Zapisano %d transakcji historycznych dla %s", saved, city_slug)
    asyncio.create_task(_task())
    return {"status": "started", "city_slug": city_slug, "years": years, "note": "Może trwać kilka minut"}

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
