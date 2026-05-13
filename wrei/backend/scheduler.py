"""
Scheduler WREI — kompletny harmonogram zadań.
Używa APScheduler (BackgroundScheduler) — działa w tle wewnątrz procesu FastAPI.

Harmonogram:
  - Scrapowanie portali co 6h (otodom, olx, morizon, gratka, domiporta, nieruchomosci_online)
  - Aktualizacja danych RCN (Deweloperuch) codziennie o 4:00
  - Geocoding transakcji bez dzielnicy co 2h
  - Kolejka LLM (Ollama text) co 10 min
  - Kolejka photo (CLIP + Vision) co 15 min
  - Generowanie market_stats codziennie o 3:00
  - Retrain modelu ML co niedzielę o 2:00
  - Sprawdzanie alertów co 15 min
  - Dzienny digest Telegram o 8:00
"""
import asyncio
import logging
from backend.db import record_scrape_run, save_listings, get_conn

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 1. Scrapowanie portali
# ─────────────────────────────────────────────

ALL_PORTALS = "otodom,olx,morizon,gratka,domiporta,nieruchomosci_online"

def crawl_all_sources(portals: str | None = None, pages: int = 2):
    from backend.db import get_hunt_config
    cfg = get_hunt_config()
    
    # Jeśli portals nie podano, bierzemy z configu
    portals = portals or ",".join(cfg.get("portals", ["otodom"]))
    direct_only = cfg.get("direct_only", False)

    logger.info("[Crawl] Start (Hunt Mode): portals=%s pages=%s", portals, pages)
    listings = []
    try:
        listings = search(
            portals=portals, 
            pages=pages, 
            min_price=cfg.get("min_price"),
            max_price=cfg.get("max_price"),
            min_area=cfg.get("min_area"),
            max_area=cfg.get("max_area"),
            rooms=cfg.get("rooms", []),
            districts=cfg.get("districts", []),
            direct_only=direct_only
        )
        save_listings(listings)
        record_scrape_run(portals, pages, direct_only, "completed", len(listings), query_url=None)
        logger.info("[Crawl] Zakończono: %d ofert", len(listings))
    except Exception:
        logger.exception("[Crawl] Błąd podczas scrapowania")
        record_scrape_run(portals, pages, direct_only, "failed", len(listings), query_url=None)


# ─────────────────────────────────────────────
# 2. Dane transakcyjne RCN (Deweloperuch)
# ─────────────────────────────────────────────

def update_rcn_data(city_slugs: list[str] | None = None, days: int = 30):
    """Pobiera transakcje RCN z ostatnich N dni i zapisuje do DB."""
    import os
    from backend.scrapers.deweloperuch import fetch_recent
    from backend.db import save_transaction_prices

    cities = city_slugs or [c.strip() for c in os.getenv("TARGET_CITIES", "warszawa").split(",")]
    for city in cities:
        try:
            transactions = fetch_recent(city, days=days, max_pages=100)
            saved = save_transaction_prices(transactions)

            logger.info("[RCN] %s: zapisano %d transakcji", city, saved)
        except Exception:
            logger.exception("[RCN] Błąd dla miasta: %s", city)
    
    # Odśwież statystyki po pobraniu nowych danych
    update_market_stats()


def initial_rcn_load(city_slugs=None, years=5):
    """
    Strategia:
    - Pierwsza sesja: pobierz ostatnie 90 dni (szybko, ~10 stron)
    - Historia: dogłębne pobieranie historii w tle
    """
    import os
    from backend.scrapers.deweloperuch import fetch_recent
    from backend.db import save_transaction_prices

    cities = city_slugs or [c.strip() for c in os.getenv("TARGET_CITIES", "warszawa").split(",")]
    
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transaction_prices")
        count = cur.fetchone()[0]

    if count > 1000:
        logger.info("[RCN] Baza zawiera %d rekordów — pomijam initial load", count)
        return

    logger.info("[RCN] Initial load: ostatnie 90 dni (fast start)...")
    for city in cities:
        try:
            # Szybki start: 90 dni, max 20 stron
            transactions = fetch_recent(city, days=90, max_pages=20)
            saved = save_transaction_prices(transactions)
            logger.info("[RCN] %s fast-start: %d transakcji", city, saved)
        except Exception:
            logger.exception("[RCN] Fast-start error dla: %s", city)

    _background_historical_load(cities, years=years)

def _background_historical_load(cities, years=5):
    """Pobieranie historii w tle — uruchamiane po fast-start."""
    from backend.scrapers.deweloperuch import fetch_historical
    from backend.db import save_transaction_prices
    for city in cities:
        try:
            logger.info("[RCN BG] Historia %d lat dla %s...", years, city)
            transactions = fetch_historical(city, years=years)
            saved = save_transaction_prices(transactions)
            logger.info("[RCN BG] %s: %d historycznych transakcji", city, saved)
        except Exception:
            logger.exception("[RCN BG] Error dla: %s", city)
    try:
        from backend.db import generate_market_stats
        generate_market_stats()
        logger.info("[RCN BG] market_stats zaktualizowane po historical load")
    except Exception as e:
        logger.warning("[RCN BG] Stats error: %s", e)
    
    # Geocoding bez rate-limitu Nominatim — używamy tylko regex (instant)
    try:
        from backend.scrapers.deweloperuch import batch_geocode_missing
        for city in cities:
            updated = batch_geocode_missing(city, limit=5000)  # regex jest instant
            logger.info("[RCN BG] Geocoding regex: %d rekordów dla %s", updated, city)
    except Exception as e:
        logger.warning("[RCN BG] Geocoding error: %s", e)


# ─────────────────────────────────────────────
# 3. Geocoding (adresy → dzielnice)
# ─────────────────────────────────────────────

def geocode_pending():
    """Geocoduje transakcje bez przypisanej dzielnicy (batch po 100)."""
    from backend.db import get_transactions_without_district, update_transaction_district
    from backend.market.geocoder import geocode_address
    import time

    pending = get_transactions_without_district(limit=100)
    if not pending:
        return

    logger.info("[Geocoder] %d adresów do geocodowania", len(pending))
    for item in pending:
        slug = item["invest_slug"]
        address = item.get("street_address") or slug.replace("-", " ").title()
        city_slug = item.get("city_slug", "warszawa")

        try:
            geo = geocode_address(address, city_slug)
            if geo and geo.get("district"):
                update_transaction_district(slug, geo["district"])
                from backend.db import save_geocode_cache
                save_geocode_cache(slug, address, geo)
        except Exception as e:
            logger.warning("[Geocoder] Błąd dla %s: %s", address, e)
        time.sleep(1.1)  # Nominatim rate limit


# ─────────────────────────────────────────────
# 4. Kolejka LLM (Ollama text)
# ─────────────────────────────────────────────

def process_llm_queue_sync():
    """Wrapper synchroniczny — tworzy nowy event loop zamiast asyncio.run()."""
    import asyncio
    from backend.nlp.llm_scorer import run_llm_queue_once
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            processed = loop.run_until_complete(run_llm_queue_once(batch_size=5))
            logger.info("[LLM Scheduler] Przetworzono %d ofert", processed)
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    except Exception:
        logger.exception("[LLM] Błąd kolejki LLM")

# ─────────────────────────────────────────────
# 5. Kolejka photo (CLIP + Ollama Vision)
# ─────────────────────────────────────────────

def process_photo_queue():
    """Analizuje zdjęcia dla ofert z score > 0.08."""
    try:
        from backend.cv.vision_scorer import process_photo_queue as _process
        asyncio.run(_process())
    except ImportError:
        logger.debug("[Photo] Moduł cv.vision_scorer niedostępny (Faza 4 nie wdrożona)")
    except Exception:
        logger.exception("[Photo] Błąd kolejki zdjęć")


# ─────────────────────────────────────────────
# 6. Market stats + ML retrain
# ─────────────────────────────────────────────

def update_market_stats():
    from backend.db import generate_market_stats
    try:
        generate_market_stats()
        logger.info("[Stats] market_stats zaktualizowane")
    except Exception:
        logger.exception("[Stats] Błąd generowania statystyk")


def retrain_ml():
    from backend.ml.trainer import train_model
    try:
        result = train_model()
        logger.info("[ML] Retrain zakończony: %s", result)
    except Exception:
        logger.exception("[ML] Błąd retrainingu modelu")


# ─────────────────────────────────────────────
# 7. Alerty + Telegram digest
# ─────────────────────────────────────────────

def check_alerts():
    """Sprawdza warunki alertów i wysyła powiadomienia Telegram."""
    try:
        from backend.alerts.evaluator import run_alert_check
        run_alert_check()
    except ImportError:
        logger.debug("[Alerts] Moduł alerts.evaluator niedostępny (Faza 5)")
    except Exception:
        logger.exception("[Alerts] Błąd sprawdzania alertów")


def send_daily_digest():
    """Wysyła dzienny digest Telegram z top okazjami."""
    try:
        from backend.alerts.channels import send_daily_digest as _digest
        _digest()
    except ImportError:
        logger.debug("[Digest] Moduł alerts.channels niedostępny (Faza 5)")
    except Exception:
        logger.exception("[Digest] Błąd wysyłania digestu")
