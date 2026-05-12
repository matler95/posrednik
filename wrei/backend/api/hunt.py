from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from backend.db import (
    get_hunt_config, get_hunt_listings, get_hunt_job, 
    save_hunt_config, get_conn
)

router = APIRouter(tags=["hunt"])

def _serialize(obj: dict) -> dict:
    out = {}
    for k, v in obj.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out

@router.post("/hunt/start")
async def hunt_start(body: dict):
    from backend.hunt_manager import hunt_manager
    config = body.get("config") or get_hunt_config()
    if body.get("save", True):
        save_hunt_config(config)
    job = await hunt_manager.start_job(config)
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stream_url": f"/hunt/stream/{job.job_id}",
    }

@router.get("/hunt/stream/{job_id}")
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

@router.get("/hunt/status")
async def hunt_status():
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
            "total_scraped": job.total_scraped,
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

@router.get("/hunt/results")
async def hunt_results(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_score: float = Query(None),
    sort_by: str = Query("score"),
    direct_only: bool = Query(False),
    district: str = Query(None),
):
    listings = get_hunt_listings(limit=limit, offset=offset)
    if min_score is not None:
        listings = [l for l in listings if (l.get("score") or 0) >= min_score]
    if direct_only:
        listings = [l for l in listings if l.get("direct_offer")]
    if district:
        listings = [l for l in listings if l.get("district") == district]

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

@router.get("/hunt/job/{job_id}")
async def hunt_job_detail(job_id: str):
    job_db = get_hunt_job(job_id)
    if job_db:
        return _serialize(job_db)
    
    from backend.hunt_manager import hunt_manager
    active = hunt_manager.current_job
    if active and active.job_id == job_id:
        return {
            "id": active.job_id,
            "status": active.status,
            "config": active.config,
            "total_scraped": active.total_scraped,
            "total_saved": active.total_saved,
            "total_ai_analyzed": active.total_ai_analyzed,
            "portals_counts": active.portals_counts,
            "started_at": active.started_at,
        }
    raise HTTPException(status_code=404, detail="Job nie znaleziony")

@router.get("/get-hunt-config")
async def get_config():
    cfg = get_hunt_config()
    return cfg

@router.post("/set-hunt-config")
async def set_config(config: dict):
    save_hunt_config(config)
    return {"status": "saved"}

# Legacy
@router.post("/run-crawl")
async def run_crawl_legacy(portals: str = Query(None), pages: int = Query(3)):
    cfg = get_hunt_config()
    if portals:
        cfg["portals"] = [p.strip() for p in portals.split(",")]
    cfg["pages"] = pages
    from backend.hunt_manager import hunt_manager
    job = await hunt_manager.start_job(cfg)
    return {"status": "started", "job_id": job.job_id}

@router.get("/hunt/listings")
async def hunt_listings_legacy(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = get_hunt_listings(limit=limit, offset=offset)
    return {"count": len(rows), "listings": [_serialize(r) for r in rows]}
