"""
WREI Backend — FastAPI application.
Celowane polowanie na nieruchomości z AI scoring.
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

app = FastAPI(title="WREI — Real Estate AI Hunter", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    init_db()
    # Start background LLM queue processor
    asyncio.create_task(_llm_queue_loop())
    logger.info("[WREI] Backend uruchomiony.")


async def _llm_queue_loop():
    """Tło: przetwarza kolejkę LLM co 60s jeśli nie ma aktywnego joba."""
    while True:
        await asyncio.sleep(60)
        try:
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
    """
    Uruchamia nowe polowanie z podaną konfiguracją.
    Zwraca job_id do śledzenia przez SSE.
    """
    from backend.hunt_manager import hunt_manager

    config = body.get("config") or await _get_config_dict()
    # Zapisz config jeśli podany
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
    """
    SSE endpoint — streamuje progress aktywnego joba.
    Frontend łączy się przez EventSource.
    """
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
        },
    )


@app.get("/hunt/status")
async def hunt_status():
    """Status aktualnego/ostatniego joba."""
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
    cur.close()
    conn.close()

    job = hunt_manager.current_job
    return {
        "config": cfg,
        "last_run": last_run,
        "total_listings": total,
        "opportunities": opportunities,
        "pending_ai": pending_ai,
        "active_job": {
            "job_id": job.job_id,
            "status": job.status,
            "total_found": job.total_found,
            "total_saved": job.total_saved,
            "portals_counts": job.portals_counts,
        } if job else None,
    }


@app.get("/hunt/results")
async def hunt_results(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_score: float = Query(None),
    sort_by: str = Query("score"),
    direct_only: bool = Query(False),
):
    """
    Wyniki polowania — oferty pasujące do zapisanego configu,
    posortowane po score lub dacie.
    """
    cfg = get_hunt_config()
    listings = get_hunt_listings(limit=limit, offset=offset)

    # Dodatkowe filtry
    if min_score is not None:
        listings = [l for l in listings if (l.get("score") or 0) >= min_score]
    if direct_only:
        listings = [l for l in listings if l.get("direct_offer")]

    # Sortowanie
    if sort_by == "score":
        listings.sort(key=lambda x: x.get("score") or 0, reverse=True)
    elif sort_by == "price":
        listings.sort(key=lambda x: x.get("price") or 999999999)
    elif sort_by == "price_per_m2":
        listings.sort(key=lambda x: x.get("price_per_m2") or 999999999)
    elif sort_by == "date":
        listings.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)

    return {
        "count": len(listings),
        "config": cfg,
        "listings": listings,
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
    return {"count": len(rows), "listings": rows}


@app.get("/listings/{listing_id}")
async def listing_detail(listing_id: int):
    """Szczegóły oferty z historią ceny i analizą AI."""
    listing = get_listing_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    history = get_listing_price_history(listing.get("url", ""))
    return {**listing, "price_history": history}


@app.post("/listings/{listing_id}/analyze")
async def trigger_ai_analysis(listing_id: int):
    """Ręczne wyzwolenie analizy AI dla konkretnej oferty."""
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
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT district, median_price_per_m2, avg_price_per_m2, sample_count
        FROM market_stats
        WHERE district IS NOT NULL AND rooms IS NULL AND condition IS NULL
        ORDER BY median_price_per_m2 DESC NULLS LAST
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"district": r[0], "median": r[1], "avg": r[2], "count": r[3]} for r in rows if r[0]]


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
        save_transaction_prices(data)

    asyncio.create_task(_task())
    return {"status": "started", "city_slug": city_slug, "days": days}


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
    cur.execute("""
        SELECT portal, COUNT(*) FROM listings
        GROUP BY portal ORDER BY COUNT(*) DESC
    """)
    by_portal = {r[0]: r[1] for r in cur.fetchall()}
    cur.close()
    conn.close()
    return {
        "total": total,
        "opportunities": opportunities,
        "pending_llm": pending_llm,
        "by_portal": by_portal,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0"}


# ─── Legacy compat ────────────────────────────────────────────────────────────

@app.post("/run-crawl")
async def run_crawl_legacy(portals: str = Query(None), pages: int = Query(3)):
    """Legacy endpoint — przekierowuje do nowego /hunt/start."""
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
    return {"count": len(rows), "listings": rows}