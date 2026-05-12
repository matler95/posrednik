"""
Hunt Job Manager — spójny flow: config → scrape → enrich → save → AI (sync top 20).

NAPRAWKI:
1. FIX AttributeError: job.total_found → job.total_scraped (w _run_job i emit)
2. FIX ImportError: save_listing_score teraz istnieje w db.py
3. Emituje enriching_done poprawnie (był pominięty w oryginalnym kodzie)
4. Lepsza obsługa błędów LLM (timeout Ollama nie crasha całego joba)
5. Poprawna serializacja zdarzeń SSE
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator, Callable

logger = logging.getLogger(__name__)

# Ile ofert analizujemy LLM SYNCHRONICZNIE przed wyświetleniem wyników
LLM_SYNC_BATCH = 20
# Maksymalna liczba ofert wysyłanych do LLM per run (reszta → kolejka w tle)
LLM_TOTAL_LIMIT = 50


class JobStatus(str, Enum):
    PENDING     = "pending"
    RUNNING     = "running"
    ENRICHING   = "enriching"
    SAVING      = "saving"
    AI_ANALYSIS = "ai_analysis"
    DONE        = "done"
    ERROR       = "error"


@dataclass
class HuntJob:
    job_id: str
    config: dict
    status: JobStatus = JobStatus.PENDING
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    total_scraped: int = 0        # FIX: było total_found w jednym miejscu
    total_saved: int = 0
    total_opportunities: int = 0
    total_ai_analyzed: int = 0
    portals_counts: dict = field(default_factory=dict)
    error: str | None = None
    events: list[dict] = field(default_factory=list)
    _subscribers: list = field(default_factory=list, repr=False)

    def emit(self, event_type: str, data: dict):
        event = {"type": event_type, "ts": time.time(), **data}
        self.events.append(event)
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.append(q)
        # Wyślij historię do nowego subskrybenta
        for event in self.events[-50:]:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                break
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)


class HuntJobManager:
    """Singleton zarządzający aktywnym jobem polowania."""

    def __init__(self):
        self._current_job: HuntJob | None = None
        self._lock = asyncio.Lock()

    @property
    def current_job(self) -> HuntJob | None:
        return self._current_job

    async def start_job(self, config: dict) -> HuntJob:
        async with self._lock:
            job_id = str(uuid.uuid4())
            job = HuntJob(job_id=job_id, config=config)
            self._current_job = job
            asyncio.create_task(self._run_job(job))
            logger.info("[JobManager] Job %s uruchomiony: %s", job_id, config)
            return job

    async def _run_job(self, job: HuntJob):
        from backend.scraper_async import run_hunt_async
        from backend.analysis import enrich_listings
        from backend.db import save_listings, save_hunt_job

        def _persist():
            try:
                save_hunt_job(
                    job.job_id, job.status, job.config,
                    total_scraped=job.total_scraped,
                    total_saved=job.total_saved,
                    total_ai=job.total_ai_analyzed,
                    error=job.error,
                    portals_counts=job.portals_counts
                )
            except Exception as ex:
                logger.warning("[JobManager] DB persistence error: %s", ex)

        try:
            # ── FAZA 1: Scrapowanie ──────────────────────────────────────
            job.status = JobStatus.RUNNING
            _persist()
            job.emit("status", {
                "status": job.status,
                "message": "🔍 Skanowanie portali...",
            })

            async def portal_progress(portal_name: str, count: int):
                job.portals_counts[portal_name] = count
                job.total_scraped = sum(job.portals_counts.values())
                job.emit("portal_done", {
                    "portal": portal_name,
                    "count": count,
                    "total_scraped": job.total_scraped,
                    "portals_counts": dict(job.portals_counts),
                })
                _persist()

            raw_listings = await run_hunt_async(job.config, progress_cb=portal_progress)
            job.total_scraped = len(raw_listings)
            job.emit("scraping_done", {
                "total_scraped": len(raw_listings),
                "portals_counts": dict(job.portals_counts),
            })

            if not raw_listings:
                job.status = JobStatus.DONE
                job.finished_at = time.time()
                job.emit("done", {
                    "total_saved": 0,
                    "total_opportunities": 0,
                    "elapsed_s": round(job.finished_at - job.started_at, 1),
                    "message": "⚠️ Brak ofert spełniających kryteria.",
                })
                return

            # ── FAZA 2: Enrichment ───────────────────────────────────────
            job.status = JobStatus.ENRICHING
            job.emit("status", {
                "status": job.status,
                "message": f"📊 Wzbogacam {len(raw_listings)} ofert (RCN + scoring)...",
            })

            city_slug = job.config.get("city_slug") or "warszawa"
            loop = asyncio.get_event_loop()
            enriched = await loop.run_in_executor(
                None,
                lambda: enrich_listings(raw_listings, city_slug=city_slug)
            )

            # FIX: emituj enriching_done (było pominięte w oryginale)
            job.emit("enriching_done", {"total_enriched": len(enriched)})
            _persist()

            # ── FAZA 3: Zapis ────────────────────────────────────────────
            job.status = JobStatus.SAVING
            job.emit("status", {
                "status": job.status,
                "message": f"💾 Zapisuję {len(enriched)} ofert...",
            })

            saved = await loop.run_in_executor(None, lambda: save_listings(enriched))
            job.total_saved = saved

            min_score = job.config.get("min_score_alert") or 0.20
            job.total_opportunities = sum(
                1 for l in enriched if (l.get("score") or 0) >= min_score
            )

            job.emit("saving_done", {
                "total_saved": saved,
                "total_opportunities": job.total_opportunities,
                "min_score": min_score,
            })
            _persist()

            # ── FAZA 4: Analiza AI (synchroniczna dla top 20) ────────────
            job.status = JobStatus.AI_ANALYSIS
            job.emit("status", {
                "status": job.status,
                "message": f"🧠 Analiza AI top {LLM_SYNC_BATCH} ofert (poczekaj chwilę)...",
            })

            analyzed_count = await _sync_ai_analysis(job, enriched, city_slug)
            job.total_ai_analyzed = analyzed_count
            _persist()

            # ── DONE ─────────────────────────────────────────────────────
            job.status = JobStatus.DONE
            job.finished_at = time.time()
            elapsed = round(job.finished_at - job.started_at, 1)

            job.emit("done", {
                "total_scraped": job.total_scraped,
                "total_saved": saved,
                "total_opportunities": job.total_opportunities,
                "total_ai_analyzed": job.total_ai_analyzed,
                "elapsed_s": elapsed,
                "portals_counts": dict(job.portals_counts),
                "message": (
                    f"✅ Gotowe: {saved} ofert, "
                    f"{job.total_opportunities} okazji, "
                    f"{job.total_ai_analyzed} przeanalizowanych przez AI "
                    f"({elapsed}s)"
                ),
            })
            _persist()

        except Exception as e:
            logger.exception("[JobManager] Błąd joba %s: %s", job.job_id, e)
            job.status = JobStatus.ERROR
            job.error = str(e)
            job.emit("error", {
                "error": str(e),
                "message": f"❌ Błąd: {e}",
            })
            _persist()


async def _sync_ai_analysis(
    job: HuntJob,
    enriched_listings: list[dict],
    city_slug: str,
    batch_size: int = LLM_SYNC_BATCH,
) -> int:
    """
    Synchroniczna analiza LLM dla top N ofert według score.
    Wyniki emitowane przez SSE na bieżąco — frontend aktualizuje karty.

    NAPRAWKI:
    - FIX ImportError: save_listing_score teraz importuje z db.py (funkcja dodana)
    - Lepsza obsługa timeoutów Ollama
    - Nie crasha joba jeśli Ollama niedostępna
    """
    from backend.db import get_listings_for_llm_analysis, save_llm_analysis, save_listing_score
    from backend.nlp.llm_scorer import analyze_listing_with_llm
    from backend.analysis import text_score_from_llm
    from backend.model import opportunity_score, group_average_price_per_sqm

    # Pobierz świeże rekordy z DB (mają ID, url itp.)
    listings_to_analyze = get_listings_for_llm_analysis(limit=batch_size)
    if not listings_to_analyze:
        logger.info("[AI] Brak ofert do analizy (wszystkie już przeanalizowane?)")
        return 0

    logger.info("[AI] Synchroniczna analiza %d ofert dla joba %s", len(listings_to_analyze), job.job_id)

    averages = group_average_price_per_sqm(enriched_listings)
    analyzed = 0

    for i, listing in enumerate(listings_to_analyze):
        try:
            job.emit("ai_progress", {
                "current": i + 1,
                "total": len(listings_to_analyze),
                "listing_id": listing["id"],
                "title": (listing.get("title") or "")[:60],
            })

            analysis = await analyze_listing_with_llm(listing)

            if analysis and "error" not in analysis:
                save_llm_analysis(listing["url"], analysis)

                # Aktualizuj text_score i re-oblicz score
                new_text_score = text_score_from_llm(analysis)
                listing["llm_analysis"] = analysis
                listing["text_score"] = new_text_score

                # Re-oblicz score z nowym text_score
                new_score = opportunity_score(
                    listing, averages,
                    listing.get("estimated_value"),
                    rcn_benchmark=listing.get("rcn_benchmark"),
                    cagr=listing.get("cagr_5y"),
                    city_slug=city_slug,
                )

                # FIX: save_listing_score teraz istnieje
                save_listing_score(listing["id"], new_score, new_text_score)

                job.emit("ai_done", {
                    "listing_id": listing["id"],
                    "url": listing["url"],
                    "investment_score": analysis.get("investment_score"),
                    "condition": analysis.get("condition"),
                    "summary": (analysis.get("summary") or "")[:300],
                    "green_flags": (analysis.get("green_flags") or [])[:4],
                    "red_flags": (analysis.get("red_flags") or [])[:4],
                    "text_score": round(new_text_score, 3),
                    "new_score": round(new_score, 3),
                    "negotiation_potential": analysis.get("negotiation_potential"),
                })
                analyzed += 1
            else:
                # Oznacz błąd żeby nie próbować ponownie w tej sesji
                save_llm_analysis(listing["url"], {"error": "llm_failed"})

        except Exception as e:
            logger.warning("[AI] Błąd dla listing %d: %s", listing.get("id", -1), e)

        # Rate limit dla Ollamy
        await asyncio.sleep(1.5)

    # Uruchom resztę (beyond batch_size) w tle
    remaining_limit = LLM_TOTAL_LIMIT - batch_size
    if remaining_limit > 0:
        asyncio.create_task(_background_ai_queue(remaining_limit))
        job.emit("status", {
            "status": JobStatus.DONE,
            "message": "🔄 Pozostałe oferty analizowane w tle...",
        })

    return analyzed


async def _background_ai_queue(limit: int = 30) -> None:
    """
    Kontynuuje analizę LLM w tle dla ofert poza top N.
    Nie blokuje użytkownika.
    """
    from backend.db import get_listings_for_llm_analysis, save_llm_analysis
    from backend.nlp.llm_scorer import analyze_listing_with_llm

    listings = get_listings_for_llm_analysis(limit=limit)
    logger.info("[AI BG] Analiza %d ofert w tle", len(listings))

    for listing in listings:
        try:
            analysis = await analyze_listing_with_llm(listing)
            if analysis and "error" not in analysis:
                save_llm_analysis(listing["url"], analysis)
        except Exception as e:
            logger.debug("[AI BG] Błąd dla listing %d: %s", listing.get("id", -1), e)
        await asyncio.sleep(2.0)


# Globalny singleton
hunt_manager = HuntJobManager()


async def stream_job_events(job: HuntJob) -> AsyncGenerator[str, None]:
    """Generator SSE — streamuje eventy joba do frontendu."""
    q = job.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                data = json.dumps(event, ensure_ascii=False, default=str)
                yield f"data: {data}\n\n"

                if event.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                yield 'data: {"type":"heartbeat"}\n\n'
    finally:
        job.unsubscribe(q)