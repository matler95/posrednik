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

async def import_rcn_history_task(ctx, city_slug: str, years: float = 20):
    """
    Task workerowy wykonujący import historyczny RCN paczkami kwartalnymi.
    Dzięki filtrowi filterLastTransactionDate=YYYY-Q-YYYY-Q obchodzimy limity stron API.
    
    Parametr years określa jak daleko wstecz szukamy danych.
    """
    from backend.scrapers.deweloperuch import iter_transactions, generate_quarter_ranges
    from backend.db import save_transaction_prices, get_checkpoint, save_checkpoint
    from datetime import date
    import asyncio
    
    # Obliczamy rok początkowy na podstawie parametru years
    end_date = date.today()
    calculated_start_year = end_date.year - int(years) if years >= 1 else end_date.year
    
    # Deweloperuch ma dane od ok. 2006
    start_year = max(2006, calculated_start_year)
    end_year = end_date.year
    end_quarter = (end_date.month - 1) // 3 + 1
    
    # Klucz checkpointu zależy od miasta i zakresu (full vs recent)
    is_full_sync = years >= 10
    job_type = "full" if is_full_sync else "recent"
    job_key = f"rcn_sync_{job_type}:{city_slug}"
    
    checkpoint = get_checkpoint(job_key) or {}
    
    # Lista wszystkich kwartałów do przerobienia
    all_ranges = generate_quarter_ranges(start_year, end_year, end_quarter)
    
    # Znajdujemy gdzie skończyliśmy (ostatni udany kwartał)
    last_completed_range = checkpoint.get("last_completed_range")
    start_idx = 0
    if last_completed_range in all_ranges:
        start_idx = all_ranges.index(last_completed_range) + 1
    
    total_saved = checkpoint.get("total_saved", 0)
    
    print(f"[Worker] Rozpoczynam PEŁNY import RCN ({city_slug}). Do przerobienia {len(all_ranges) - start_idx} kwartałów.", flush=True)
    
    for i in range(start_idx, len(all_ranges)):
        q_range = all_ranges[i]
        print(f"[Worker] Pobieram kwartał: {q_range}...", flush=True)
        
        quarter_records = 0
        batch = []
        
        try:
            # Iterujemy po stronach wewnątrz JEDNEGO kwartału
            for tx in iter_transactions(city_slug, last_transaction_date=q_range):
                batch.append(tx)
                quarter_records += 1
                
                if len(batch) >= 200:
                    saved = save_transaction_prices(batch)
                    total_saved += saved
                    batch = []
                    await asyncio.sleep(0.1)
            
            if batch:
                saved = save_transaction_prices(batch)
                total_saved += saved
            
            print(f"  -> Kwartał {q_range} zakończony. Pobrano {quarter_records} rekordów. Suma: {total_saved}", flush=True)
            
            # Zapisujemy checkpoint po każdym pełnym kwartale
            save_checkpoint(job_key, {
                "last_completed_range": q_range,
                "total_saved": total_saved,
                "status": "in_progress",
                "last_update": date.today().isoformat()
            })
            
            # Lekki delay między kwartałami dla bezpieczeństwa (rate limit)
            await asyncio.sleep(2.0)
            
        except Exception as e:
            print(f"[Worker] Błąd podczas kwartału {q_range}: {e}", flush=True)
            # Nie przerywamy całego procesu, może następny kwartał zadziała
            await asyncio.sleep(10)
            continue
            
    save_checkpoint(job_key, {
        "status": "completed",
        "total_saved": total_saved,
        "last_update": date.today().isoformat()
    })
    print(f"[Worker] PEŁNY IMPORT ZAKOŃCZONY. Łącznie w bazie: {total_saved} rekordów.", flush=True)
    logger.info("[Worker] RCN Full Import Finished. Total: %d", total_saved)

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
