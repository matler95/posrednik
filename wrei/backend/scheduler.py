import logging
from apscheduler.schedulers.background import BackgroundScheduler

from backend.db import init_db, record_scrape_run, save_listings
from backend.scraper import search

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(daemon=True)


def crawl_all_sources(portals="otodom", pages=1, direct_only=False):
    logger.info("Rozpoczynam crawl ofert: portals=%s pages=%s direct_only=%s", portals, pages, direct_only)
    listings = []
    try:
        listings = search(portals=portals, pages=pages, direct_only=direct_only)
        save_listings(listings)
        run_id = record_scrape_run(portals, pages, direct_only, "completed", len(listings), query_url=None)
        logger.info("Crawl zakończony: %s ofert zapisanych", len(listings))
        return run_id
    except Exception as exc:
        logger.exception("Błąd podczas crawlowania ofert")
        record_scrape_run(portals, pages, direct_only, "failed", len(listings), query_url=None)
        raise


def start_scheduler(interval_minutes=60):
    init_db()
    
    # 1. Scrapowanie
    scheduler.add_job(
        crawl_all_sources,
        "interval",
        minutes=interval_minutes,
        args=("otodom", 2, False),
        id="crawl_all_sources",
        replace_existing=True,
    )
    
    # 2. Market stats (codziennie o 3:00)
    from backend.db import generate_market_stats
    scheduler.add_job(
        generate_market_stats,
        "cron",
        hour=3,
        minute=0,
        id="stats_update",
        replace_existing=True,
    )
    
    # 3. Trening modelu ML (co niedzielę o 2:00)
    from backend.ml.trainer import train_model
    scheduler.add_job(
        train_model,
        "cron",
        day_of_week="sun",
        hour=2,
        minute=0,
        id="ml_retrain",
        replace_existing=True,
    )
    
    scheduler.start()
    logger.info("Scheduler uruchomiony z zadanym interwalem: %s minut", interval_minutes)


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler zatrzymany")
