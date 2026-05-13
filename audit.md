WREI Real Estate AI — Complete Technical Audit

1. Executive Summary
WREI is a real estate opportunity hunter built on FastAPI + PostgreSQL + Redis/ARQ + React/Vite, targeting the Warsaw apartment market. The concept is solid and the codebase shows genuine engineering effort. However, the system has multiple production-blocking issues that would cause silent data loss, score corruption, queue stalls, and security exposure in a real deployment. The overall architecture is mid-prototype — functional for personal use on a single machine, but not production-ready.
Overall Production Readiness: 3.5/10
Key findings at a glance:

No authentication on any API endpoint (public write access)
eval() used in alert evaluator with insufficient sandboxing
Scheduler and ARQ worker run duplicate cron jobs simultaneously
RCN historical import has no resumability or progress checkpointing
Score formula uses market_position from the same batch being scored (data leakage)
DB connection pool is not returned on exception in many paths
Frontend has no error boundaries, no real empty states, no mobile layout
AI prompt template references {condition_hint} and {floor_info} but these are never injected
Photo analysis pipeline is architecturally decoupled from scoring but score is written before photos are analyzed


2. Architecture Overview
Browser → Nginx → Frontend (Vite/React)
                → Backend (FastAPI, port 8000)
                    ├── Scrapers (sync, per-portal)
                    ├── Enrichment (analysis.py → model.py)
                    ├── NLP (Ollama qwen2.5)
                    ├── CV (Ollama moondream + CLIP)
                    ├── Alerts (Telegram)
                    └── DB layer (psycopg2 pool)
                → Worker (ARQ/Redis)
                    └── Cron jobs (duplicate of scheduler.py)
PostgreSQL ←────────────────────────────────────────┘
Redis ←─────────────────────────────────────────────┘
Ollama (host) ← accessed via host.docker.internal
The architecture has a fundamental split-brain problem: backend/scheduler.py (APScheduler running inside FastAPI) and backend/tasks.py (ARQ worker crons) define overlapping schedules. Both will fire simultaneously in a docker-compose up deployment.

3. Critical Issues
C1 — No Authentication on Any Endpoint
Severity: CRITICAL | Probability: 100% exploitable | Location: backend/main.py, all routers
Every API endpoint — including POST /hunt/start, POST /set-hunt-config, POST /market/ingest, POST /listings/{id}/analyze — is completely open. Anyone who can reach port 80 can trigger unlimited scraping jobs, modify hunt configuration, queue Ollama analysis tasks, or read all stored listings.
Fix: Add FastAPI dependency with API key or JWT validation on all mutating endpoints minimum. Use APIKeyHeader for internal tools:
pythonfrom fastapi.security import APIKeyHeader
API_KEY = os.getenv("WREI_API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_key(key: str = Depends(api_key_header)):
    if key != API_KEY:
        raise HTTPException(403)

C2 — eval() with Insufficient Sandbox in Alert Evaluator
Severity: CRITICAL | Probability: High if Telegram alerts are configured | Location: backend/alerts/evaluator.py:64
pythonreturn bool(eval(condition_expr, {"__builtins__": {}}, context))
The FORBIDDEN_PATTERNS regex check is bypassable. Python's {"__builtins__": {}} sandbox has been broken for years. Examples of bypass:
python# Bypasses all regex checks:
score.__class__.__mro__[1].__subclasses__()
().__class__.__bases__[0].__subclasses__()[104](['rm','-rf','/'])
SAFE_NAMES is never actually enforced in the eval — it's only a comment/documentation. The code checks patterns in the string but doesn't restrict the namespace to only those names.
Fix: Use asteval library or rewrite conditions as a structured filter object (JSON schema with explicit field comparisons) rather than arbitrary Python expressions.

C3 — Scheduler + ARQ Worker Both Fire Cron Jobs
Severity: CRITICAL | Probability: 100% in docker-compose | Location: backend/scheduler.py + backend/tasks.py + backend/main.py
backend/main.py calls startup() which would start APScheduler if integrated (it's imported in scheduler.py). backend/tasks.py:WorkerSettings defines cron_jobs for ARQ. In the current docker-compose.yml, both backend and worker services run. The backend service uses uvicorn backend.main:app — main.py does NOT currently call start_scheduler(), but the import exists and scheduler.py is ready to be activated.
However, the immediate critical issue is that tasks.py schedules:

crawl_all_sources_task at 6,12,18h
process_llm_queue_task every 10 minutes
check_alerts_task every 15 minutes

If start_scheduler() is ever called (it's one line away), every job runs twice simultaneously, causing duplicate scrapes, duplicate DB writes, and doubled Ollama load.
Fix: Remove scheduler.py entirely. Use ARQ exclusively for all scheduling. Delete the APScheduler dependency.

C4 — DB Connection Pool Leak on Exception
Severity: CRITICAL | Probability: High under any error condition | Location: backend/data/connection.py, all get_conn() callers
PooledConnectionWrapper returns connections to the pool in close() and __exit__(). However, the vast majority of callers do:
pythonconn = get_conn()
cur = conn.cursor()
cur.execute(...)  # if this raises, conn is never returned
conn.close()
There's no try/finally in any of the 30+ database functions in backend/data/listings.py, stats.py, transactions.py, etc. A single DB exception will leak a connection permanently. With maxconn=10, ten errors exhaust the pool and the application hangs.
Fix: Use context manager pattern everywhere:
pythonwith get_conn() as conn:
    cur = conn.cursor()
    ...
PooledConnectionWrapper.__exit__ already handles rollback + return. Audit all 30+ call sites.

C5 — Score Data Leakage: group_average_price_per_sqm Uses Current Batch
Severity: CRITICAL for scoring integrity | Location: backend/model.py:group_average_price_per_sqm, backend/analysis.py:enrich_listings
pythonaverages = group_average_price_per_sqm(listings)  # computed from THIS batch
# then used as benchmark for scoring THIS batch
listing["market_position"] = market_position(listing, averages)
The "market position" component (weight 0.15) is computed relative to the average of the listings being scored right now. This means:

If you scrape 5 expensive listings, all score lower
If you scrape 5 cheap listings, all score higher
Scores are not comparable across different scrape runs
A listing's score changes every time it's re-evaluated with a different batch

Fix: market_position must use pre-computed market_stats from the DB, not the current batch average.

4. High Priority Problems
H1 — AI Prompt Template Has Unformatted Placeholders
Severity: HIGH | Location: backend/nlp/llm_scorer.py:PROMPT_TEMPLATE and _build_prompt()
The template contains {condition_hint} and {floor_info} as format keys, but _build_prompt() computes floor_info and condition_hint as local variables and passes them to .format(). However, the PROMPT_TEMPLATE string at module level is:
pythonPROMPT_TEMPLATE = """\
...
Data:
Title: {title} | District: {district}
Price: {price} PLN | Area: {area} m2 | Rooms: {rooms} | Price/m2: {price_per_m2}
RCN Benchmark: {rcn_benchmark} | CAGR 5y: {cagr_pct}% | Gap: {transaction_gap_pct}% ({transaction_gap_sign})
Desc: {description}"""
{condition_hint} and {floor_info} appear in the docstring/comment but are computed and then never inserted — the template doesn't contain them. The LLM receives no condition or floor information. This means the AI cannot assess renovation needs or floor desirability.
Fix: Add | Condition: {condition_hint} | Floor: {floor_info} to the template string.

H2 — save_listings Writes Score BEFORE Photo Analysis
Severity: HIGH | Location: backend/data/listings.py:save_listings, backend/cv/vision_scorer.py
The enrichment pipeline in analysis.py sets photo_score=0 for all new listings (since photos aren't analyzed yet), saves to DB with this zero score, then later the vision queue updates photo_analysis but does NOT recalculate score. The composite score in DB permanently reflects photo_score=0 even after photos are analyzed.
save_photo_analysis() only updates photo_analysis column, not score or photo_score.
Fix: After save_photo_analysis(), trigger a score recalculation:
pythondef save_photo_analysis(listing_id, analysis):
    ...
    # also update photo_score and recalculate total score
    new_photo_score = analysis.get("photo_score", 0)
    update_listing_score_with_photo(listing_id, new_photo_score)

H3 — ARQ Redis Pub/Sub Used for SSE but Never Cleaned Up
Severity: HIGH | Location: backend/hunt_manager.py:stream_job_events
pythonpubsub = redis_conn.pubsub()
await pubsub.subscribe(channel_name)
# ...
while True:
    message = await pubsub.get_message(timeout=30.0)
If the client disconnects (browser tab closed), the finally block does unsubscribe, but redis_conn (a full ARQ pool) is never properly closed in all exit paths. More critically, if the job never publishes a done/error event (worker crash), this coroutine loops forever on heartbeats, one per 30 seconds, holding an open Redis connection per connected client indefinitely.
Fix: Add a maximum timeout (e.g. 10 minutes) and use asyncio.timeout(). Use aioredis directly for pub/sub rather than the ARQ pool.

H4 — initial_rcn_load Checks Count But Doesn't Handle Partial Loads
Severity: HIGH | Location: backend/scheduler.py:initial_rcn_load
pythonif count > 1000:
    logger.info("[RCN] Baza zawiera %d rekordów — pomijam initial load", count)
    return
If a previous import loaded 1001 records and then crashed, the system skips the load entirely. There's no concept of "which date ranges have been loaded." A partial import covering only the last 30 days will permanently block the full historical import.
Fix: Track loaded date ranges in a dedicated table rcn_import_checkpoints(city_slug, date_from, date_to, status).

H5 — domiporta.py Calls normalize_listing From Its Own Module (Circular)
Severity: HIGH | Location: backend/scrapers/domiporta.py:search()
pythonfrom backend.scrapers.domiporta import normalize_listing  # istniejąca funkcja
normalize_listing is not defined anywhere in domiporta.py. This import will raise ImportError at runtime whenever __NEXT_DATA__ is found on Domiporta pages. The scraper silently falls through to HTML parsing only.
Fix: Define normalize_listing in domiporta.py or remove the branch and use only HTML parsing.

H6 — hunt_manager.py Returns a Dataclass with No Actual Job Tracking
Severity: HIGH | Location: backend/hunt_manager.py:start_job
python@dataclass
class SimpleJob:
    job_id: str
    status: str
return SimpleJob(job_id=job_id, status=JobStatus.PENDING)
The job is enqueued in ARQ but the returned object has no connection to the actual job state. hunt_manager.current_job always returns None. The /hunt/job/{job_id} endpoint falls through to DB lookup, which only works after the worker writes to hunt_jobs table — which has a race condition: the HTTP response returns before the worker writes the initial status, so a rapid status poll returns 404.

H7 — PooledConnectionWrapper Registered JSONB Per-Connection
Severity: HIGH | Location: backend/data/connection.py:PooledConnectionWrapper.__init__
pythonregister_default_jsonb(self.conn)
register_default_jsonb is called every time a connection is checked out from the pool. This is harmless on first call but may cause unexpected behavior if connections are reused and the type registration accumulates. More importantly, this is an expensive operation called on every single DB query. It should be called once after pool creation.

5. Medium Priority Problems
M1 — Scraper search() in scraper.py Doesn't Call enrich_listings
The search() function returns raw unenriched listings. Only search_and_enrich() does enrichment. The scheduler's crawl_all_sources() calls search() then save_listings() — so listings saved by the scheduler cron have no score, no RCN benchmark, no market_position. The ARQ worker's run_hunt_job_task uses run_hunt_async + enrich_listings separately, which is correct. The two code paths produce different quality data silently.
Location: backend/scheduler.py:crawl_all_sources

M2 — calculate_preliminary_score Has Dead Code Path for Fresh Installs
Location: backend/model.py:calculate_preliminary_score
pythonis_fresh_install = (not ml_estimate or ml_estimate <= 0) and not effective_benchmark
if is_fresh_install:
    proxy_val = max(0.0, market_pos_val)
    price_gap = proxy_val
    txn_gap_pos = proxy_val
When both ML estimate and RCN benchmark are absent (new installation, no data), price_gap and txn_gap_pos are both set to market_pos_val — which is itself computed from the batch average (see C5). This means the score double-counts the market position signal with weights 0.35 + 0.30 + 0.15 = 0.80 of the total score from a single noisy signal.

M3 — CLIP Model Downloaded at Runtime Inside Docker
Location: backend/cv/clip_filter.py:_load_model
python_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
This downloads ~600MB from HuggingFace on first use, inside the running container. No caching is configured. Container restarts re-download. In a network-restricted environment or with HuggingFace rate limits, this fails silently (returns True for all images — passthrough).

M4 — record_scrape_run References portals Table That May Not Exist at Start
Location: backend/data/scrapes.py:record_scrape_run
The portals table is created in migration 001 but _register_portals in init_db runs after migrations. If a scrape job fires before init_db completes (race condition at startup), the FK constraint portal TEXT REFERENCES portals(name) causes the insert to fail silently (it's not in a try/except at the call site in scheduler).

M5 — LLM Queue Semaphore Hardcoded to 3 Concurrent Requests
Location: backend/nlp/llm_scorer.py:run_llm_queue_once
pythonsemaphore = asyncio.Semaphore(3)
Ollama runs locally and is single-threaded for inference. Sending 3 concurrent requests causes queuing inside Ollama, increases memory pressure, and provides no throughput benefit over sequential processing. With a 7B model on CPU, each request takes 20-60 seconds. Three concurrent requests cause timeout cascades.
Fix: Set semaphore to 1 for CPU-based Ollama. Make it configurable via env var.

M6 — transaction_gap_ratio Clamps at -0.5 But Not Documented
Location: backend/model.py:transaction_gap_ratio
A listing priced 200% above the RCN benchmark returns -0.5 (clamped), same as one priced 60% above. The score breakdown shows -50% for both, misleading the user. The clamping silently hides extreme overpricing.

M7 — get_hunt_listings SQL Uses hunt_config WHERE id = 1 Hardcoded
Location: backend/data/listings.py:get_hunt_listings
sqlWITH cfg AS (SELECT config FROM hunt_config WHERE id = 1)
If the hunt_config table has no rows (fresh install before any config save), the CTE returns empty, the CROSS JOIN produces no results, and get_hunt_listings returns an empty list with no error. The frontend shows "no listings" even if 10,000 listings exist in DB.

M8 — scraper_utils.fetch_html Saves Debug HTML for Every Request
Location: backend/scraper_utils.py:fetch_html
pythondef fetch_html(url, portal="default", timeout=20.0):
    ...
    if html:
        save_debug_html(url, portal, html)
    else:
        _save_debug(url, portal, b"[EMPTY RESPONSE]")
Every single HTTP request writes a file to debug_scrapers/. At 3 portals × 3 pages × 25 listings = 225 files per scrape run, this fills disk over time. There's no cleanup mechanism. This is debug code accidentally shipped to production.

M9 — listing_history Insert Doesn't Use ON CONFLICT
Location: backend/data/listings.py:save_listing_history
Every call to save_listings also calls save_listing_history with all listings. This inserts a new history row every time, including when nothing changed. For a listing unchanged across 100 scrape runs, 100 identical history rows are inserted. The listing_history table will grow unboundedly.

M10 — Frontend API Base URL Hardcoded Fallback to /api
Location: frontend/src/api/client.js
jsconst BASE = import.meta.env.VITE_API_URL || '/api';
The nginx config proxies /api/ to http://backend:8000/. But FastAPI routers have no /api prefix — routes are /listings, /hunt/start, etc. The nginx strips the /api/ prefix in proxy_pass http://backend:8000/. This works, but if the frontend is run outside Docker (dev mode), VITE_API_URL must be set to http://localhost:8000 — not /api. The vite.config.js has no proxy configured for development, so dev mode API calls will fail with 404.

6. Low Priority Improvements

L1: backend/find_path.py is a debug script committed to the repository and imported nowhere. Remove it.
L2: alerts/telegram_bot.py (root level) is unused — a duplicate of backend/alerts/channels.py. Remove.
L3: backend/test_integration.py references run_hunt_async with a pages_per_portal parameter that doesn't exist in the function signature. The test will fail immediately.
L4: backend/scrapers/gratka.py and morizon.py are commented out in __init__.py but still present. Either delete or document why they're disabled.
L5: _RCN_CACHE in trend_analyzer.py is a module-level dict with no TTL. Stale RCN data persists for the entire process lifetime.
L6: condition_multiplier in model.py returns 0.92 for unknown condition, silently penalizing listings with no condition data.
L7: The walkthrough.md references Streamlit dashboard which has been removed. Documentation is stale.
L8: requirements.txt includes python-telegram-bot but the code uses raw httpx for Telegram. Unnecessary dependency.
L9: No .env.example validation — missing required vars (e.g. empty TELEGRAM_TOKEN) cause silent feature degradation rather than startup failure.
L10: frontend/vite.config.js missing server.proxy for development, making local development without Docker impossible.


7. Backend Audit
Structure & Modularization
The backend/data/ split (connection, listings, alerts, transactions, hunt, scrapes, stats, cache) is well-conceived but backend/db.py re-exports everything via from backend.data.X import *. This star-import pattern makes it impossible to know what's available in db namespace without reading all submodules, breaks IDE autocomplete, and creates implicit dependencies.
API Design

No versioning (/v1/ prefix)
No request validation models (Pydantic) on POST /hunt/start — body: dict accepts anything
/set-hunt-config accepts config: dict with no schema validation — malformed configs silently break scoring
/market/ingest and /market/ingest-history create ARQ pool connections on every request rather than using a shared pool

Error Handling
Across all API endpoints, errors propagate as unhandled 500s with full Python tracebacks exposed to the client. No global exception handler is registered. FastAPI default behavior returns the exception message in the response body.
Logging
Logging is configured per-module with logger = logging.getLogger(__name__) but no root logger configuration is set in main.py. Log level, format, and handler depend on uvicorn defaults. In production, structured JSON logging is absent.
Concurrency & Async
The scraper functions are all synchronous (fetch_html uses httpx.Client, not AsyncClient). They're called via asyncio.to_thread in the ARQ worker, which is correct. However, the FastAPI endpoints that call scrapers directly (e.g. legacy /run-crawl) block the event loop.
Memory
The _RCN_CACHE dict in trend_analyzer.py and the _LATEST_MODEL/_LATEST_META in ml/predictor.py are module-level globals. In a multi-worker uvicorn deployment, each worker has its own copy. RCN cache grows per-worker with no eviction. ML model is loaded per-worker.
Configuration Management
All configuration is via environment variables with no validation layer. Missing REDIS_HOST defaults to localhost, which fails in Docker where Redis is at hostname redis. The .env.example shows POSTGRES_HOST=db but code defaults to db — this is correct for Docker but wrong for local development.

8. Scraping Audit
Otodom
The extract_json_payload function correctly targets __NEXT_DATA__. However:

Three regex patterns tried in sequence — the first works, the others are dead code
_extract_district returns "Warszawa" as hardcoded fallback instead of None, polluting district filters
_extract_price iterates candidates but the regularPrice key doesn't exist in Otodom's structure
Images: {width} and {height} template replacement is hardcoded to 800x600 — Otodom may change this URL format

OLX

_find_listings_in_payload tries three lambda paths, which is good
_normalize_olx_listing: price_obj.get("value", {}) — if value is an integer, .get() fails with AttributeError. This is a silent crash caught by return None
District extraction: district_obj = location.get("district") or {} — if district_obj is a string (which it sometimes is on OLX), the code does district = district_obj.get("name") which raises AttributeError

Location: backend/scrapers/olx.py:_normalize_olx_listing
pythondistrict_obj = location.get("district") or {}
if isinstance(district_obj, dict):
    district = district_obj.get("name") or district  # correct
elif isinstance(district_obj, str) and district_obj:
    district = district_obj  # correct
Actually this path is handled correctly — false alarm here. But the price extraction is not.
Domiporta

_try_next_data tries to find items key in pageProps but Domiporta doesn't use Next.js — this always returns empty
_parse_html_cards selectors are guesses — article.sneaky-link is not a real Domiporta class
The normalize_listing import (see H5) causes ImportError in the __NEXT_DATA__ branch

Gratka / Morizon
Both disabled in __init__.py for 403 errors. The session-based fetch (fetch_html_with_session) establishes a session and visits homepage, but doesn't handle CSRF tokens or cookie-based anti-bot systems. Both portals use Cloudflare — raw httpx will be blocked immediately.
Anti-Bot Handling

User-Agent rotation: 7 UAs, all Chrome/Firefox — no Safari mobile, no curl variants
No cookie persistence across requests within a scraping session
No JavaScript rendering (no Playwright/Selenium)
Otodom specifically uses dynamic rendering for some content — __NEXT_DATA__ may be absent on bot-detected requests, silently returning 0 listings
No proxy pool configured anywhere
Rate limiting is per-portal but resets on process restart

Deduplication
deduplicate_listings in scraper_utils.py deduplicates by URL within a batch, and save_listings uses ON CONFLICT (url) DO UPDATE. This is correct. However, OLX listings sometimes change URLs between runs (promotional vs standard URL), causing duplicate records with different URLs but identical content.

9. Deweloperuch Import Audit
Current Implementation
iter_transactions in deweloperuch.py is the core generator. It:

Uses proper pagination with totalPages from API response
Has exponential backoff for 429/500 errors
Normalizes records with regex-based district extraction

Critical Issues
No Resumability: If the import crashes on page 847 of 2000, the next run starts from page 1. There is no checkpoint mechanism. A full 5-year import generates ~200,000+ records across ~2000+ API pages at 50 per page. A single crash wastes hours of progress.
No Date-Range Chunking: The fetch_historical(years=5) function issues one continuous paginated request for all 5 years. This is fragile — a single network interruption restarts everything. The API supports filterDateFrom/filterDateTo which enables chunked imports.
Rate Limit: 1.2s Between Pages: For 2000 pages, this is 2000 × 1.2s = 40 minutes minimum. With retries and network variance, realistically 2-4 hours for a full 5-year import. No parallelization is attempted (though parallelizing by city or year-range would be safe).
District Coverage: Regex patterns cover ~85% for Warsaw. The remaining ~15% with district=NULL silently degrades RCN benchmark accuracy for those districts (they fall through to city-wide median, which is less precise for scoring).
TERYT Code Matching: The WARSAW_TERYT_MAP in deweloperuch.py maps 6-digit codes to districts. The check is if rec_name.startswith("1465") — correct for Warsaw (TERYT 1465), but rec_name is record.get("name") which is a full investment name string, not a TERYT code. This check will match any investment name starting with "1465" as a string, which is not a TERYT code. This entire branch is broken and never works.
Location: backend/scrapers/deweloperuch.py:_normalize
pythonrec_name = record.get("name") or ""
if city_slug == "warszawa" and rec_name.startswith("1465"):
    teryt = rec_name[:6]
    district = WARSAW_TERYT_MAP.get(teryt)
record.get("name") returns the investment name like "Osiedle Wilanów Premium", not "146515". This condition never triggers.
Full Historical Import Strategy (Q1 2019 → Today)
Ideal Architecture:
1. Create checkpoint table:
   CREATE TABLE rcn_import_jobs (
     id SERIAL PRIMARY KEY,
     city_slug TEXT,
     date_from DATE,
     date_to DATE,
     status TEXT, -- pending/running/done/failed
     pages_total INT,
     pages_done INT,
     records_saved INT,
     started_at TIMESTAMP,
     finished_at TIMESTAMP,
     error TEXT
   );

2. Generate monthly chunks from 2019-01-01 to today:
   [(2019-01, 2019-01-31), (2019-02, 2019-02-28), ...]
   = ~77 months × 1 city = 77 jobs

3. Process each chunk sequentially with:
   - 1.2s between API pages
   - Retry with exponential backoff
   - Checkpoint after each page (update pages_done)
   - Mark job 'done' on completion
   - On restart: skip 'done' jobs, resume 'running' from last page

4. Validate completeness:
   SELECT date_trunc('month', creation_date), COUNT(*)
   FROM transaction_prices
   WHERE city_slug = 'warszawa'
   GROUP BY 1 ORDER BY 1;
   -- Compare with expected counts from Deweloperuch total field

5. Backfill missing months detected by gap analysis
Implementation:
pythonasync def import_rcn_history_chunked(ctx, city_slug: str, start_year: int = 2019):
    from datetime import date
    from dateutil.relativedelta import relativedelta
    
    # Generate monthly chunks
    start = date(start_year, 1, 1)
    end = date.today()
    chunks = []
    current = start
    while current < end:
        next_month = current + relativedelta(months=1)
        chunks.append((current.isoformat(), min(next_month, end).isoformat()))
        current = next_month
    
    for date_from, date_to in chunks:
        # Check if already done
        existing = get_checkpoint(city_slug, date_from, date_to)
        if existing and existing['status'] == 'done':
            continue
        
        job_id = create_checkpoint(city_slug, date_from, date_to)
        try:
            batch = []
            page = get_last_page(job_id) or 1
            
            for tx in iter_transactions(city_slug, date_from, date_to, start_page=page):
                batch.append(tx)
                if len(batch) >= 500:
                    save_transaction_prices(batch)
                    update_checkpoint_progress(job_id, page)
                    batch = []
                    await asyncio.sleep(0)  # yield to event loop
            
            if batch:
                save_transaction_prices(batch)
            
            mark_checkpoint_done(job_id)
        except Exception as e:
            mark_checkpoint_failed(job_id, str(e))
            raise  # ARQ will retry the task
Speed vs Reliability Trade-off:

Sequential monthly chunks: ~77 jobs × ~20 pages each × 1.2s = ~31 minutes total (Warsaw only)
Parallel city imports: multiply workers by city count, each gets own Redis queue
Do NOT parallelize within a city — Deweloperuch API likely rate-limits by IP


10. Database Audit
Schema Quality
Missing constraints:

listings.price has no CHECK (price > 0) constraint — negative prices can be stored
listings.area has no CHECK (area > 0) constraint
transaction_prices.amount_sqm has no CHECK (amount_sqm > 500) — nonsense values possible
watchlist.condition_expr has no length limit — very long expressions waste evaluation time

Missing indexes:

listings(city_slug, score DESC) — queries filter by city and sort by score frequently but no composite index exists
listings(llm_analysis) with WHERE llm_analysis IS NULL — LLM queue query does full table scan with partial condition
alert_sent_log(sent_at) exists but (listing_id, watchlist_id) is the PK — the deduplication query WHERE listing_id = %s AND watchlist_id = %s uses PK lookup correctly
transaction_prices(city_slug, year, quarter, district) — the get_rcn_benchmark query uses district, rooms_number, size with a date range — no index covers this combination

Recommended missing index:
sqlCREATE INDEX idx_listings_llm_queue ON listings(score DESC)
  WHERE llm_analysis IS NULL AND (llm_error_count IS NULL OR llm_error_count < 3);

CREATE INDEX idx_tp_benchmark_lookup ON transaction_prices(city_slug, district, year, quarter, rooms_number, size);
Normalization Issues
listings.rooms is stored as TEXT — values can be "1", "2", "ONE", "TWO", null. The hunt config stores rooms as JSON array of strings ["2", "3"]. Comparison in SQL:
sqll.rooms::TEXT = ANY(ARRAY(SELECT jsonb_array_elements_text(cfg.config->'rooms')))
This breaks if rooms contains "TWO" instead of "2" (OLX returns text codes). The normalization should happen at ingestion time.
Transactional Integrity
save_listings calls execute_values then separately calls save_listing_history. These are in separate transactions. If save_listing_history fails, listings are saved but history is not — inconsistency. The outer try/except in save_listings logs a warning but doesn't roll back the listing save.
Migration Quality
Migrations 002 onwards use ALTER TABLE ... ADD COLUMN IF NOT EXISTS which is safe. However:

Migration 004 inserts sample watchlist rows with ON CONFLICT DO NOTHING — but watchlist has no unique constraint defined, so ON CONFLICT DO NOTHING on no unique column causes a syntax error in PostgreSQL
Migration 007 adds UUID PRIMARY KEY to hunt_jobs but the id column in the save_hunt_job function is passed as a string UUID — this works but no UUID type validation exists


11. AI Evaluation Audit
Prompt Quality
The prompt requests JSON output with specific keys but:

Doesn't specify all expected keys (condition, investment_score, negotiation_potential, green_flags, red_flags, urgency_signals, summary, location_quality)
The example JSON only shows three fields
No examples of valid green_flags or red_flags are provided
qwen2.5:7b will hallucinate field names inconsistently

Missing from prompt:

Output format specification (valid JSON only, no markdown)
Field type specifications (arrays must be arrays, not strings)
Range specifications (investment_score: 1-10 integer)

Hallucination Risk
The prompt includes Desc: {description} truncated to 1500 characters. For listings with:

Empty description: the LLM invents details from title/district alone
Non-Polish description: the LLM may switch language
HTML in description (not stripped): confuses the model

No output validation beyond isinstance(result, dict). A response like {"summary": 42, "investment_score": "high", "green_flags": "metro nearby"} passes validation but breaks downstream consumers expecting typed values.
Scoring Stability
The text_score_from_llm function:
pythoninvestment = float(llm_analysis.get("investment_score") or 5) / 10
negotiation = float(llm_analysis.get("negotiation_potential") or 5) / 10
Default of 5 for missing fields means 50% text score even with no analysis. Combined with opportunity_score adding text_score * 0.08, listings never analyzed by LLM get a free +4% score boost from the default. This biases scores upward for un-analyzed listings.
Fix: Default should be None for unanalyzed fields, with text_score = 0 when llm_analysis is None.
Photo Analysis Pipeline
moondream is a 1.7GB model running on CPU. At 4 images per listing × 180s timeout per image, a single listing takes up to 12 minutes of photo analysis. The process_photo_queue runs every 15 minutes with batch_size=3. This means photo analysis throughput is ~3 listings per 15 minutes = 12/hour. A database with 10,000 listings would take 833 hours (34 days) to analyze fully.
The CLIP pre-filter downloads openai/clip-vit-base-patch32 (~600MB) on first use with no HuggingFace token configured. In air-gapped or rate-limited environments, this fails silently (passthrough mode — all images accepted).
Reproducibility
No temperature is set in the Ollama API call:
pythonjson={
    "model": MODEL,
    "messages": [...],
    "stream": False,
    "format": "json",
}
Ollama uses temperature=0.8 by default. The same listing analyzed twice will produce different scores. For a scoring system, temperature should be 0.

12. Queueing Audit
ARQ Configuration
WorkerSettings in tasks.py is well-structured. However:
No retry policy defined:
pythonclass WorkerSettings:
    functions = [run_hunt_job_task, ...]
    # No max_tries, no retry_delay
ARQ default is max_tries=5 with no delay. A failing run_hunt_job_task will be retried 5 times immediately, causing 5 duplicate hunt runs.
Fix:
python@job(max_tries=1)  # Hunt jobs should not retry automatically
async def run_hunt_job_task(ctx, job_id, config):
    ...
Dead Letter Handling
No dead letter queue configured. Failed jobs disappear from ARQ's queue after max_tries exhausted. There's no audit trail of failed jobs beyond what was written to hunt_jobs table before the failure.
Idempotency
run_hunt_job_task is not idempotent. If retried with the same job_id, it:

Overwrites the hunt_jobs record via ON CONFLICT
Re-scrapes all portals
Re-saves all listings (idempotent via ON CONFLICT (url))
Re-analyzes with LLM (skipped if llm_analysis IS NOT NULL)

Point 2-3 are acceptable. But re-scraping with the same job_id creates confusing audit logs.
process_llm_queue_task Concurrency
The LLM queue task is scheduled every 10 minutes with semaphore=3 internally. If processing 10 listings takes 15 minutes, the next cron fires while the previous one is still running. ARQ will run two instances simultaneously, both competing for Ollama and the same DB rows. No locking prevents this.
Fix: Use ARQ's unique=True job option or implement advisory locking.
SSE Stream Architecture
The SSE stream (stream_job_events) uses Redis Pub/Sub correctly for real-time events. However, events published by the worker before the frontend connects are lost — there's no event replay/history. If the browser connects 5 seconds after a job starts, it misses the initial status events and the progress bar starts from an unknown state.
Fix: Persist events to a Redis list with TTL, replay on connect.

13. Frontend UX Audit
Information Architecture
The sidebar has 4 items: Polowanie, Statystyki, Alerty, Konfiguracja. "Polowanie" is both the main page and the entry point — reasonable. However:

"Alerty" shows historical triggered alerts, not alert configuration — the naming is confusing
No way to configure watchlist alerts from the frontend (only pre-seeded SQL rows in migration 004)
No user onboarding — a fresh install shows "Brak ofert" with no guidance

Hunt Page (Hunt.jsx)
At ~750 lines, Hunt.jsx is a monolithic component. ListingCard, ScorePill, ScoreBreakdown, AIFlags, StatCard, StickyBar, DataQualityBanner are all defined in the same file. This makes testing and maintenance extremely difficult.
Score presentation:

Score displayed as integer 0-100 with a label ("Okazja"/"Dobra") — good
Score bar uses green/amber/gray — accessible
But: no explanation of what "score" means anywhere in the UI. A user seeing "42 Dobra" has no idea if that's good or why

Filter UX:

Sort buttons and filters are in a sticky bar — good
But filterDistrict state resets on page navigation (no URL params)
The "Tylko okazje (≥25%)" checkbox and minScore state manipulation is fragile — setMinScore(e.target.checked ? 0.25 : null) means unchecking always resets to null (no score filter), not to whatever it was before

Loading States

Initial load shows 3 skeleton cards — adequate
While hunting, listings.length === 0 shows the empty state card even though a hunt is running — confusing
No progress percentage shown during enrichment phase
AI analysis shows "Analiza AI..." with a spinner icon but uses a CSS spin animation via style string instead of Tailwind animate-spin

Mobile Usability

Layout.jsx uses a fixed 220px sidebar with marginLeft: 220 on main content — completely broken on mobile (< 768px viewport)
ListingCard in Hunt.jsx uses fixed widths (width: 190) for the image — overflows on narrow screens
No @media queries anywhere in index.css for responsive layout
No viewport meta tag adjustment for mobile

Accessibility

All icon-only buttons (<MapIcon />, sort buttons) have no aria-label
Color-only score indication (green/amber/gray) has no text alternative for colorblind users
Input fields in Settings.jsx use Tailwind classes that don't set <label for=""> relationships
<select> in Stats.jsx has no <label>

Error Handling
No React error boundaries. A single component throwing (e.g. malformed listing.score_components) crashes the entire Hunt page with a white screen. No error state in any useEffect — errors are logged to console only.
Recharts in Stats.jsx
javascriptfunction cn(...inputs) {
  return inputs.filter(Boolean).join(' ');
}
The cn helper is reimplemented inline in Stats.jsx instead of using the clsx package that's already in package.json. Minor but indicates copy-paste development.

14. Security Audit
Critical Security Issues
S1 — No Authentication (See C1)
S2 — eval() Sandbox Bypass (See C2)
S3 — SSRF via market/geocode-missing and Nominatim
backend/api/market.py calls batch_geocode_missing which calls geocode_address which uses Nominatim with the street address from the DB. If an attacker inserts a listing with street_address = "http://internal-service/admin" (via the scraper pipeline or direct DB manipulation), the geocoder will make requests to that address. The httpx.get call in geocoder.py follows redirects and has no allowlist for domains.
Fix: Validate that geocoding queries contain only street address patterns before sending to Nominatim.
S4 — Photo Download SSRF
cv/fetcher.py downloads images from URLs stored in the images JSONB column. A scraper-injected listing could have images: ["http://169.254.169.254/latest/meta-data/"] (AWS metadata endpoint). The fetch_image function follows redirects with no allowlist.
Fix:
python# Validate URL before downloading
from urllib.parse import urlparse
allowed_domains = {"*.otodom.pl", "*.olx.pl", ...}
parsed = urlparse(url)
if not any(parsed.netloc.endswith(d) for d in ALLOWED_DOMAINS):
    raise ValueError(f"Untrusted image domain: {parsed.netloc}")
S5 — Secrets in docker-compose.yml
yamlPOSTGRES_PASSWORD: postgres
Hardcoded credentials in docker-compose.yml committed to repository. If this repo is public, the DB password is exposed. No .env file usage for secrets in compose.
S6 — Debug HTML Files May Contain Scraped PII
save_debug_html saves full HTML responses to debug_scrapers/. Otodom and OLX pages contain user profile data, phone numbers, and location data of listing owners. These files are written to the container's filesystem with no encryption or access control.
S7 — Telegram Token in Logs
backend/alerts/channels.py constructs the Telegram API URL as:
pythonurl = TELEGRAM_API.format(token=TELEGRAM_TOKEN)
If this URL is logged (e.g. in an exception traceback from httpx), the bot token is exposed in logs. The TELEGRAM_API template includes the token in the path.
S8 — No Rate Limiting on API Endpoints
POST /hunt/start can be called unlimited times, each triggering a full scraping job. This allows resource exhaustion attacks. No rate limiting middleware is configured.

15. Scalability Assessment
Component | Current Capacity | Bottleneck | Notes
Scraping throughput | ~200 listings/run | Rate limiter (portal delays) | Correct by design
LLM analysis~12/hourSingle Ollama CPU instanceScales with GPU
Photo analysis | ~12 listings/hour | Moondream + CLIP on CPU | GPU needed
DB connections | Max 10 (pool) | No connection per worker isolation | Increase to 20
RCN import | 2-4 hours for 5 years | Sequential, 1.2s/page | Parallelizable by month
Frontend | Loads 100 listings at once | No virtual scrolling | Will lag at 500+
Redis | Single instance | No clustering | Adequate for personal use

The system is fundamentally single-user/single-machine architected. Horizontal scaling would require:
Moving from psycopg2 thread pool to asyncpg
Moving _RCN_CACHE and ML model cache to Redis
Making scraper workers stateless


16. Reliability Assessment
Failure Scenario | Current Behavior | Should Behave | 
Ollama unreachable | LLM queue silently skips, 30s retry | Correct 
PostgreSQL down | Connection pool exhausted, app hangs | Should fail fast with circuit breaker 
Redis down | ARQ worker crashes, no SSE events | Should degrade gracefully 
Scraper returns 0 listings | Silently no-ops | Should alert if sustained 
RCN import partial failure | No resumption | Should checkpoint and resume 
Worker process restart | In-progress jobs lost | ARQ marks as failed after timeout 
Frontend API timeout | White screen (no error boundary) | Should show error state

MTTF estimate: Under sustained load (multiple users triggering hunts), the DB connection pool exhaustion (C4) would cause application hang within minutes. Single-user, single-machine operation is stable for days.


17. Production Readiness Score: 3.5/10
Dimension | Score | Rationale
Security | 1/10 | No auth, eval injection, SSRF
Data Integrity | 4/10 | ON CONFLICT correct but pool leaks, no transactions
Reliability | 4/10 | Works for happy path, fails on errors
Observability | 3/10 | Print/log statements, no metrics
Performance | 5/10 | Adequate for single user
Code Quality | 6/10 | Reasonable structure, some anti-patterns
Testability | 2/10 | No tests (test_integration.py is broken)
Documentation | 5/10 | Inline comments, stale walkthrough

18. Immediate Fixes (Next 48 Hours)
Priority 1 (Do today):

Add API key authentication to all mutation endpoints (POST /hunt/start, POST /set-hunt-config, POST /market/ingest*, DELETE operations)
Replace eval() with structured conditions — rewrite condition_expr as a JSON filter schema:

python# Instead of: "score > 0.25 and district == 'Mokotów'"
# Use: {"score": {"gt": 0.25}, "district": {"eq": "Mokotów"}}

Fix DB connection pool leak — wrap all DB functions in with get_conn() as conn: pattern
Fix the scheduler duplication — remove start_scheduler() call entirely, rely solely on ARQ cron
Fix debug HTML leak — gate save_debug_html behind DEBUG=true env var

Priority 2 (Do tomorrow):

Fix broken TERYT detection in deweloperuch.py:_normalize
Fix domiporta.py ImportError — remove the from backend.scrapers.domiporta import normalize_listing line
Fix Ollama temperature — add "options": {"temperature": 0} to all Ollama API calls
Fix prompt template — add {condition_hint} and {floor_info} to PROMPT_TEMPLATE
Add React error boundaries to Hunt.jsx and ListingDetail.jsx


19. Recommended Refactors
R1 — Replace APScheduler with ARQ Exclusively
Delete backend/scheduler.py. Move all job definitions to backend/tasks.py. This eliminates the duplicate scheduling problem and centralizes all async work.
R2 — Introduce Pydantic Models for All API Inputs
pythonclass HuntConfig(BaseModel):
    min_price: int = Field(ge=0)
    max_price: int = Field(ge=0)
    portals: List[Literal["otodom", "olx", "domiporta", "nieruchomosci_online"]]
    ...

@router.post("/hunt/start")
async def hunt_start(body: HuntConfig):
    ...
R3 — Replace eval() Alert System with DSL
pythonOPERATORS = {"gt": operator.gt, "lt": operator.lt, "eq": operator.eq, "gte": operator.ge}

def evaluate_condition(listing: dict, condition: dict) -> bool:
    for field, checks in condition.items():
        val = listing.get(field)
        for op, threshold in checks.items():
            if not OPERATORS[op](val or 0, threshold):
                return False
    return True
R4 — Fix Market Position Score Signal
Replace group_average_price_per_sqm(listings) with a DB query:
pythondef get_district_averages_from_db(city_slug: str) -> dict:
    # Query market_stats table, not current batch
R5 — Add Vite Dev Proxy
js// vite.config.js
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', rewrite: (path) => path.replace(/^\/api/, '') }
    }
  }
})
R6 — Implement RCN Import Checkpointing
(See section 9 for full implementation)
R7 — Photo Score Update After Analysis
pythondef save_photo_analysis(listing_id: int, analysis: dict) -> None:
    photo_score = analysis.get("photo_score", 0.0)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE listings SET
                photo_analysis = %s,
                photo_score = %s,
                score = LEAST(1.0, score + %s * 0.05),
                updated_at = NOW()
            WHERE id = %s AND photo_score IS DISTINCT FROM %s
        """, (Json(analysis), photo_score, photo_score, listing_id, photo_score))
        conn.commit()

20. Ideal Target Architecture
┌─────────────────────────────────────────────────────────────┐
│                        Nginx (TLS termination)               │
└──────────┬──────────────────────────────────────────────────┘
           │
┌──────────▼──────────┐        ┌─────────────────────────────┐
│  FastAPI Backend     │        │  React Frontend (static CDN) │
│  (read-only APIs)    │        └─────────────────────────────┘
│  + JWT auth          │
└──────────┬──────────┘
           │ async
┌──────────▼──────────────────────────────────────────────────┐
│                    Redis (ARQ Queue + Pub/Sub)                │
└──────────┬──────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────┐
│                    ARQ Workers (3 types)                      │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ Scrape Worker│  │ AI Worker    │  │ RCN Import Worker    │ │
│  │ (sync HTTP)  │  │ (Ollama)     │  │ (Deweloperuch API)   │ │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬──────────┘ │
└─────────┼────────────────┼─────────────────────┼────────────┘
          │                │                      │
┌─────────▼────────────────▼──────────────────────▼────────────┐
│                    PostgreSQL (asyncpg pool)                    │
│  + Connection pooling via PgBouncer                            │
└───────────────────────────────────────────────────────────────┘
          │
┌─────────▼────────────────────────────────────────────────────┐
│                    Ollama (GPU-accelerated)                     │
│  + Model: qwen2.5:7b (text) + llava (vision)                  │
│  + temperature: 0, seed: 42 for reproducibility               │
└───────────────────────────────────────────────────────────────┘
Key changes from current:

FastAPI becomes read-only API + auth layer; mutations go through job queue
Replace APScheduler with ARQ crons exclusively
Replace psycopg2 with asyncpg for true async DB
Add PgBouncer for connection pooling (supports 100+ concurrent connections)
Replace moondream with llava (better vision quality, same size)
Add structured logging (structlog → Loki or CloudWatch)
Add health checks with readiness probe that verifies DB + Redis + Ollama connectivity


21. Step-by-Step Plan for Full Historical Import (Q1 2019 → Today)
Phase 0: Preparation (1 day)
sql-- Create checkpoint table
CREATE TABLE rcn_import_checkpoints (
    id SERIAL PRIMARY KEY,
    city_slug TEXT NOT NULL,
    date_from DATE NOT NULL,
    date_to DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending/running/done/failed
    last_page INT DEFAULT 0,
    total_pages INT,
    records_saved INT DEFAULT 0,
    attempts INT DEFAULT 0,
    error TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    UNIQUE(city_slug, date_from, date_to)
);

-- Pre-populate monthly chunks for Warsaw
INSERT INTO rcn_import_checkpoints (city_slug, date_from, date_to)
SELECT 
    'warszawa',
    generate_series('2019-01-01'::date, date_trunc('month', NOW())::date, '1 month'::interval)::date,
    (generate_series('2019-01-01'::date, date_trunc('month', NOW())::date, '1 month'::interval) + '1 month - 1 day'::interval)::date
ON CONFLICT DO NOTHING;
Phase 1: Fix iter_transactions for Resumability
pythondef iter_transactions_resumable(
    city_slug: str,
    date_from: str,
    date_to: str,
    checkpoint_id: int,
    start_page: int = 1,
) -> Generator[dict, None, None]:
    with httpx.Client(headers=DEFAULT_HEADERS) as client:
        page = start_page
        total_pages = None
        
        while True:
            data = _fetch_page(client, city_slug, page, date_from, date_to)
            if not data or "data" not in data:
                break
            
            pagination = data.get("pagination", {})
            if total_pages is None:
                total_pages = pagination.get("totalPages", 1)
                update_checkpoint_total_pages(checkpoint_id, total_pages)
            
            for record in data["data"]:
                normalized = _normalize(record, city_slug)
                if normalized.get("sale_rcn_id") and normalized.get("amount_sqm"):
                    yield normalized
            
            # Checkpoint after each page
            update_checkpoint_page(checkpoint_id, page)
            
            if page >= total_pages:
                break
            page += 1
            time.sleep(RATE_LIMIT_SLEEP)
Phase 2: ARQ Task for Chunked Import
pythonasync def import_rcn_chunk_task(ctx, checkpoint_id: int):
    """Process a single monthly chunk. ARQ will retry on failure."""
    checkpoint = get_checkpoint_by_id(checkpoint_id)
    if checkpoint['status'] == 'done':
        return  # Idempotent
    
    mark_checkpoint_running(checkpoint_id)
    
    city_slug = checkpoint['city_slug']
    date_from = checkpoint['date_from'].isoformat()
    date_to = checkpoint['date_to'].isoformat()
    start_page = checkpoint['last_page'] or 1
    
    batch = []
    total_saved = 0
    
    try:
        for tx in iter_transactions_resumable(city_slug, date_from, date_to, 
                                               checkpoint_id, start_page):
            batch.append(tx)
            if len(batch) >= 200:
                saved = save_transaction_prices(batch)
                total_saved += saved
                batch = []
                await asyncio.sleep(0.1)  # cooperative yield
        
        if batch:
            total_saved += save_transaction_prices(batch)
        
        mark_checkpoint_done(checkpoint_id, total_saved)
        logger.info("[RCN] Chunk %s→%s: %d records", date_from, date_to, total_saved)
    
    except Exception as e:
        mark_checkpoint_failed(checkpoint_id, str(e))
        raise  # ARQ retries up to max_tries

import_rcn_chunk_task = job(max_tries=3, retry_delay=timedelta(minutes=5))(import_rcn_chunk_task)
Phase 3: Orchestrator
pythonasync def start_full_historical_import(ctx, city_slug: str = 'warszawa'):
    """Enqueue all pending monthly chunks."""
    redis = ctx['redis']
    pending = get_pending_checkpoints(city_slug)
    
    logger.info("[RCN] Enqueueing %d monthly chunks for %s", len(pending), city_slug)
    
    # Enqueue with 5-second delays to avoid thundering herd
    for i, checkpoint in enumerate(pending):
        await redis.enqueue_job(
            'import_rcn_chunk_task',
            checkpoint['id'],
            _defer_by=timedelta(seconds=i * 5)
        )
    
    return len(pending)
Phase 4: Validation Query
sql-- After import, check for gaps
SELECT 
    date_trunc('month', creation_date) as month,
    COUNT(*) as transactions,
    COUNT(district) as with_district,
    ROUND(COUNT(district)::numeric / COUNT(*) * 100, 1) as coverage_pct
FROM transaction_prices
WHERE city_slug = 'warszawa'
  AND creation_date >= '2019-01-01'
GROUP BY 1
ORDER BY 1;

-- Expected: ~200-500 transactions per month for Warsaw
-- Flag months with < 50 transactions as potentially incomplete
Phase 5: Gap Detection and Backfill
pythonasync def detect_and_backfill_gaps(ctx, city_slug: str, min_expected_per_month: int = 50):
    """Re-queue months with suspiciously low transaction counts."""
    gap_months = query_months_below_threshold(city_slug, min_expected_per_month)
    
    for month_start, month_end in gap_months:
        # Reset checkpoint status to re-import
        reset_checkpoint(city_slug, month_start, month_end)
        await ctx['redis'].enqueue_job('import_rcn_chunk_task', 
                                        get_checkpoint_id(city_slug, month_start, month_end))
Phase 6: Geocoding Pass
After import completes, run district assignment:
bash# Via ARQ task
arq backend.tasks.WorkerSettings --queue default \
    --run-job batch_geocode_missing_task warszawa 10000
Timeline Estimate
PhaseDurationNotesSchema + checkpoint setup2 hoursSQL migrationsCode changes4 hoursResumable iterator, ARQ taskEnqueue all 77 chunks5 minutesScript run onceImport execution35-90 minutes77 × ~30s avg per chunkValidation queries30 minutesManual reviewGeocoding pass2-4 hoursNominatim rate limitTotal~6 hoursWith monitoring
Anti-ban strategy: Stay at 1.2s between pages (current setting). Don't parallelize within the same city. Use one IP. Deweloperuch is a scraping-friendly public data portal but has 429 responses — the existing exponential backoff handles this.