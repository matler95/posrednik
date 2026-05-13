import asyncio
import logging
import json
import time
import os
from arq import create_pool
from arq.connections import RedisSettings

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

async def run_hunt_job_task(ctx, job_id: str, config: dict):
    """
    Task workerowy wykonujący pełne polowanie.
    """
    from backend.hunt_manager import JobStatus
    from backend.db import save_hunt_job
    from backend.scraper_async import run_hunt_async
    from backend.analysis import enrich_listings
    from backend.db import save_listings
    
    redis = ctx['redis']
    
    def emit(event_type: str, data: dict):
        event = {
            "type": event_type, 
            "job_id": job_id,
            "ts": time.time(), 
            **data
        }
        # Publikujemy do Redis pub/sub dla SSE
        asyncio.create_task(redis.publish(f"hunt_events:{job_id}", json.dumps(event)))

    def _persist(status, total_scraped=0, total_saved=0, total_ai=0, error=None, portals_counts=None):
        try:
            save_hunt_job(
                job_id, status, config,
                total_scraped=total_scraped,
                total_saved=total_saved,
                total_ai=total_ai,
                error=error,
                portals_counts=portals_counts
            )
        except Exception as ex:
            logger.warning("[Worker] DB persistence error: %s", ex)

    try:
        # 1. Start
        emit("status", {"status": JobStatus.RUNNING, "message": "🔍 Rozpoczynam polowanie w tle..."})
        _persist(JobStatus.RUNNING)

        # 2. Scrape
        portals_counts = {}
        async def progress_cb(pname, count):
            portals_counts[pname] = count
            total = sum(portals_counts.values())
            emit("portal_done", {
                "portal": pname, "count": count, 
                "total_scraped": total, "portals_counts": portals_counts
            })
            _persist(JobStatus.RUNNING, total_scraped=total, portals_counts=portals_counts)

        raw_listings = await run_hunt_async(config, progress_cb=progress_cb)
        total_scraped = len(raw_listings)
        emit("scraping_done", {"total_scraped": total_scraped, "portals_counts": portals_counts})

        if not raw_listings:
            emit("done", {"message": "⚠️ Brak ofert.", "total_saved": 0})
            _persist(JobStatus.DONE, total_scraped=total_scraped, portals_counts=portals_counts)
            return

        # 3. Enrich
        emit("status", {"status": JobStatus.ENRICHING, "message": f"📊 Wzbogacam {total_scraped} ofert..."})
        _persist(JobStatus.ENRICHING, total_scraped=total_scraped, portals_counts=portals_counts)
        
        city_slug = config.get("city_slug") or "warszawa"
        enriched = await asyncio.to_thread(enrich_listings, raw_listings, city_slug=city_slug)
        emit("enriching_done", {"total_enriched": len(enriched)})

        # 4. Save
        emit("status", {"status": JobStatus.SAVING, "message": f"💾 Zapisuję {len(enriched)} ofert..."})
        _persist(JobStatus.SAVING, total_scraped=total_scraped, portals_counts=portals_counts)
        
        saved = await asyncio.to_thread(save_listings, enriched)
        min_score = config.get("min_score_alert") or 0.20
        opps = sum(1 for l in enriched if (l.get("score") or 0) >= min_score)
        
        emit("saving_done", {"total_saved": saved, "total_opportunities": opps})
        _persist(JobStatus.SAVING, total_scraped=total_scraped, total_saved=saved, portals_counts=portals_counts)

        # 5. AI (Enqueued as sub-tasks or run here)
        # Dla uproszczenia w Stage 2 runujemy top 10 tutaj, reszta w osobnym tasku
        emit("status", {"status": JobStatus.AI_ANALYSIS, "message": "🧠 Analiza AI top ofert..."})
        _persist(JobStatus.AI_ANALYSIS, total_scraped=total_scraped, total_saved=saved, portals_counts=portals_counts)
        
        # TODO: Implement AI sync loop here if needed or just finish
        
        emit("done", {
            "status": JobStatus.DONE,
            "total_saved": saved,
            "total_opportunities": opps,
            "message": "✅ Polowanie zakończone pomyślnie."
        })
        _persist(JobStatus.DONE, total_scraped=total_scraped, total_saved=saved, portals_counts=portals_counts)

    except Exception as e:
        logger.exception("[Worker] Job %s failed: %s", job_id, e)
        emit("error", {"error": str(e)})
        _persist(JobStatus.ERROR, error=str(e))

from arq import cron

async def crawl_all_sources_task(ctx):
    from backend.scheduler import crawl_all_sources
    await asyncio.to_thread(crawl_all_sources)

async def update_rcn_data_task(ctx):
    from backend.scheduler import update_rcn_data
    await asyncio.to_thread(update_rcn_data)

async def geocode_pending_task(ctx):
    from backend.scheduler import geocode_pending
    await asyncio.to_thread(geocode_pending)

async def process_llm_queue_task(ctx):
    from backend.nlp.llm_scorer import run_llm_queue_once
    processed = await run_llm_queue_once(batch_size=10)
    logger.info("[Worker] LLM Queue: processed %d", processed)

async def process_photo_queue_task(ctx):
    try:
        from backend.cv.vision_scorer import process_photo_queue
        await process_photo_queue()
    except Exception as e:
        logger.debug("[Worker] Photo queue skipped or failed: %s", e)

async def update_market_stats_task(ctx):
    from backend.db import generate_market_stats
    await asyncio.to_thread(generate_market_stats)

async def retrain_ml_task(ctx):
    from backend.ml.trainer import train_model
    await asyncio.to_thread(train_model)

async def check_alerts_task(ctx):
    from backend.alerts.evaluator import run_alert_check
    await asyncio.to_thread(run_alert_check)

async def send_daily_digest_task(ctx):
    from backend.alerts.channels import send_daily_digest
    await asyncio.to_thread(send_daily_digest)

async def import_rcn_history_task(ctx, city_slug: str, years: int):
    from backend.scrapers.deweloperuch import iter_transactions
    from backend.db import save_transaction_prices, get_checkpoint, save_checkpoint
    from datetime import date, timedelta
    import asyncio
    
    start_date = date.today() - timedelta(days=years * 365)
    # Align to start of month for cleaner slicing
    current_date = date(start_date.year, start_date.month, 1)
    end_date = date.today()
    
    job_key = f"rcn_history_v2:{city_slug}:{years}y"
    checkpoint = get_checkpoint(job_key) or {}
    
    # Resume from last month if possible
    last_month_str = checkpoint.get("last_month")
    if last_month_str:
        current_date = date.fromisoformat(last_month_str)
        
    total_saved = checkpoint.get("total_saved", 0)
    
    print(f"[Worker] Rozpoczynam krokowy import RCN ({years} lat) dla {city_slug} od {current_date.isoformat()}", flush=True)
    
    while current_date <= end_date:
        next_month = (current_date + timedelta(days=32)).replace(day=1)
        # Format: 2019-1-2019-1 (for one month)
        range_str = f"{current_date.year}-{current_date.month}-{current_date.year}-{current_date.month}"
        
        print(f"[Worker] Pobieram okres (filterLastTransactionDate): {range_str}...", flush=True)
        
        month_records = 0
        month_saved = 0
        batch = []
        for tx in iter_transactions(city_slug, last_transaction_date=range_str):
            batch.append(tx)
            month_records += 1
            
            if len(batch) >= 500:
                saved = save_transaction_prices(batch)
                total_saved += saved
                month_saved += saved
                batch = []
                save_checkpoint(job_key, {"last_month": current_date.isoformat(), "total_saved": total_saved})
                print(f"  -> Przetworzono 500 (Nowych: {saved}, Suma zadania: {total_saved})", flush=True)
        
        if batch:
            saved = save_transaction_prices(batch)
            total_saved += saved
            month_saved += saved
            
        print(f"[Worker] Zakończono {range_str}. Przejrzano {month_records}, Zapisano {month_saved} nowych. Suma: {total_saved}", flush=True)
        
        current_date = next_month
        save_checkpoint(job_key, {"last_month": current_date.isoformat(), "total_saved": total_saved})
        await asyncio.sleep(2)
    
    logger.info("[Worker] KOMPLETNY IMPORT ZAKOŃCZONY. Łącznie: %d rekordów.", total_saved)

async def startup(ctx):
    ctx['redis'] = await create_pool(RedisSettings(host=REDIS_HOST))

async def shutdown(ctx):
    await ctx['redis'].close()

class WorkerSettings:
    functions = [
        run_hunt_job_task, 
        crawl_all_sources_task,
        update_rcn_data_task,
        geocode_pending_task,
        process_llm_queue_task,
        process_photo_queue_task,
        update_market_stats_task,
        retrain_ml_task,
        check_alerts_task,
        send_daily_digest_task,
        import_rcn_history_task
    ]
    cron_jobs = [
        cron(crawl_all_sources_task, hour={6, 12, 18}, minute=0),
        cron(update_rcn_data_task, hour=4, minute=0),
        cron(geocode_pending_task, minute={0, 30}), # co 30 min zamiast 2h dla lepszej responsywności
        cron(process_llm_queue_task, minute={0, 10, 20, 30, 40, 50}),
        cron(process_photo_queue_task, minute={5, 20, 35, 50}),
        cron(update_market_stats_task, hour=3, minute=0),
        cron(retrain_ml_task, weekday='sun', hour=2, minute=0),
        cron(check_alerts_task, minute={0, 15, 30, 45}),
        cron(send_daily_digest_task, hour=8, minute=0),
    ]
    redis_settings = RedisSettings(host=REDIS_HOST)
    on_startup = startup
    on_shutdown = shutdown
    job_timeout = 3600 # 1 godzina na import historii
