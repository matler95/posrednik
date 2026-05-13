import logging
import httpx
from fastapi import APIRouter
from backend.db import get_conn

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])

@router.get("/health")
async def health_check():
    status = {"status": "ok", "components": {}}
    
    # 1. Database check
    try:
        from backend.db import get_conn
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close(); conn.close()
        status["components"]["database"] = "ok"
    except Exception as e:
        status["status"] = "error"
        status["components"]["database"] = f"error: {str(e)}"
        
    # 2. Ollama check
    try:
        from backend.nlp.llm_scorer import OLLAMA_URL
        async with httpx.AsyncClient(timeout=2.0) as client:
            base_url = OLLAMA_URL.rsplit('/', 2)[0]
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                status["components"]["ollama"] = "ok"
            else:
                status["components"]["ollama"] = f"status: {resp.status_code}"
    except Exception as e:
        status["components"]["ollama"] = f"unreachable: {str(e)}"
        
    # 3. Redis (ARQ) check
    try:
        import os
        from arq import create_pool
        from arq.connections import RedisSettings
        REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
        redis = await create_pool(RedisSettings(host=REDIS_HOST))
        await redis.ping()
        await redis.close()
        status["components"]["redis"] = "ok"
    except Exception as e:
        status["components"]["redis"] = f"error: {str(e)}"

    return status

@router.get("/stats")
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

@router.get("/health-legacy")
async def health_legacy():
    return {"status": "ok", "version": "2.2"}
