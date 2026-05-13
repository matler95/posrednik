"""
WREI Backend — FastAPI application.
Modularized version v3.0.
"""
import os
import asyncio
import logging
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from backend.db import init_db, get_conn
from backend.api import listings, hunt, market, alerts, system

logger = logging.getLogger(__name__)

app = FastAPI(title="WREI — Real Estate AI Hunter", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("WREI_API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if not API_KEY:
        # If no key is configured, allow all (or we could enforce default)
        return
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials"
        )

# Register Routers
app.include_router(listings.router, prefix="/listings", tags=["listings"], dependencies=[Depends(verify_api_key)])
app.include_router(hunt.router, prefix="/hunt", tags=["hunt"], dependencies=[Depends(verify_api_key)])
app.include_router(market.router, prefix="/market", tags=["market"], dependencies=[Depends(verify_api_key)])
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"], dependencies=[Depends(verify_api_key)])
app.include_router(system.router, prefix="/system", tags=["system"], dependencies=[Depends(verify_api_key)])

@app.on_event("shutdown")
async def shutdown_event():
    from backend.db import close_pool
    from backend.hunt_manager import hunt_manager
    await hunt_manager.close()
    close_pool()
    logger.info("[Main] System shutdown.")

@app.on_event("startup")
async def startup_event():
    """Startup routine: migrations, market stats, and RCN ingestion."""
    init_db()
    
    # 1. Market stats check
    asyncio.create_task(_ensure_market_stats())

    # 2. RCN Initial Ingestion check
    asyncio.create_task(_enqueue_initial_rcn_ingest())

    logger.info("[WREI] Backend v3.0 (Modular + Distributed) is ready.")

async def _ensure_market_stats():
    """Generates market stats if missing and data is available."""
    try:
        from backend.db import generate_market_stats, get_conn
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM market_stats")
            ms_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM listings")
            l_count = cur.fetchone()[0]
        
        if ms_count == 0 and l_count > 10:
            logger.info("[Startup] Missing market_stats. Generating...")
            await asyncio.to_thread(generate_market_stats)
    except Exception as e:
        logger.warning("[Startup] Market stats check failed: %s", e)

async def _enqueue_initial_rcn_ingest():
    """Enqueues RCN ingestion based on current DB state."""
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        from backend.db import get_conn
        
        REDIS_HOST = os.getenv("REDIS_HOST", "redis")
        
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM transaction_prices")
            rcn_count = cur.fetchone()[0]
        
        redis = await create_pool(RedisSettings(host=REDIS_HOST))
        
        if rcn_count < 100:
            # Empty DB: Full history (20 years)
            logger.info("[Startup] RCN database empty. Enqueuing FULL history sync...")
            await redis.enqueue_job('import_rcn_history_task', "warszawa", 20)
        elif rcn_count < 10000:
            # Partial DB: Medium history (7 years)
            logger.info("[Startup] RCN database small (%d). Enqueuing 7-year history sync...", rcn_count)
            await redis.enqueue_job('import_rcn_history_task', "warszawa", 7)
        else:
            # Healthy DB: Quick catch-up (last 30 days)
            logger.info("[Startup] RCN database healthy. Enqueuing 30-day catch-up...")
            await redis.enqueue_job('import_rcn_history_task', "warszawa", 0.08)
            
        await redis.close()
    except Exception as e:
        logger.warning("[Startup] RCN auto-ingest failed to enqueue: %s", e)