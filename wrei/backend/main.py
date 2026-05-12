"""
WREI Backend — FastAPI application.
Modularized version v3.0.
"""
import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import init_db
from backend.api import listings, hunt, market, alerts, system

logger = logging.getLogger(__name__)

app = FastAPI(title="WREI — Real Estate AI Hunter", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(listings.router)
app.include_router(hunt.router)
app.include_router(market.router)
app.include_router(alerts.router)
app.include_router(system.router)

@app.on_event("startup")
async def startup():
    init_db()
    
    # 1. Market stats generation
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
        logger.warning("[Startup] Market stats check error: %s", e)

    # 2. RCN Auto-ingest
    try:
        from backend.db import get_conn
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transaction_prices")
        rcn_count = cur.fetchone()[0]
        cur.close(); conn.close()
        
        if rcn_count < 100:
            logger.info("[Startup] Mało danych RCN (%d). Pobieram ostatnie 90 dni...", rcn_count)
            from backend.scrapers.deweloperuch import fetch_recent
            from backend.db import save_transaction_prices
            
            def _rcn_task():
                data = fetch_recent("warszawa", days=90)
                save_transaction_prices(data)
                logger.info("[Startup RCN] Pobrano %d transakcji.", len(data))
                
            asyncio.create_task(asyncio.to_thread(_rcn_task))
            
    except Exception as e:
        logger.warning("[Startup] RCN ingest error: %s", e)
    
    logger.info("[WREI] Backend v3.0 (Modular + Distributed) uruchomiony.")