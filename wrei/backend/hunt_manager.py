"""
Hunt Job Manager — spójny flow: config → scrape → enrich → save → AI queue.
Jeden aktywny job na raz, progress streamowany przez SSE.
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


class JobStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    ENRICHING = "enriching"
    SAVING    = "saving"
    AI_QUEUE  = "ai_analysis"
    DONE      = "done"
    ERROR     = "error"


@dataclass
class HuntJob:
    job_id: str
    config: dict
    status: JobStatus = JobStatus.PENDING
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    total_scraped: int = 0
    total_saved: int = 0
    total_opportunities: int = 0
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
        # Wyślij historię eventów do nowego subskrybenta
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
            job_id = str(uuid.uuid4())[:8]
            job = HuntJob(job_id=job_id, config=config)
            self._current_job = job
            asyncio.create_task(self._run_job(job))
            logger.info("[JobManager] Job %s uruchomiony dla config: %s", job_id, config)
            return job

    async def _run_job(self, job: HuntJob):
        from backend.scraper_async import run_hunt_async
        from backend.analysis import enrich_listings
        from backend.db import save_listings, get_conn

        try:
            # ── FAZA 1: Scrapowanie ────────────────────────────────
            job.status = JobStatus.RUNNING
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
                    "portals_counts": job.portals_counts,
                })

            raw_listings = await run_hunt_async(job.config, progress_cb=portal_progress)
            job.total_scraped = len(raw_listings)
            job.emit("scraping_done", {
                "total_scraped": len(raw_listings),
                "portals_counts": job.portals_counts,
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

            # ── FAZA 2: Enrichment (RCN + scoring) ────────────────
            job.status = JobStatus.ENRICHING
            job.emit("status", {
                "status": job.status,
                "message": f"📊 Wzbogacam {len(raw_listings)} ofert (RCN + scoring)...",
            })

            city_slug = job.config.get("city_slug", "warszawa")
            # Enrichment jest synchroniczny i blokujący — puszczamy w executorze
            loop = asyncio.get_event_loop()
            enriched = await loop.run_in_executor(
                None,
                lambda: enrich_listings(raw_listings, city_slug=city_slug)
            )

            job.emit("enriching_done", {
                "total_enriched": len(enriched),
            })

            # ── FAZA 3: Zapis do DB ────────────────────────────────
            job.status = JobStatus.SAVING
            job.emit("status", {
                "status": job.status,
                "message": f"💾 Zapisuję {len(enriched)} ofert...",
            })

            saved = await loop.run_in_executor(None, lambda: save_listings(enriched))
            job.total_saved = saved

            # Policz okazje (score >= 0.25)
            min_score = job.config.get("min_score_alert", 0.25)
            job.total_opportunities = sum(
                1 for l in enriched if (l.get("score") or 0) >= min_score
            )

            job.emit("saving_done", {
                "total_saved": saved,
                "total_opportunities": job.total_opportunities,
                "min_score": min_score,
            })

            # ── FAZA 4: Kickoff AI queue dla top ofert ─────────────
            job.status = JobStatus.AI_QUEUE
            job.emit("status", {
                "status": job.status,
                "message": "🧠 Analiza AI w tle (wyniki pojawiają się na bieżąco)...",
            })

            # Triggeruj priorytetową analizę AI dla nowych ofert z tego joba
            asyncio.create_task(
                _priority_ai_analysis(job, enriched)
            )

            # ── DONE ───────────────────────────────────────────────
            job.status = JobStatus.DONE
            job.finished_at = time.time()
            elapsed = round(job.finished_at - job.started_at, 1)

            job.emit("done", {
                "total_scraped": job.total_scraped,
                "total_saved": saved,
                "total_opportunities": job.total_opportunities,
                "elapsed_s": elapsed,
                "portals_counts": job.portals_counts,
                "message": (
                    f"✅ Gotowe: {saved} ofert zapisanych, "
                    f"{job.total_opportunities} okazji, "
                    f"AI analiza w tle ({elapsed}s)"
                ),
            })

        except Exception as e:
            logger.exception("[JobManager] Błąd joba %s: %s", job.job_id, e)
            job.status = JobStatus.ERROR
            job.error = str(e)
            job.emit("error", {
                "error": str(e),
                "message": f"❌ Błąd: {e}",
            })


async def _priority_ai_analysis(job: HuntJob, enriched_listings: list[dict], batch_size: int = 20):
    """
    Priorytetowa analiza AI dla ofert z aktualnego joba.
    Przetwarza top oferty po score, emituje eventy do SSE.
    """
    from backend.db import get_listings_for_llm_analysis, save_llm_analysis
    from backend.nlp.llm_scorer import analyze_listing_with_llm

    # Pobierz świeże oferty z DB (mają już ID)
    listings_to_analyze = get_listings_for_llm_analysis(limit=batch_size)
    if not listings_to_analyze:
        return

    logger.info("[AI Priority] Analizuję %d ofert dla joba %s", len(listings_to_analyze), job.job_id)

    for listing in listings_to_analyze:
        try:
            analysis = await analyze_listing_with_llm(listing)
            if analysis and "error" not in analysis:
                save_llm_analysis(listing["url"], analysis)
                job.emit("ai_done", {
                    "listing_id": listing["id"],
                    "url": listing["url"],
                    "investment_score": analysis.get("investment_score"),
                    "condition": analysis.get("condition"),
                    "summary": (analysis.get("summary") or "")[:300],
                    "green_flags": analysis.get("green_flags", [])[:3],
                    "red_flags": analysis.get("red_flags", [])[:3],
                })
        except Exception as e:
            logger.warning("[AI Priority] Błąd dla listing %d: %s", listing.get("id", -1), e)

        await asyncio.sleep(2.0)  # rate limit Ollamy


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
                # Heartbeat żeby połączenie nie wygasło
                yield 'data: {"type":"heartbeat"}\n\n'
    finally:
        job.unsubscribe(q)
