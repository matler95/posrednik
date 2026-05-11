"""
Hunt Job Manager — zarządza aktywnym jobem polowania.
Jeden job na raz (inwestor ma jeden profil, jeden aktywny crawl).
Wyniki streamowane przez SSE do frontendu w czasie rzeczywistym.
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    ENRICHING = "enriching"
    AI_ANALYSIS = "ai_analysis"
    DONE = "done"
    ERROR = "error"


@dataclass
class HuntJob:
    job_id: str
    config: dict
    status: JobStatus = JobStatus.PENDING
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    total_found: int = 0
    total_saved: int = 0
    portals_done: list[str] = field(default_factory=list)
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
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        for event in self.events:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                break
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)


class HuntJobManager:
    """Singleton zarządzający aktualnym jobem polowania."""

    def __init__(self):
        self._current_job: HuntJob | None = None
        self._lock = asyncio.Lock()

    @property
    def current_job(self) -> HuntJob | None:
        return self._current_job

    async def start_job(self, config: dict) -> HuntJob:
        """Tworzy nowy job i uruchamia go w tle. Jeśli jest aktywny, anuluje go."""
        async with self._lock:
            job_id = str(uuid.uuid4())[:8]
            job = HuntJob(job_id=job_id, config=config)
            self._current_job = job
            asyncio.create_task(self._run_job(job))
            logger.info("[JobManager] Nowy job %s uruchomiony", job_id)
            return job

    async def _run_job(self, job: HuntJob):
        from backend.scraper_async import run_hunt_async
        from backend.analysis import enrich_listings
        from backend.db import save_listings

        try:
            job.status = JobStatus.RUNNING
            job.emit("status", {"status": job.status, "message": "Scrapowanie portali..."})

            async def progress_cb(portal_name: str, count: int):
                job.portals_done.append(portal_name)
                job.portals_counts[portal_name] = count
                job.total_found += count
                job.emit("portal_done", {
                    "portal": portal_name,
                    "count": count,
                    "total_found": job.total_found,
                })

            listings = await run_hunt_async(job.config, progress_cb=progress_cb)
            job.total_found = len(listings)
            job.emit("scraping_done", {"total_found": len(listings)})

            if not listings:
                job.status = JobStatus.DONE
                job.finished_at = time.time()
                job.emit("done", {"total_saved": 0, "message": "Brak ofert spełniających kryteria."})
                return

            # Instant enrichment (sync, ale szybkie — DB + calc)
            job.status = JobStatus.ENRICHING
            job.emit("status", {"status": job.status, "message": f"Wzbogacam {len(listings)} ofert..."})

            city_slug = job.config.get("city_slug", "warszawa")
            enriched = enrich_listings(listings, city_slug=city_slug)

            saved = save_listings(enriched)
            job.total_saved = saved
            job.emit("enriched", {"total_saved": saved})

            # Kick off AI analysis for top candidates (fire-and-forget)
            job.status = JobStatus.AI_ANALYSIS
            job.emit("status", {
                "status": job.status,
                "message": "Analiza AI w tle (oferty pojawiają się na bieżąco)...",
            })

            # Trigger AI queue processing in background
            asyncio.create_task(_process_ai_queue_for_job(job))

            job.status = JobStatus.DONE
            job.finished_at = time.time()
            elapsed = round(job.finished_at - job.started_at, 1)
            job.emit("done", {
                "total_saved": saved,
                "elapsed_s": elapsed,
                "message": f"Gotowe: {saved} ofert, analiza AI w tle.",
            })

        except Exception as e:
            logger.exception("[JobManager] Błąd joba %s: %s", job.job_id, e)
            job.status = JobStatus.ERROR
            job.error = str(e)
            job.emit("error", {"error": str(e)})


async def _process_ai_queue_for_job(job: HuntJob, batch_size: int = 20):
    """Przetwarza kolejkę AI dla top ofert z aktualnego joba."""
    from backend.db import get_listings_for_llm_analysis, save_llm_analysis
    from backend.nlp.llm_scorer import analyze_listing_with_llm

    listings = get_listings_for_llm_analysis(limit=batch_size)
    if not listings:
        return

    logger.info("[AI Queue] Analizuję %d ofert dla joba %s", len(listings), job.job_id)
    for listing in listings:
        try:
            analysis = await analyze_listing_with_llm(listing)
            if analysis and "error" not in analysis:
                save_llm_analysis(listing["url"], analysis)
                job.emit("ai_done", {
                    "listing_id": listing["id"],
                    "url": listing["url"],
                    "condition": analysis.get("condition"),
                    "investment_score": analysis.get("investment_score"),
                    "summary": analysis.get("summary", "")[:200],
                })
        except Exception as e:
            logger.warning("[AI Queue] Błąd dla listing %d: %s", listing.get("id", -1), e)
        await asyncio.sleep(0.5)


# Globalny singleton
hunt_manager = HuntJobManager()


async def stream_job_events(job: HuntJob) -> AsyncGenerator[str, None]:
    """
    Generator SSE — streamuje eventy joba do frontendu.
    Używać jako response body dla EventSource.
    """
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
                yield "data: {\"type\":\"heartbeat\"}\n\n"
    finally:
        job.unsubscribe(q)