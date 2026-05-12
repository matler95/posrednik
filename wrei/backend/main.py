"""
WREI Backend — FastAPI application.
Celowane polowanie na nieruchomości z AI scoring.

NAPRAWKI v2.2:
- /market/districts: spójne nazwy pól (rcn_median, offer_avg, count)
- /hunt/results: zwraca score_components dla UI breakdown
- /hunt/status: fix job.total_found → job.total_scraped (było w v2.1, upewniamy się)
- /market/rcn-stats: endpoint do monitorowania jakości geocodingu
- startup: scheduler + initial RCN load
"""
import asyncio
import logging
import os
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.db import (
    get_hunt_config, get_hunt_listings, get_listing_by_id,
    get_listing_price_history, get_listings, init_db, save_hunt_config,
    get_conn,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="WREI — Real Estate AI Hunter", version="2.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# backend/main.py — w startup()
@app.on_event("startup")
async def startup():
    init_db()
    
    # Generuj market_stats jeśli puste ale mamy dane
    try:
        from backend.db import get_conn, generate_market_stats
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM market_stats")
        ms_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM listings")
        l_count = cur.fetchone()[0]
        cur.close(); conn.close()
        
        if ms_count == 0 and l_count > 10:
            logger.info("[Startup] Generuję market_stats...")
            await asyncio.get_event_loop().run_in_executor(None, generate_market_stats)
    except Exception as e:
        logger.warning("[Startup] market_stats init: %s", e)
    
    asyncio.create_task(_llm_queue_loop())
    try:
        from backend.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning("[Startup] Scheduler error: %s", e)
    logger.info("[WREI] Backend v2.2 uruchomiony.")


async def _llm_queue_loop():
    """Tło: przetwarza kolejkę LLM co 60s jeśli nie ma aktywnego joba."""
    while True:
        await asyncio.sleep(60)
        try:
            from backend.hunt_manager import hunt_manager
            job = hunt_manager.current_job
            if job and job.status not in ("done", "error"):
                continue
            from backend.db import get_listings_for_llm_analysis, save_llm_analysis
            from backend.nlp.llm_scorer import analyze_listing_with_llm
            listings = get_listings_for_llm_analysis(limit=5)
            for listing in listings:
                analysis = await analyze_listing_with_llm(listing)
                if analysis and "error" not in analysis:
                    save_llm_analysis(listing["url"], analysis)
                await asyncio.sleep(2)
        except Exception as e:
            logger.debug("[LLM loop] %s", e)


# ─── Hunt endpoints ───────────────────────────────────────────────────────────

@app.post("/hunt/start")
async def hunt_start(body: dict):
    from backend.hunt_manager import hunt_manager
    config = body.get("config") or await _get_config_dict()
    if body.get("save", True):
        save_hunt_config(config)
    job = await hunt_manager.start_job(config)
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stream_url": f"/hunt/stream/{job.job_id}",
    }


@app.get("/hunt/stream/{job_id}")
async def hunt_stream(job_id: str):
    from backend.hunt_manager import hunt_manager, stream_job_events
    job = hunt_manager.current_job
    if not job or job.job_id != job_id:
        raise HTTPException(status_code=404, detail="Job nie istnieje lub wygasł.")
    return StreamingResponse(
        stream_job_events(job),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/hunt/status")
async def hunt_status():
    """Status aktualnego/ostatniego joba. FIX: total_scraped (nie total_found)."""
    from backend.hunt_manager import hunt_manager

    cfg = get_hunt_config()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM listings")
    total = cur.fetchone()[0]
    cur.execute("SELECT MAX(finished_at) FROM scrape_runs WHERE status = 'completed'")
    last_run = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM listings WHERE score >= 0.25")
    opportunities = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM listings WHERE llm_analysis IS NULL AND score > 0.08")
    pending_ai = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM transaction_prices")
    rcn_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM transaction_prices WHERE district IS NOT NULL")
    rcn_with_district = cur.fetchone()[0]
    cur.close()
    conn.close()

    job = hunt_manager.current_job
    active_job_data = None
    if job:
        active_job_data = {
            "job_id": job.job_id,
            "status": job.status,
            "total_scraped": job.total_scraped,   # FIX: nie total_found
            "total_saved": job.total_saved,
            "total_ai_analyzed": job.total_ai_analyzed,
            "portals_counts": job.portals_counts,
            "elapsed_s": round(job.finished_at - job.started_at, 1) if job.finished_at else None,
            "error": job.error,
        }

    return {
        "config": cfg,
        "last_run": last_run.isoformat() if last_run else None,
        "total_listings": total,
        "opportunities": opportunities,
        "pending_ai": pending_ai,
        "rcn_transactions": rcn_count,
        "rcn_district_coverage": round(rcn_with_district / rcn_count * 100, 1) if rcn_count > 0 else 0,
        "active_job": active_job_data,
    }


@app.get("/hunt/results")
async def hunt_results(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_score: float = Query(None),
    sort_by: str = Query("score"),
    direct_only: bool = Query(False),
    district: str = Query(None),
):
    """
    Wyniki polowania — oferty pasujące do zapisanego configu.
    Zwraca score_components dla UI breakdown.
    """
    listings = get_hunt_listings(limit=limit, offset=offset)

    # Dodatkowe filtry
    if min_score is not None:
        listings = [l for l in listings if (l.get("score") or 0) >= min_score]
    if direct_only:
        listings = [l for l in listings if l.get("direct_offer")]
    if district:
        listings = [l for l in listings if l.get("district") == district]

    # Sortowanie
    sort_fns = {
        "score": lambda x: -(x.get("score") or 0),
        "price": lambda x: x.get("price") or 999_999_999,
        "price_per_m2": lambda x: x.get("price_per_m2") or 999_999_999,
        "date": lambda x: str(x.get("created_at") or ""),
        "gap": lambda x: -(x.get("transaction_gap") or -99),
    }
    fn = sort_fns.get(sort_by, sort_fns["score"])
    listings.sort(key=fn)

    return {
        "count": len(listings),
        "config": get_hunt_config(),
        "listings": [_serialize(l) for l in listings],
    }


# ─── Listings endpoints ───────────────────────────────────────────────────────

@app.get("/listings")
async def listings_endpoint(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_score: float = Query(None),
    portal: str = Query(None),
    district: str = Query(None),
    direct_only: bool = Query(False),
    min_price: int = Query(None),
    max_price: int = Query(None),
    min_area: float = Query(None),
    max_area: float = Query(None),
):
    rows = get_listings(
        limit=limit, offset=offset, min_score=min_score,
        portal=portal, district=district, direct_only=direct_only,
        min_price=min_price, max_price=max_price,
        min_area=min_area, max_area=max_area,
    )
    return {"count": len(rows), "listings": [_serialize(r) for r in rows]}


@app.get("/listings/{listing_id}")
async def listing_detail(listing_id: int):
    listing = get_listing_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    history = get_listing_price_history(listing.get("url", ""))
    return {**_serialize(listing), "price_history": [_serialize(h) for h in history]}


@app.post("/listings/{listing_id}/analyze")
async def trigger_ai_analysis(listing_id: int):
    from backend.db import save_llm_analysis
    from backend.nlp.llm_scorer import analyze_listing_with_llm
    listing = get_listing_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    analysis = await analyze_listing_with_llm(listing)
    if analysis:
        save_llm_analysis(listing["url"], analysis)
        return {"status": "done", "analysis": analysis}
    return {"status": "error", "message": "Analiza nie powiodła się (sprawdź Ollama)"}


# ─── Config endpoints ─────────────────────────────────────────────────────────

@app.get("/get-hunt-config")
async def get_config():
    cfg = get_hunt_config()
    defaults = {
        "min_price": 0, "max_price": 430000,
        "min_area": 0, "max_area": 45,
        "city_slug": "warszawa", "districts": [], "rooms": [],
        "portals": ["otodom", "olx"], "direct_only": False,
        "min_score_alert": 0.25, "pages": 3,
    }
    for k, v in defaults.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


@app.post("/set-hunt-config")
async def set_config(config: dict):
    save_hunt_config(config)
    return {"status": "saved"}


async def _get_config_dict() -> dict:
    return get_hunt_config()


# ─── Market endpoints ─────────────────────────────────────────────────────────

@app.get("/market/trend")
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


@app.get("/market/districts")
async def market_districts(city_slug: str = Query("warszawa")):
    """
    Zestawienie dzielnicowe: RCN mediana + ceny ofertowe.
    FIX: spójne nazwy pól → rcn_median, offer_avg, rcn_count, offer_count, count
    """
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
        # Fallback: market_stats jeśli brak RCN
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
            # aliasy dla kompatybilności wstecznej
            "median": float(r[1]) if r[1] else None,
            "avg": float(r[3]) if r[3] else None,
            "count": r[2],
        }
        for r in rows if r[0]
    ]


@app.get("/market/rcn-benchmark")
async def rcn_benchmark(
    city_slug: str = Query("warszawa"),
    district: str = Query(None),
    rooms: int = Query(None),
):
    from backend.market.trend_analyzer import get_rcn_benchmark
    return {"benchmark_sqm": get_rcn_benchmark(city_slug, district=district, rooms=rooms)}


@app.post("/market/ingest")
async def market_ingest(city_slug: str = Query("warszawa"), days: int = Query(30)):
    from backend.scrapers.deweloperuch import fetch_recent
    from backend.db import save_transaction_prices

    async def _task():
        data = fetch_recent(city_slug, days=days)
        saved = save_transaction_prices(data)
        logger.info("[Ingest] Zapisano %d transakcji dla %s", saved, city_slug)

    asyncio.create_task(_task())
    return {"status": "started", "city_slug": city_slug, "days": days}


@app.post("/market/ingest-history")
async def market_ingest_history(city_slug: str = Query("warszawa"), years: int = Query(5)):
    from backend.scrapers.deweloperuch import fetch_historical
    from backend.db import save_transaction_prices

    async def _task():
        data = fetch_historical(city_slug, years=years)
        saved = save_transaction_prices(data)
        logger.info("[Ingest-history] Zapisano %d transakcji historycznych dla %s", saved, city_slug)

    asyncio.create_task(_task())
    return {"status": "started", "city_slug": city_slug, "years": years, "note": "Może trwać kilka minut"}


@app.get("/market/rcn-stats")
async def rcn_stats(city_slug: str = Query("warszawa")):
    """Statystyki jakości danych RCN — pokrycie district, top dzielnice."""
    from backend.scrapers.deweloperuch import get_district_coverage_stats
    return get_district_coverage_stats(city_slug)


@app.post("/market/geocode-missing")
async def geocode_missing(city_slug: str = Query("warszawa"), limit: int = Query(100)):
    """Uruchamia batch geocoding dla rekordów bez dzielnicy."""
    from backend.scrapers.deweloperuch import batch_geocode_missing

    async def _task():
        updated = batch_geocode_missing(city_slug, limit=limit)
        logger.info("[GeoFill] Zaktualizowano %d rekordów", updated)

    asyncio.create_task(_task())
    return {"status": "started", "city_slug": city_slug, "limit": limit}


# ─── Stats / health ───────────────────────────────────────────────────────────

@app.get("/stats")
async def stats():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM listings")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM listings WHERE llm_analysis IS NULL AND score > 0.08")
    pending_llm = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM listings WHERE score >= 0.25")
    opportunities = cur.fetchone()[0]
    cur.execute("SELECT portal, COUNT(*) FROM listings GROUP BY portal ORDER BY COUNT(*) DESC")
    by_portal = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT COUNT(*) FROM transaction_prices")
    rcn_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM transaction_prices WHERE district IS NOT NULL")
    rcn_geocoded = cur.fetchone()[0]
    cur.close()
    conn.close()
    return {
        "total": total,
        "opportunities": opportunities,
        "pending_llm": pending_llm,
        "by_portal": by_portal,
        "rcn_total": rcn_total,
        "rcn_geocoded": rcn_geocoded,
        "rcn_coverage_pct": round(rcn_geocoded / rcn_total * 100, 1) if rcn_total > 0 else 0,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.2"}


# ─── Legacy compat ────────────────────────────────────────────────────────────

@app.post("/run-crawl")
async def run_crawl_legacy(portals: str = Query(None), pages: int = Query(3)):
    cfg = get_hunt_config()
    if portals:
        cfg["portals"] = [p.strip() for p in portals.split(",")]
    cfg["pages"] = pages
    from backend.hunt_manager import hunt_manager
    job = await hunt_manager.start_job(cfg)
    return {"status": "started", "job_id": job.job_id}


@app.get("/hunt/listings")
async def hunt_listings_legacy(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = get_hunt_listings(limit=limit, offset=offset)
    return {"count": len(rows), "listings": [_serialize(r) for r in rows]}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _serialize(obj: dict) -> dict:
    """Serializuje datetime i Decimal do JSON-friendly typów."""
    out = {}
    for k, v in obj.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out