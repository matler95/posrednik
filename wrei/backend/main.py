"""WREI — FastAPI v2.0 — Wszystkie endpointy."""
import os
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel

from backend.analysis import enrich_listings, find_opportunities
from backend.db import init_db, save_listings, get_listings
from backend.scheduler import start_scheduler
from backend.scraper import available_portals, search

app = FastAPI(
    title="WREI — Wyszukiwarka i Analiza Nieruchomości",
    description="Dane transakcyjne RCN, ML wycena, NLP + Vision scoring.",
    version="2.0.0",
)


# ── Pydantic ──────────────────────────────────
class AlertCreate(BaseModel):
    name: str
    condition_expr: str = ""
    min_score: float = 0.15
    city_slug: str = "warszawa"


# ── Health ────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/portals")
def get_portals():
    return {"portals": available_portals()}


# ── Wyszukiwanie ─────────────────────────────
@app.get("/search")
def search_listings(
    query_url: str | None = Query(None),
    portals: str = Query("otodom"),
    pages: int = Query(1, ge=1),
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    min_area: int | None = Query(None, ge=0),
    max_area: int | None = Query(None, ge=0),
    rooms: str | None = Query(None),
    direct_only: bool = Query(False),
    threshold: float = Query(0.15, ge=0, le=1),
    city_slug: str = Query("warszawa"),
):
    try:
        listings = search(
            query_url=query_url, portals=portals,
            min_price=min_price, max_price=max_price,
            min_area=min_area, max_area=max_area,
            rooms=rooms, pages=pages, direct_only=direct_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    enriched = enrich_listings(listings, city_slug=city_slug)
    opportunities = find_opportunities(enriched, threshold)
    return {
        "query_url": query_url,
        "city_slug": city_slug,
        "total_listings": len(enriched),
        "listings": enriched,
        "opportunities": opportunities,
    }


@app.post("/run-crawl")
def run_crawl(
    background_tasks: BackgroundTasks,
    portals: str = Query("otodom"),
    pages: int = Query(1, ge=1),
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    min_area: int | None = Query(None, ge=0),
    max_area: int | None = Query(None, ge=0),
    rooms: str | None = Query(None),
    direct_only: bool = Query(False),
    city_slug: str = Query("warszawa"),
):
    try:
        listings = search(
            portals=portals, min_price=min_price, max_price=max_price,
            min_area=min_area, max_area=max_area,
            rooms=rooms, pages=pages, direct_only=direct_only,
        )
        # Wzbogać o ML scoring + dane RCN przed zapisem
        enriched = enrich_listings(listings, city_slug=city_slug)
        save_listings(enriched)
        from backend.nlp.llm_scorer import process_llm_queue
        background_tasks.add_task(process_llm_queue)
        return {"status": "ok", "saved": len(enriched)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



# ── Listings z DB ─────────────────────────────
@app.get("/listings")
def get_listings_endpoint(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_score: float | None = Query(None),
    portal: str | None = Query(None),
    district: str | None = Query(None),
    direct_only: bool = Query(False),
    min_price: int | None = Query(None),
    max_price: int | None = Query(None),
    min_area: float | None = Query(None),
    max_area: float | None = Query(None),
):
    rows = get_listings(
        limit=limit, offset=offset,
        min_score=min_score, portal=portal,
        district=district, direct_only=direct_only,
        min_price=min_price, max_price=max_price,
        min_area=min_area, max_area=max_area
    )
    return {"count": len(rows), "listings": rows}



@app.get("/listings/{listing_id}/history")
def get_price_history(listing_id: int):
    from backend.db import get_listing_price_history
    history = get_listing_price_history(listing_id)
    return {"listing_id": listing_id, "history": history}


# ── Dane rynkowe (RCN) ───────────────────────
@app.get("/market/rcn-benchmark")
def get_rcn_benchmark_endpoint(
    city_slug: str = Query("warszawa"),
    district: str | None = Query(None),
    rooms: int | None = Query(None),
):
    from backend.market.trend_analyzer import get_rcn_benchmark
    benchmark = get_rcn_benchmark(city_slug, district=district, rooms=rooms)
    return {"city_slug": city_slug, "district": district, "rooms": rooms, "benchmark_sqm": benchmark}


@app.get("/market/trend")
def get_market_trend(
    city_slug: str = Query("warszawa"),
    district: str | None = Query(None),
):
    from backend.market.trend_analyzer import get_quarterly_trend, compute_cagr, get_offer_vs_transaction_gap
    return {
        "city_slug": city_slug,
        "district": district,
        "cagr_5y": compute_cagr(city_slug, district=district),
        "offer_vs_transaction_gap": get_offer_vs_transaction_gap(city_slug, district=district),
        "quarterly_trend": get_quarterly_trend(city_slug, district=district),
    }


@app.post("/market/ingest")
def ingest_rcn(
    background_tasks: BackgroundTasks,
    city_slug: str = Query("warszawa"),
    days: int = Query(30, ge=1, le=3650),
):
    """Ręczny trigger RCN. days=1825 = 5 lat initial load."""
    from backend.scheduler import update_rcn_data
    background_tasks.add_task(update_rcn_data, [city_slug], days)
    return {"status": "started", "city_slug": city_slug, "days": days}


# ── Alerty CRUD ───────────────────────────────
@app.get("/alerts")
def list_alerts():
    from backend.alerts.evaluator import get_watchlist_alerts
    return {"alerts": get_watchlist_alerts()}


@app.post("/alerts", status_code=201)
def create_alert(alert: AlertCreate):
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO watchlist (name, condition_expr, min_score, city_slug) VALUES (%s, %s, %s, %s) RETURNING id",
        (alert.name, alert.condition_expr, alert.min_score, alert.city_slug),
    )
    alert_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": alert_id, **alert.model_dump()}


@app.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int):
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE watchlist SET active = FALSE WHERE id = %s", (alert_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "deactivated", "id": alert_id}


@app.patch("/alerts/{alert_id}/toggle")
def toggle_alert(alert_id: int):
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE watchlist SET active = NOT active WHERE id = %s RETURNING active", (alert_id,))
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Alert nie znaleziony")
    return {"id": alert_id, "active": row[0]}


# ── Startup ───────────────────────────────────
@app.on_event("startup")
def on_startup():
    init_db()
    start_scheduler()
