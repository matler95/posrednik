import os
from typing import List
from fastapi import FastAPI, BackgroundTasks, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from psycopg2.extras import Json

from backend.db import save_listings, get_listings

from backend.scraper import search

import asyncio
from backend.nlp.llm_scorer import process_llm_queue

app = FastAPI(title="WREI Backend")

@app.on_event("startup")
async def startup_event():
    # Inicjalizacja bazy
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS hunt_config (id INT PRIMARY KEY, config JSONB, updated_at TIMESTAMP)")
    # Upewnijmy się, że jeśli tabela jest w starym formacie, zostanie przebudowana (prosta migracja)
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='hunt_config' AND column_name='max_price'")
    if cur.fetchone():
        cur.execute("DROP TABLE hunt_config")
        cur.execute("CREATE TABLE hunt_config (id INT PRIMARY KEY, config JSONB, updated_at TIMESTAMP)")
    
    cur.execute("INSERT INTO hunt_config (id, config, updated_at) VALUES (1, '{}', NOW()) ON CONFLICT DO NOTHING")
    conn.commit()
    cur.close(); conn.close()
    
    # Uruchom procesy AI w tle na stałe
    asyncio.create_task(process_llm_queue())


    # Opcjonalnie: asyncio.create_task(process_photo_queue())


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Enrichment ────────────────────────────────
def enrich_listings(listings: list[dict], city_slug: str = "warszawa") -> list[dict]:
    from backend.market.trend_analyzer import get_rcn_benchmark, compute_cagr
    
    enriched = []
    for l in listings:
        try:
            district = l.get("district")
            rooms = l.get("rooms")
            area = l.get("area")
            bench = get_rcn_benchmark(city_slug, district=district, rooms=rooms, area=area)

            l["rcn_benchmark"] = bench
            if bench and l.get("price_per_m2"):
                gap = (bench - l["price_per_m2"]) / bench
                l["transaction_gap"] = round(gap, 4)
            l["cagr_5y"] = compute_cagr(city_slug, district=district)
            score = 0.0
            if l.get("transaction_gap"):
                score += max(0, min(0.5, l["transaction_gap"] * 2))
            if l.get("direct_offer"):
                score += 0.3
            l["score"] = round(score, 2)
            l["city_slug"] = city_slug
        except Exception as e:
            print(f"Błąd enrich: {e}")
        enriched.append(l)
    return enriched

# ── Tasks ─────────────────────────────────────
def perform_full_crawl_task(params: dict, city_slug: str):
    try:
        print(f"Rozpoczynam crawl dla {city_slug}...")
        listings = search(**params)
        print(f"Pobrano {len(listings)} surowych ofert.")
        if not listings:
            return
        enriched = enrich_listings(listings, city_slug=city_slug)
        save_listings(enriched)
        print(f"Zapisano {len(enriched)} ofert do bazy.")
        from backend.nlp.llm_scorer import process_llm_queue
        process_llm_queue()
    except Exception as exc:
        print(f"Błąd w zadaniu crawlera: {exc}")

# ── Endpoints ─────────────────────────────────
@app.post("/run-crawl")
def run_crawl(
    background_tasks: BackgroundTasks,
    portals: str = Query("otodom"),
    pages: int = Query(5, ge=1, le=100)
):
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT config FROM hunt_config WHERE id = 1")
    row = cur.fetchone()
    cur.close(); conn.close()
    
    cfg = row[0] if row and row[0] else {}
    city_slug = cfg.get("city_slug", "warszawa")
    
    search_params = {
        "portals": portals,
        "pages": pages,
        "min_price": cfg.get("min_price"),
        "max_price": cfg.get("max_price"),
        "min_area": cfg.get("min_area"),
        "max_area": cfg.get("max_area"),
        "rooms": None, # Na razie bez rooms, można dorobić
        "districts": cfg.get("districts", []),
        "direct_only": False,
    }
    background_tasks.add_task(perform_full_crawl_task, search_params, city_slug)
    return {"status": "started", "message": "Zadanie uruchomione w tle."}

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
    from backend.db import get_listings
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
    return {"listing_id": listing_id, "history": get_listing_price_history(listing_id)}

@app.get("/market/rcn-benchmark")
def get_rcn_benchmark_endpoint(city_slug: str = "warszawa", district: str = None, rooms: int = None):
    from backend.market.trend_analyzer import get_rcn_benchmark
    return {"benchmark_sqm": get_rcn_benchmark(city_slug, district=district, rooms=rooms)}

@app.get("/market/trend")
def get_market_trend(city_slug: str = "warszawa", district: str = None):
    from backend.market.trend_analyzer import get_quarterly_trend, compute_cagr, get_offer_vs_transaction_gap
    return {
        "quarterly_trend": get_quarterly_trend(city_slug, district),
        "cagr_5y": compute_cagr(city_slug, district),
        "offer_vs_transaction_gap": get_offer_vs_transaction_gap(city_slug, district)
    }

@app.post("/market/ingest")
def ingest_market_data(background_tasks: BackgroundTasks, city_slug: str = "warszawa", days: int = 30):
    from backend.scrapers.deweloperuch import fetch_recent, save_transaction_prices
    from backend.db import update_market_stats
    def task():
        data = fetch_recent(city_slug, days=days)
        save_transaction_prices(data)
        update_market_stats()
    background_tasks.add_task(task)
    return {"status": "started", "city_slug": city_slug}

@app.post("/set-hunt-config")
def set_config(config: dict):
    from backend.db import save_hunt_config
    save_hunt_config(config)
    return {"status": "saved"}

@app.get("/get-hunt-config")
def get_config():
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT config FROM hunt_config WHERE id = 1")
    row = cur.fetchone()
    cur.close(); conn.close()
    
    default_cfg = {
        "min_price": 0, "max_price": 430000, 
        "min_area": 0, "max_area": 45, 
        "city_slug": "warszawa", "districts": [], "rooms": []
    }
    
    if row and row[0]:
        cfg = row[0]
        # Uzupełnij brakujące klucze domyślnymi wartościami
        for k, v in default_cfg.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    return default_cfg

@app.get("/stats")

def get_stats():
    from backend.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM listings")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM listings WHERE llm_analysis IS NULL")
    pending_llm = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM listings WHERE photo_analysis IS NULL")
    pending_photo = cur.fetchone()[0]
    cur.close(); conn.close()
    return {
        "total": total,
        "pending_llm": pending_llm,
        "pending_photo": pending_photo
    }

@app.get("/health")

def health():
    return {"status": "ok"}
