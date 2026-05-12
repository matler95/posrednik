Audyt i Plan Przebudowy WREI — Analiza Repozytorium1. Aktualny Stan ProjektuCo działa (lub jest kompletne strukturalnie)Backend core: FastAPI jest poprawnie skonfigurowane z CORS, routingiem i lifecycle hooks. Migracje SQL (001–007) są spójne i przemyślane — schemat bazy jest solidny. Connection pooling przez ThreadedConnectionPool jest obecny.Scraping: Scraper Otodom (otodom.py) jest najlepiej napisanym plikiem w repozytorium — wielopoziomowy fallback dla ekstrakcji pól, walidacja, rotacja UA. OLX scraper jest kompletny. Domiporta, Gratka, Morizon są szkieletowe (403 blokady, brak działającego parsera). Deweloperuch scraper jest dobrze napisany z regex geocodingiem dla Warszawy (~85% coverage) i retry logic.Scoring engine (model.py): Logika scoringowa jest przemyślana — opportunity_score, score_breakdown, transaction_gap_ratio, value_growth_bonus, anomaly detection. Wagi są zbalansowane. Fallback na market_stats gdy brak RCN jest zaimplementowany.Hunt Manager (SSE): Architektura job managera z SSE streaming jest dobra koncepcyjnie — eventy portal_done, ai_done, enriching_done pozwalają na live updates w UI.Frontend Hunt page: Hunt.jsx jest najbardziej kompletnym komponentem — live SSE consumption, score breakdown, AI flags, sticky filters bar, map view. To jest rzeczywiście działający UI.Co nie działa / jest zepsuteKrytyczne:startup() w main.py ma bug — próbuje użyć conn po cur.close(); conn.close() (linia z rcn_count używa już zamkniętego połączenia). To crashuje przy starcie.python# Bug w main.py startup:
cur.close(); conn.close()
# ...
cur = conn.cursor()  # conn jest zamknięte!_background_historical_load w schedulerze uruchamia batch_geocode_missing który odpytuje Nominatim (rate limit 1 req/s) synchronicznie w schedulerze — blokuje cały BackgroundScheduler na godziny.process_llm_queue_sync tworzy nowy event loop w każdym wywołaniu schedulera (asyncio.new_event_loop()), co przy FastAPI jest race condition i może crashować przy concurrent access.alert_sent_log tabela jest definiowana w migracji 004, ale get_alerts() w db.py odpytuje price_alerts — to inna tabela. Alerty w UI nie będą działać.test_integration.py importuje run_hunt_async z błędną sygnaturą (pages_per_portal=1 nie istnieje).Poważne:LLM_QUEUE_LOOP w main.py (_llm_queue_loop) odpytuje get_listings_for_llm_analysis co 60 sekund w pętli, równolegle z schedulerem robiącym to samo co 10 minut — duplikacja pracy, potencjalne race conditions na aktualizacji llm_analysis.save_listings() używa ON CONFLICT (url) DO UPDATE — dobre, ale score_version jest inkrementowany przy każdym updacie (w tym przy identycznych danych). Po tygodniu scraping każdy listing będzie miał score_version=50+.get_hunt_listings() używa CTE z hunt_config w złożonym JOINie — gdy brak rekordu w hunt_config (id=1), zwraca 0 wyników bez błędu. Silent failure.predict_value() zawsze wraca (None, False) gdy brak modelu ML (bo /backend/models/ jest puste) — wtedy price_gap w scoring wynosi 0.0, co degraduje scoring do samego market_position + freshness + direct.Wydajnościowe:enrich_listings() jest wywoływane w loop.run_in_executor() — to blokuje thread pool dla każdego wywołania. RCN cache jest per-request, nie globalny — przy każdym nowym runie pełny cold start DB queries.get_rcn_benchmark() ma in-memory cache _RCN_CACHE ale jest czyszczony co 1000 wpisów (_RCN_CACHE.clear()) — podczas batch processing przekracza ten limit i czyści się w trakcie enrichmentu.Co jest niedokończoneCV pipeline (Faza 4): vision_scorer.py, clip_filter.py, fetcher.py — kompletny kod, ale transformers i torch są zakomentowane w requirements.txt. Pipeline jest dead code.Watchlist / alerty per-user: Tabela watchlist ma kolumny i seed data (migracja 004), ale brak endpointów CRUD dla watchlisty. Użytkownik nie może dodać własnego alertu przez UI — tylko statyczne seedy z migracji.Multi-city support: .env.example ma TARGET_CITIES=warszawa,krakow,..., ale search() w scraper.py zawsze buduje URL dla Warszawy (OTODOM_BASE jest hardcoded). Krakow nie będzie działać.ML model training: trainer.py jest kompletny, ale models/ directory jest pusty. Bez modelu scoring degraduje się znacząco.Geocoding dla transakcji: batch_geocode_missing jest wywoływany w schedulerze, ale Nominatim rate limit (1 req/s) sprawia, że 1000 brakujących rekordów zajmuje ~17 minut per run.Settings page (Settings.jsx): Używa Tailwind classes (card-accent, btn-primary) które nie istnieją w index.css — te klasy są zdefiniowane tylko przez @layer components z ograniczonym scope. Strona może wyglądać źle.Alerts page (Alerts.jsx): Używa card-premium, animate-in, slide-in-from-bottom-4 — Tailwind v3 nie ma tych klas domyślnie, wymagają pluginu. UI jest broken.Problemy architektoniczneBrak separation of concerns w db.py: Plik ma 600+ linii i miesza connection pooling, DDL, DML, biznes logic. Nie da się przetestować bez bazy.Brak retry strategy dla scraperów przy skali: fetch_html() ma 3 próby, ale między nimi nie ma exponential jitter — przy masowym scrapowaniu Otodom zbanuje IP.Brak queue system: LLM analiza jest robiona przez asyncio.sleep(1.5) między requestami w pętli. Brak dead-letter queue, brak retry dla failed LLM calls (tylko llm_error_count < 3 jako guard).Frontend routing problem: vite.config.js nie ma proxy skonfigurowanego — VITE_API_URL=/api działa tylko przez nginx. W trybie dev (npm run dev bez nginx) backend jest nieosiągalny.Brak autentykacji: Żaden endpoint nie ma auth. Każdy może uruchomić hunt, zmienić config, zresettować bazę przez /market/ingest-history.Problemy produktoweUżytkownik nie może zobaczyć "dlaczego ta oferta ma taki score" bez kliknięcia "Rozkład score" — kluczowa informacja jest ukryta. Ranking okazji jest tylko po score, brak sortowania po absolute value (ile zarabiam na tej okazji). Brak "watchlist" dla konkretnych ofert — nie mogę zapisać interesującej mnie oferty. Brak historii polowań — co znalazłem tydzień temu?2. Krytyczne Problemy Blokujące RozwójP0 — Blokujące działanie systemuProblemWpływRyzykoBug w startup() (użycie zamkniętego connection)System nie startuje stabilnieCRITICALBrak modelu ML → scoring degradowanyCore feature nie działa poprawnieCRITICALprice_alerts vs alert_sent_log — niezgodność tabelAlerty w UI zawsze pusteHIGHNominatim blokuje scheduler threadScheduler zawiesza się na godzinyHIGHP1 — Degradujące jakość danychProblemWpływRyzykoRace condition LLM queue (main loop + scheduler)Duplikaty, lost updatesHIGHget_hunt_listings() silent failure bez hunt_configUser widzi 0 ofert bez komunikatuMEDIUMCV pipeline dead codeZdjęcia nie są analizowane mimo kompletnego koduMEDIUMscore_version infinite incrementDB bloat, false cache invalidationMEDIUMP2 — Produktowe blokeryProblemWpływRyzykoBrak CRUD watchlistyUżytkownik nie może skonfigurować alertówHIGHBrak autentykacjiBezpieczeństwo, multi-user niemożliwyHIGHHardcoded Warszawa URLsMulti-city nie działaMEDIUMBroken Tailwind classes w Alerts/SettingsUI stron brokenLOW-MEDIUM3. Docelowa Architektura Systemu┌─────────────────────────────────────────────────────────────────┐
│                         NGINX / Caddy                           │
│                    (SSL termination, routing)                    │
└──────────┬──────────────────────────────────────┬───────────────┘
           │                                      │
    ┌──────▼──────┐                       ┌───────▼──────┐
    │  Frontend   │                       │   Backend    │
    │  React/Vite │                       │  FastAPI     │
    │  (SPA)      │                       │  (async)     │
    └─────────────┘                       └──────┬───────┘
                                                 │
              ┌──────────────────────────────────┼──────────────────────────┐
              │                                  │                          │
    ┌─────────▼──────┐              ┌────────────▼──────┐       ┌──────────▼───┐
    │  Task Queue    │              │   PostgreSQL 15    │       │   Redis      │
    │  (ARQ/Celery)  │              │   (primary store)  │       │   (cache +   │
    │                │              │                    │       │    sessions) │
    └─────────┬──────┘              └────────────────────┘       └──────────────┘
              │
    ┌─────────▼──────────────────────────────┐
    │          Workers                        │
    │  ┌────────────┐  ┌───────────────────┐ │
    │  │  Scraper   │  │   AI Pipeline     │ │
    │  │  Worker    │  │   Worker          │ │
    │  │            │  │  ┌─────────────┐  │ │
    │  │  - Otodom  │  │  │ LLM Scorer  │  │ │
    │  │  - OLX     │  │  │ (Ollama/    │  │ │
    │  │  - RCN     │  │  │  Claude)    │  │ │
    │  └────────────┘  │  ├─────────────┤  │ │
    │                  │  │ Vision AI   │  │ │
    │                  │  │ (moondream) │  │ │
    │                  │  ├─────────────┤  │ │
    │                  │  │  Scorer     │  │ │
    │                  │  │  Engine     │  │ │
    │                  │  └─────────────┘  │ │
    │                  └───────────────────┘ │
    └────────────────────────────────────────┘Komponenty i ich odpowiedzialnościFastAPI Backend — tylko API layer. Nie robi scrapingu, nie robi AI analysis. Deleguje do task queue. Zwraca dane z DB/cache.Task Queue (ARQ — AsyncIO Redis Queue) — lekka alternatywa dla Celery, natywnie async. Osobne queues: scraping, enrichment, ai_analysis, notifications. Priority queues dla pilnych zadań.PostgreSQL — jedyne source of truth. TimescaleDB extension dla price history (opcjonalnie, ale warto).Redis — cache dla hot data (top listings, market stats, rcn benchmarks), session storage, task queue backend, rate limiting.Scraper Worker — izolowany process, własny rate limiter per portal, własny IP pool (opcjonalnie), retry z exponential backoff.AI Pipeline Worker — oddzielony od scrapera. Może być skalowany niezależnie. Prioritetyzuje oferty z wysokim preliminary_score.4. Architektura Modułu SNIPERFlow danych end-to-endUser definiuje profil (raz)
         │
         ▼
hunt_config zapisany w DB
         │
         ▼ (scheduler co 6h lub manual trigger)
┌────────────────────────────────────────────┐
│              SCRAPING PHASE                │
│                                            │
│  dla każdego portalu (concurrent):         │
│  1. Fetch strony wynikowe (paginated)      │
│  2. Parsuj listingi                        │
│  3. Deduplikuj po URL                      │
│  4. Sprawdź czy URL istnieje w DB          │
│     - Nie istnieje → NEW listing           │
│     - Istnieje → sprawdź czy cena się      │
│       zmieniła → PRICE_CHANGE event        │
└────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────┐
│           ENRICHMENT PHASE                 │
│                                            │
│  1. Oblicz price_per_m2                    │
│  2. Pobierz RCN benchmark (z cache Redis)  │
│  3. Oblicz transaction_gap                 │
│  4. Pobierz CAGR (z cache Redis)           │
│  5. Oblicz preliminary_score               │
│  6. Zapisz do DB                           │
│  7. Trigger alert check (jeśli score > X)  │
└────────────────────────────────────────────┘
         │
         ▼ (async, nie blokuje)
┌────────────────────────────────────────────┐
│           AI ANALYSIS PHASE                │
│  (tylko dla preliminary_score > threshold) │
│                                            │
│  KOLEJKA PRIORYTETOWA (score malejąco):    │
│                                            │
│  1. LLM Analysis (Qwen 2.5):               │
│     - opis → JSON z flags, summary         │
│     - green_flags, red_flags               │
│     - negotiation_potential (0-10)         │
│     - investment_score (0-10)              │
│     - urgency_signals                      │
│                                            │
│  2. Vision Analysis (Moondream):           │
│     - download top 4 zdjęcia               │
│     - CLIP filter (rzuty, loga)            │
│     - condition_score (1-10) per photo     │
│     - aggregate → photo_score              │
│                                            │
│  3. Re-score z AI boost:                   │
│     - opportunity_score = f(preliminary,   │
│                              text_score,   │
│                              photo_score)  │
│     - zapisz do DB                         │
└────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────┐
│           ALERT EVALUATION                 │
│                                            │
│  1. Sprawdź active watchlist               │
│  2. Eval condition_expr per alert          │
│  3. Check alert_sent_log (dedup)           │
│  4. Send Telegram notification             │
│  5. Zapisz do alert_sent_log               │
└────────────────────────────────────────────┘Deduplikacja — strategiaPrzy save_listing(listing):
  SELECT id, price, updated_at FROM listings WHERE url = $1
  
  IF not found:
    INSERT new listing
    EMIT event: "new_listing"
    
  IF found AND price != existing.price:
    UPDATE listing (price, updated_at, score_version+1)
    INSERT INTO listing_history (snapshot)
    EMIT event: "price_change"
    
  IF found AND price == existing.price:
    UPDATE listing (updated_at only)
    -- nie zwiększaj score_version
    -- nie rób re-enrichment jeśli < 24hRCN Cache StrategyRedis key: "rcn:{city_slug}:{district}:{rooms_bucket}"
TTL: 24h
rooms_bucket: None, "1", "2", "3", "4+"

Przy zapytaniu o benchmark:
  1. Sprawdź Redis
  2. Jeśli hit → return
  3. Jeśli miss → DB query → zapisz do Redis → return
  4. Jeśli brak w DB → fallback na market_stats (inna key)Scoring — precyzyjne wagipython# Preliminary score (bez AI):
score = (
    price_gap    * 0.35   # vs ML estimate
  + txn_gap_pos  * 0.30   # vs RCN transactions  
  + market_pos   * 0.15   # vs current offers avg
  + freshness    * 0.12   # days on market
  + direct       * 0.08   # no agent
) * condition_mult + growth_bonus - anomaly_penalty

# AI boost (additive, max +13%):
final_score = min(
  preliminary + text_score * 0.08 + photo_score * 0.05,
  1.0
)

# Przy braku ML model (brak modelu .joblib):
# price_gap = max(0, market_pos) jako proxy
# OZNACZAJ w UI: "Scoring bez ML (bazuje na cenach ofertowych)"5. Plan Przebudowy Krok po KrokuStage 0 — Stabilizacja (Tydzień 1)Cele: System działa stabilnie, nie crashuje, dane są spójne.Taski:Napraw bug startup w main.py — osobne connection dla każdego bloku.python# Zamiast jednego bloku — dwa oddzielne:
async def startup():
    init_db()
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM market_stats")
            ms_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM listings")
            l_count = cur.fetchone()[0]
    except Exception as e:
        logger.warning("[Startup] market_stats check: %s", e)
    
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM transaction_prices")
            rcn_count = cur.fetchone()[0]
    except Exception as e:
        logger.warning("[Startup] rcn check: %s", e)Usuń _llm_queue_loop z main.py — scheduler robi to samo. Jeden punkt odpowiedzialności.Przenieś Nominatim geocoding do oddzielnego task (nie w scheduler thread). Geocoding przez regex jest instant — oddziel od Nominatim który jest slow.Napraw get_alerts() — zmień tabelę z price_alerts na alert_sent_log lub stwórz dedykowany endpoint dla watchlist matches.Dodaj PooledConnectionWrapper context manager (brakuje __enter__/__exit__):pythonclass PooledConnectionWrapper:
    def __enter__(self): return self
    def __exit__(self, *args):
        if args[0]: self.rollback()
        self.close()Fix score_version — inkrementuj tylko gdy faktycznie zmienił się score (dodaj warunek do UPDATE).Napraw Tailwind classes w Alerts.jsx i Settings.jsx — zastąp card-premium przez card, animate-in przez fade-in.Zależności: Żadne — to hotfixy.Ryzyka: Niskie — zmiany są izolowane.Estimated complexity: 2-3 dni backend.Stage 1 — Backend Core (Tygodnie 2-3)Cele: Solidny, testowalny backend z separation of concerns.Taski:Podziel db.py na moduły:backend/
  data/
    connection.py      # pool, get_conn, context manager
    listings.py        # CRUD listings
    market.py          # market_stats, transaction_prices
    jobs.py            # hunt_jobs, scrape_runs
    alerts.py          # watchlist, alert_sent_log
    geocache.py        # geocode_cacheDodaj Redis cache layer:python# backend/cache.py
import redis.asyncio as redis

_redis = None

async def get_redis():
    global _redis
    if not _redis:
        _redis = await redis.from_url("redis://redis:6379")
    return _redis

async def cache_get(key: str):
    r = await get_redis()
    val = await r.get(key)
    return json.loads(val) if val else None

async def cache_set(key: str, value, ttl: int = 3600):
    r = await get_redis()
    await r.setex(key, ttl, json.dumps(value, default=str))Dodaj ARQ task queue:python# backend/tasks.py
from arq import create_pool, ArqRedis

async def scrape_portal(ctx, portal: str, config: dict):
    """Task: scrape single portal"""
    ...

async def enrich_listing(ctx, listing_id: int):
    """Task: enrich single listing"""
    ...

async def analyze_listing_ai(ctx, listing_id: int):
    """Task: AI analysis"""
    ...

WORKER_SETTINGS = WorkerSettings(
    functions=[scrape_portal, enrich_listing, analyze_listing_ai],
    redis_settings=RedisSettings(host="redis"),
    max_jobs=5,
    job_timeout=120,
)Dodaj preliminary_score fast-path — oblicz scoring bez DB round-trip przy save:pythonasync def save_and_enrich_batch(listings: list[dict]) -> list[dict]:
    """Enrich + save atomically, return enriched listings"""
    averages = group_average_price_per_sqm(listings)
    rcn_cache = {}
    
    enriched = []
    for listing in listings:
        e = await _enrich_one(listing, averages, rcn_cache)
        enriched.append(e)
    
    save_listings(enriched)  # bulk upsert
    return enrichedEstimated complexity: 5-7 dni backend.Estimated impact: Eliminuje race conditions, umożliwia testing.Stage 2 — Fetchery (Tygodnie 3-4)Cele: Stabilny, skalowalny scraping z prawdziwą deduplikacją.Taski:Refaktoruj scraper architecture — jeden BasePortalScraper:pythonclass BasePortalScraper:
    portal_name: str
    base_url: str
    rate_limit: float = 1.5  # seconds between requests
    
    async def fetch_page(self, page: int, params: dict) -> list[dict]:
        """Fetch and parse one page. Return raw listings."""
        raise NotImplementedError
    
    async def fetch_all(self, params: dict, max_pages: int = 10) -> list[dict]:
        """Paginate through all results."""
        all_listings = []
        for page in range(1, max_pages + 1):
            listings = await self.fetch_page(page, params)
            if not listings:
                break
            all_listings.extend(listings)
            await asyncio.sleep(self.rate_limit + random.uniform(0, 0.5))
        return all_listings
    
    def normalize(self, raw: dict) -> dict | None:
        """Normalize raw listing to standard schema."""
        raise NotImplementedErrorNapraw Otodom URL builder dla multi-city:pythonCITY_URLS = {
    "warszawa": "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/mazowieckie/warszawa/warszawa",
    "krakow": "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/malopolskie/krakow/krakow",
    "wroclaw": "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/dolnoslaskie/wroclaw/wroclaw",
}Dodaj snapshot detection — przy fetch sprawdzaj czy oferta zniknęła (status: inactive):pythonasync def mark_inactive_listings(portal: str, seen_urls: set[str]):
    """Mark listings not seen in latest scrape as potentially inactive."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE listings 
        SET is_active = FALSE, last_seen = NOW()
        WHERE portal = %s 
          AND url != ALL(%s)
          AND created_at < NOW() - INTERVAL '24 hours'
          AND is_active = TRUE
    """, (portal, list(seen_urls)))
    conn.commit()Dodaj kolumnę is_active BOOLEAN DEFAULT TRUE do listings — brakuje w obecnym schemacie.Implementuj proper rate limiting per portal przez token bucket w Redis (zamiast in-process):pythonasync def check_rate_limit(portal: str) -> bool:
    """Redis-based rate limiting. Returns True if request allowed."""
    r = await get_redis()
    key = f"rate:{portal}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 1)  # 1 second window
    limits = {"otodom": 1, "olx": 1, "deweloperuch": 1}
    return count <= limits.get(portal, 1)Estimated complexity: 4-5 dni backend.Ryzyka: Otodom/OLX mogą zmienić HTML strukturę — testy regresyjne na sample HTML są niezbędne.Stage 3 — AI Analysis (Tygodnie 4-5)Cele: Niezawodny pipeline AI z prioritetyzacją i retry.Taski:Przepisz LLM pipeline na async task queue z priority:pythonasync def analyze_listing_ai(ctx, listing_id: int, priority: str = "normal"):
    """
    ARQ task. Priority: "high" (score > 0.3) | "normal" | "low"
    """
    listing = get_listing_by_id(listing_id)
    if not listing or listing.get("llm_error_count", 0) >= 3:
        return
    
    result = await analyze_listing_with_llm(listing)
    
    if result and "error" not in result:
        save_llm_analysis(listing["url"], result)
        new_score = recalculate_score(listing, result)
        save_listing_score(listing_id, new_score)
        await check_alert_triggers(listing_id, new_score)
    else:
        increment_llm_error_count(listing_id)Ulepsz LLM prompt — obecny prompt jest zbyt długi i chaotyczny:pythonPROMPT = """Analyze this Warsaw real estate listing. Return ONLY valid JSON.

LISTING:
Price: {price} PLN ({price_per_m2} PLN/m²)
Area: {area}m² | Rooms: {rooms} | District: {district}
Days on market: {days_on_market}
RCN benchmark: {rcn_benchmark} PLN/m² ({gap_sign}{gap_pct}% vs transactions)
Description: {description_300chars}

Return JSON with exactly these fields:
{{
  "investment_score": <1-10>,
  "negotiation_potential": <1-10>,
  "condition": "<new|good|average|renovation>",
  "summary": "<2 sentences max>",
  "green_flags": ["<specific observation>"],
  "red_flags": ["<specific risk>"],
  "urgency_signals": ["<if any>"],
  "hidden_costs_estimate": <PLN or 0>
}}"""Dodaj Vision pipeline (odkomentuj w requirements.txt):Zaplanuj gradual rollout — najpierw tylko dla score > 0.30, max 4 zdjęcia, timeout 30s per zdjęcie.Dodaj fallback: jeśli Ollama niedostępna → keyword scoring jako degraded mode (obecna analyze_description() funkcja).Dodaj ai_quality_score do listings — pole 0-1 mówiące jak dobra była analiza AI (czy LLM zwróciło pełne dane, czy był timeout):python# 1.0 = pełna analiza LLM + vision
# 0.7 = tylko LLM
# 0.3 = keyword fallback  
# 0.0 = brak analizyEstimated complexity: 5-7 dni (backend + AI tuning).Ryzyka: Ollama może być niedostępna — bezwzględny fallback jest krytyczny.Stage 4 — Scoring (Tydzień 5-6)Cele: Precyzyjny, interpretowalny scoring z ML model.Taski:Wytrenuj podstawowy ML model — zebrać 200+ listings z cenami i wytrenować GradientBoosting jak w trainer.py. Model powinien być bootstrapowany ze statycznych danych:python# bootstrap_model.py — jednorazowy skrypt
# Pobiera dane historyczne RCN i buduje podstawowy model wyceny
# bez danych z scrapera (cold start problem)Dodaj is_ml_estimate flagę do UI — gdy brak modelu, wyświetl komunikat "Scoring bazuje na cenach ofertowych (brak modelu ML)".Dodaj scoring explanation API endpoint:python@app.get("/listings/{id}/score-explanation")
async def score_explanation(listing_id: int):
    """Returns human-readable explanation of scoring."""
    listing = get_listing_by_id(listing_id)
    breakdown = score_breakdown(listing, ...)
    
    return {
        "total": breakdown["total_pct"],
        "components": breakdown["components"],
        "explanation": generate_text_explanation(breakdown),
        "comparable_listings": get_similar_priced_listings(listing),
    }Dodaj anomaly detection dla cen — osobny endpoint i flaga w UI:python# Anomalie: cena za m² < 2000 PLN, cena < 50k przy area > 15m²
# Wyświetlaj czerwony banner: "⚠️ Prawdopodobna anomalia cenowa"Estimated complexity: 3-4 dni backend + 1-2 dni ML.Stage 5 — Frontend (Tygodnie 6-7)Cele: Clean, fast, informative UI. Nie fancy — użyteczny.Taski:Priorytet #1: Dashboard inwestora na /hunt — obecna implementacja jest dobra, ale wymaga:Wyświetlaj "Scoring bez ML" banner gdy is_ml_estimate = False.Dodaj "Absolute value" sortowanie — "zaoszczędzę X PLN":jsx// W StickyBar dodaj:
{ value: 'savings', label: 'Oszczędność ↓' }
// W fetchListings dodaj computed field:
listing.estimated_savings = listing.rcn_benchmark 
  ? Math.round((listing.rcn_benchmark - listing.price_per_m2) * listing.area)
  : nullDodaj CRUD dla watchlist — strona /alerts/manage:jsx// Prosta forma: name, condition_expr, min_score, city_slug
// Przykłady gotowych alertów:
const PRESET_ALERTS = [
  { name: "Okazja Mokotów", expr: "district == 'Mokotów' and score > 0.25" },
  { name: "Bezpośrednie Wola", expr: "district == 'Wola' and direct_offer == True" },
]Napraw Alerts i Settings pages — zastąp broken Tailwind classes.Dodaj "Porównanie ofert" view — zaznacz 2-3 oferty, porównaj side-by-side.Dodaj is_active indicator na kartach — wyszarzenie nieaktywnych ofert.Estimated complexity: 5-7 dni frontend.Stage 6 — Monitoring i Optymalizacja (Tydzień 8)Cele: Observability, performance, cost optimization.Taski:Dodaj Prometheus metrics:python# backend/metrics.py
from prometheus_client import Counter, Histogram, Gauge

listings_scraped = Counter("listings_scraped_total", "Total listings scraped", ["portal"])
ai_analysis_duration = Histogram("ai_analysis_seconds", "AI analysis duration")
active_opportunities = Gauge("active_opportunities", "Listings with score >= 0.25")
llm_errors = Counter("llm_errors_total", "LLM analysis failures")Dodaj Sentry dla error tracking (darmowy plan wystarczy).Dodaj DB query monitoring — pg_stat_statements extension:sql-- Top slow queries:
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;Dodaj Redis monitoring — redis-commander w docker-compose dla dev.Optymalizuj top 3 slow endpoints z pg_stat_statements.Dodaj EXPLAIN ANALYZE dla get_hunt_listings() — podejrzewam brak indeksu na score + created_at compound.Estimated complexity: 3-4 dni DevOps/backend.6. Proponowany Stack TechnologicznyBackendFastAPI 0.115+          # async, modern, OpenAPI out of box
ARQ                     # async task queue, Redis-backed, prostszy od Celery
psycopg3 (nie psycopg2) # async support, better connection pooling
redis.asyncio           # cache + rate limiting + sessions
httpx                   # już używane, dobre
tenacity                # już używane, retry logic
APScheduler             # już używane, zostaje dla cron jobs
Pydantic v2             # schema validation (upgrade z v1)AIOllama (self-hosted)    # qwen2.5:7b dla LLM, moondream dla vision
Claude API              # fallback gdy Ollama niedostępna (opcjonalnie)
transformers + torch    # CLIP filter (CPU-only)
spaCy pl                # już używane, NLP features
scikit-learn + joblib   # ML model (GradientBoosting), już zaimplementowaneScraping/Fetchinghttpx AsyncClient       # już używane
playwright              # TYLKO jeśli Otodom zacznie wymagać JS rendering
BeautifulSoup4 + lxml   # HTML parsing
Nominatim (OSM)         # geocoding, rate limited — tylko jako fallbackDatabasePostgreSQL 15           # already, zostaje
TimescaleDB extension   # opcjonalnie dla price_history time series
Redis 7                 # cache + sessions + task queueFrontendReact 19 + Vite 8       # already, zostaje
TailwindCSS v3          # already — usunąć nieistniejące custom classes
Recharts                # already, zostaje
Leaflet + react-leaflet # already, zostaje
Axios                   # already, zostaje
React Router v7         # already, zostajeHosting/DeploymentDocker Compose          # dev i staging
VPS (Hetzner CX32)      # ~18 EUR/mies, 8 vCPU, 32GB RAM
Nginx                   # already
Caddy                   # SSL termination (prostszy config niż nginx dla SSL)
GitHub Actions          # CI/CDObservabilityPrometheus + Grafana    # metrics
Sentry                  # error tracking (free tier)
structlog               # structured logging (zamień print → logger)7. Model DanychListings (ulepszony)sqlCREATE TABLE listings (
    id                  SERIAL PRIMARY KEY,
    portal              TEXT NOT NULL,
    url                 TEXT UNIQUE NOT NULL,
    title               TEXT,
    price               INT,
    area                FLOAT,
    price_per_m2        FLOAT,
    district            TEXT,
    city_slug           TEXT DEFAULT 'warszawa',
    rooms               TEXT,
    floor               INT,
    total_floors        INT,
    year_built          INT,
    condition           TEXT,
    building_type       TEXT,
    ownership           TEXT,
    heating             TEXT,
    direct_offer        BOOLEAN DEFAULT FALSE,
    description         TEXT,
    images              JSONB DEFAULT '[]',
    features            JSONB DEFAULT '{}',
    raw_location        JSONB DEFAULT '{}',
    lat                 FLOAT,
    lng                 FLOAT,
    
    -- Scoring
    preliminary_score   FLOAT,
    score               FLOAT,
    score_version       INT DEFAULT 1,
    score_components    JSONB,     -- breakdown dla UI
    is_ml_estimate      BOOLEAN DEFAULT FALSE,
    ai_quality_score    FLOAT,    -- 0-1, jak dobra analiza AI
    
    -- RCN
    rcn_benchmark       FLOAT,
    transaction_gap     FLOAT,
    cagr_5y             FLOAT,
    estimated_value     FLOAT,
    
    -- AI Analysis
    llm_analysis        JSONB,
    photo_analysis      JSONB,
    text_score          FLOAT,
    photo_score         FLOAT,
    llm_error_count     INT DEFAULT 0,
    
    -- Status tracking
    is_active           BOOLEAN DEFAULT TRUE,  -- BRAKUJE w obecnym schemacie
    days_on_market      INT DEFAULT 0,
    first_seen          TIMESTAMP DEFAULT NOW(),
    last_seen           TIMESTAMP DEFAULT NOW(),
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW(),
    last_enriched_at    TIMESTAMP,
    
    -- Error tracking
    anomaly_score       FLOAT,
    anomaly_flags       JSONB,    -- ['price_too_low', 'area_suspicious']
    
    source              TEXT,
    price_drop_pct      FLOAT,    -- % spadek od pierwszej ceny
    price_history_min   INT,      -- min cena historyczna
    price_history_max   INT       -- max cena historyczna
);

-- Indeksy
CREATE INDEX idx_listings_score_active ON listings(score DESC, is_active) WHERE is_active = TRUE;
CREATE INDEX idx_listings_hunt ON listings(city_slug, price, area, score DESC);
CREATE INDEX idx_listings_new ON listings(created_at DESC) WHERE is_active = TRUE;
CREATE INDEX idx_listings_ai_queue ON listings(preliminary_score DESC) 
    WHERE llm_analysis IS NULL AND llm_error_count < 3;Price History (ulepszony)sqlCREATE TABLE listing_price_history (
    id          SERIAL PRIMARY KEY,
    listing_url TEXT NOT NULL REFERENCES listings(url),
    price       INT NOT NULL,
    price_per_m2 FLOAT,
    score       FLOAT,
    change_type TEXT,  -- 'initial', 'price_drop', 'price_increase', 'reactivated'
    change_pct  FLOAT, -- % zmiana vs poprzedni
    recorded_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_lph_url_date ON listing_price_history(listing_url, recorded_at DESC);Watchlist (ulepszony)sqlCREATE TABLE watchlist (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    condition_expr  TEXT DEFAULT '',
    min_score       FLOAT DEFAULT 0.15,
    city_slug       TEXT DEFAULT 'warszawa',
    -- Preconfigured filters (UI-friendly)
    max_price       INT,
    min_area        FLOAT,
    max_area        FLOAT,
    districts       TEXT[],
    rooms           TEXT[],
    direct_only     BOOLEAN DEFAULT FALSE,
    -- Alert config
    channels        JSONB DEFAULT '{"telegram": true}',
    alert_threshold FLOAT DEFAULT 0.25,
    -- Status
    active          BOOLEAN DEFAULT TRUE,
    last_triggered  TIMESTAMP,
    trigger_count   INT DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);Hunt Jobs (ulepszony)sqlCREATE TABLE hunt_jobs (
    id              UUID PRIMARY KEY,
    status          TEXT NOT NULL,
    config          JSONB NOT NULL,
    triggered_by    TEXT DEFAULT 'manual',  -- 'manual', 'scheduler', 'alert'
    portals_counts  JSONB DEFAULT '{}',
    started_at      TIMESTAMP DEFAULT NOW(),
    finished_at     TIMESTAMP,
    total_scraped   INT DEFAULT 0,
    total_saved     INT DEFAULT 0,
    total_new       INT DEFAULT 0,          -- nowe oferty
    total_updated   INT DEFAULT 0,          -- zaktualizowane
    total_ai        INT DEFAULT 0,
    error           TEXT,
    metadata        JSONB DEFAULT '{}'      -- dodatkowe stats
);8. Strategia SkalowaniaTysiące ofert — data tierOtodom Warszawa ma ~3000-5000 aktywnych ofert w typowych filtrach. Przy codziennym scraping to ~15k rekordów miesięcznie (z historią). PostgreSQL bez problemu obsłuży 1M+ rekordów na VPS CX32.Bottleneck to nie storage ale query performance. Kluczowe indeksy (powyżej) rozwiązują ~95% przypadków. VACUUM ANALYZE co tydzień przez scheduler.Częste aktualizacje — scraping tierNie scrapuj wszystkich portali jednocześnie. Rozłóż w czasie:00:00 - Otodom
02:00 - OLX  
04:00 - RCN update
06:00 - Otodom (segunda vuelta)
08:00 - morning digest Telegram
12:00 - OLX
18:00 - Otodom (peak hours)Każdy portal ma osobny semaphore (max 2 concurrent pages). Przy 3 stronach × 25 listings × 1.5s delay = ~4.5 minuty per portal.Parallel processingpython# Scraping: concurrent portals, sequential pages per portal
async def run_hunt_async(config):
    tasks = [
        asyncio.create_task(scrape_portal("otodom", config)),
        asyncio.create_task(scrape_portal("olx", config)),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

# AI analysis: sequential z rate limit (Ollama single-threaded)
# 1 listing per 3-5 sekund (timeout Qwen2.5 na CPU)
# 100 listings/dzień jeśli Ollama na CPU
# Priorytetyzuj top 20 scores → rest w tleRate limitspythonPORTAL_RATE_LIMITS = {
    "otodom": 1.2,      # 1 req / 1.2s
    "olx": 1.0,         # 1 req / 1.0s  
    "deweloperuch": 1.2, # 50 records per page, 60 pages = 72s total
}

# Implementacja przez Redis token bucket (nie in-process)
# Resetuje przy restarcie kontenerów — bezpiecznieRetry strategypython@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def fetch_with_retry(url: str, client: httpx.AsyncClient) -> str:
    response = await client.get(url, timeout=20.0)
    if response.status_code == 429:
        raise httpx.HTTPStatusError(...)  # trigger retry
    return response.textCost optimizationUruchamiaj Ollama tylko gdy jest kolejka (nie idle). Moondream używaj tylko dla listings z score > 0.25 (oszczędność ~70% wywołań). RCN benchmark cache TTL=24h w Redis (oszczędność ~90% DB queries).9. Strategia AIAnaliza klasyczna (heurystyki, bez AI)Wykrywanie ceny za m² (anomalii) — proste thresholdy (< 2000 PLN/m²). Detekcja "bezpośrednia" — pattern matching na advertType. days_on_market — prosta arytmetyka. Keyword scoring (backup) — lista POSITIVE/NEGATIVE keywords. RCN gap — czysta matematyka.LLM (Qwen 2.5 local lub Claude API)Analiza opisu — jakościowe sygnały których nie widać w danych: "pilna sprzedaż", "właściciel wyprowadza się za granicę", ukryte wady ("do odświeżenia", "stan deweloperski"). Ekstrakcja hidden costs estimate (szacunek kosztów remontu). Detekcja urgency signals. Sentiment i tone — desperation vs overpriced seller.Nie używaj LLM do: obliczania ceny (to matematyka), detekcji dzielnicy (regex), sprawdzania dostępności (scraping).Vision AI (Moondream)Condition scoring zdjęć — nowe/dobry/do remontu. Wykrywanie rzutów technicznych (odfiltruj przed scoringiem). Identyfikacja kluczowych features: balkon, piwnica, garaż (backup dla text extraction).Nie używaj Vision do: wszystkich ofert (za wolne na CPU). Tylko dla preliminary_score > 0.25 i max 4 zdjęcia.Embeddings (przyszłość, nie teraz)Semantic search po opisach (podobne mieszkania). Clustering ofert by style/charakter. "Znajdź mi coś podobnego do tej oferty".Decyzja: kiedy używać Claude API vs OllamaOllama (local):
  + zero cost
  - wolny na CPU (3-8s per listing)
  - wymaga 8+ GB RAM
  
Claude API (external):
  + szybki (< 1s)
  - koszt: ~$0.003 per listing (claude-haiku)
  - dla 100 listings/dzień = $0.30/dzień = ~$9/mies
  
Rekomendacja: Ollama primary, Claude jako fallback przy timeout10. Finalna RekomendacjaPrzebuduj natychmiast
main.py startup() — bug z closed connection (30 minut pracy)
db.py — podziel na moduły (2 dni)
Nominatim w schedulerze — przenieś do async task (1 dzień)
LLM queue duplication — usuń _llm_queue_loop (1 godzina)
Broken Tailwind classes w Alerts/Settings (2 godziny)
Fix get_alerts() endpoint (1 godzina)
Zostaw
Logika scoringowa w model.py — jest dobra, tylko drobne poprawki
Hunt SSE architecture — dobry design, wymaga stabilizacji
score_breakdown() — świetne dla UI
Deweloperuch scraper — najlepiej napisany moduł
Migracje SQL — spójne, zostają
React component structure w Hunt.jsx — dobra baza
Usuń
dashboard/ (Streamlit) — dead code, zastąpiony przez React
backend/find_path.py — debug utility, nie powinno być w repo
backend/test_integration.py — broken test, nie ma wartości
Zakomentowane portale w PORTAL_SCRAPERS (Morizon, Gratka) — albo napraw albo usuń całkowicie
Przepisz od zera
db.py — za duży monolith, needs separation
scraper_async.py — uprość, użyj BasePortalScraper
scheduler.py — przepisz na ARQ worker (APScheduler w FastAPI ma problemy z async context)
Settings.jsx i Alerts.jsx — broken UI, przepisz z czystymi CSS variables
Rekomendowana kolejnośćTydzień 1: Stage 0 (bugfixy) + Setup Redis + Setup ARQ
Tydzień 2: Stage 1 (db.py refactor) + Redis cache dla RCN
Tydzień 3: Stage 2 (scraper base class) + multi-city
Tydzień 4: Stage 3 (AI pipeline) + CV activation
Tydzień 5: Stage 4 (ML model bootstrap) + scoring tests  
Tydzień 6: Stage 5 (frontend CRUD watchlist + fixes)
Tydzień 7: Stage 6 (monitoring + perf)
Tydzień 8: Integration testing + production deploy