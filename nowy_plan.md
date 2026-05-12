Stage 0 — Stabilizacja (Tydzień 1)
Cel: Usunąć crashe i niespójności które blokują development.

Taski:

Backend:

Wprowadzić ThreadedConnectionPool do db.py — zastąpić wszystkie get_conn() wywołaniem z poola. To jest najpilniejszy task.
Usunąć backend/models/model.py lub przenieść jako backend/models/legacy_model.py z wyraźnym komentarzem.
Naprawić deduplikację w deduplicate_listings() — zachowuj ofertę z najnowszym updated_at nie pierwszą w liście.
Dodać fallback score dla świeżych instalacji: gdy brak ML modelu i brak RCN, użyj price_per_m2 porównany do mediany z zaindeksowanych ofert (market_position × 0.65 jako proxy).
Frontend:

Zastąpić card-premium klasami które faktycznie istnieją (card, card-accent) w Stats.jsx i Settings.jsx. To jednorazowe find-replace.
Usunąć Streamlit z docker-compose.yml i requirements.txt — albo wyraźnie oznaczyć jako legacy.
Testy:

Dodać prosty integration test: start → hunt → check listings count > 0. Można jako skrypt Python, nie pytest.
Zależności: Nic nie blokuje. Ryzyko: Niskie — zmiany defensywne. Sprint: 3-4 dni.

Stage 1 — Backend Core (Tydzień 2)
Cel: Solidna warstwa danych, poprawny scoring, stabilne API.

Taski:

Database:

Zaimplementować psycopg2.pool.ThreadedConnectionPool(minconn=2, maxconn=10) jako singleton w db.py.
Dodać indeks na listings(url, updated_at) dla szybkiego sprawdzania aktualizacji.
Dodać indeks na transaction_prices(invest_slug, district) — przyspiesza geocoding queries.
Dodać kolumnę preliminary_score w listings — oddzielona od score (który zawiera AI boost). Umożliwia pokazanie listy natychmiast po enrichmencie bez czekania na LLM.
Scoring:

Naprawić flow: preliminary_score zapisywany do DB natychmiast po enrichmencie, score aktualizowany po LLM.
Dodać score_version INT DEFAULT 1 do listings — inkrementowany przy każdej re-kalkulacji, ułatwia debugging.
Upewnić się że condition_multiplier() poprawnie parsuje polskie wartości ("dobry", "do remontu" itp.) — dodać test case.
API:

Dodać GET /listings/new — zwraca oferty dodane w ostatnich N godzinach, posortowane po preliminary_score. To jest core Sniper view.
Dodać GET /hunt/job/{job_id} — persystentny status joba (zapisywać do DB).
Naprawić rooms filtrowanie w get_hunt_listings() — konwersja typów przy porównaniu TEXT vs lista.
Zależności: Stage 0 musi być gotowy. Ryzyko: Średnie — zmiana w db.py może wprowadzić race conditions jeśli connection pool źle skonfigurowany. Sprint: 4-5 dni.

Stage 2 — Fetchery (Tydzień 3)
Cel: Scraping działa stabilnie dla min. 2 portali, obsługa 403, dedup aktualizacji.

Taski:

HTTP Client:

Dodać retry na 403 z losowym User-Agent switch. Obecny kod loguje 403 i zwraca "". Zmienić na: przy 403 czekaj 5-15s, zmień UA, retry max 2 razy.
Opcjonalnie: lista darmowych proxy rotacyjnych (webshare.io free tier) jako fallback.
Dodać X-Cache-Miss header logging — żeby wiedzieć kiedy Cloudflare blokuje.
Otodom/OLX:

Testy end-to-end: uruchomić scraper, sprawdzić liczbę wyników, porównać z ręcznym przeglądaniem strony.
Dodać validate_listing() — reject ofert bez ceny, bez powierzchni, lub z price_per_m2 < 2000 lub > 50000 (anomalie).
Morizon/Gratka:

Uruchomić raz, zalogować raw HTML do pliku, przeanalizować strukturę. Jeśli CSS selektory nie działają — naprawić lub oznaczyć jako DISABLED i nie ładować do PORTAL_SCRAPERS.
Lepiej mieć 2 działające portale niż 6 z których 4 zwracają puste wyniki.
Deweloperuch:

Dodać fetch_recent() wywołanie przy starcie jeśli baza ma < 100 transakcji dla danego cities — bez czekania na scheduler.
Rozważyć cache wyników get_rcn_benchmark() w Redis lub prostym dict z TTL=1h — bardzo często wywoływana funkcja.
Zależności: Stage 1. Ryzyko: Średnie — blokady portali są poza kontrolą. Sprint: 4-5 dni, można równolegle z Stage 1.

Stage 3 — AI Analysis (Tydzień 4)
Cel: LLM analiza działa dla 100% ofert w rozsądnym czasie, photo pipeline opcjonalny.

Taski:

LLM Pipeline:

Zmienić strategię: zamiast top 20 sync w huncie, zaimplementować prioritized queue. Queue ma priorytety: high (score ≥ 0.3), medium (score ≥ 0.15), low (reszta). Worker przetwarza high najpierw.
Dodać LLM_TIMEOUT = 45.0 jako constant — obecne 120s jest za długie, powoduje że jeden hanging request blokuje całą kolejkę.
Dodać batch processing: 3 oferty naraz jeśli Ollama obsługuje concurrent requests (sprawdzić /api/version).
Zapisywać llm_error_count per listing — jeśli > 3 próby failed, oznaczyć llm_analysis = {"error": "max_retries"} i nie próbować więcej.
Prompt engineering:

Obecny prompt jest dobry ale za długi (~3000 znaków opisu). Skrócić description do 1500 znaków z textwrap.shorten(). Krótszy prompt = szybsza odpowiedź = lepsza przepustowość.
Dodać przykład pożądanego output w prompcie (few-shot) — zwiększa jakość i zmniejsza JSON parse errors.
Photo Pipeline (opcjonalny):

Jeśli lokalnie: moondream działa na CPU z 4GB RAM dla jednego zdjęcia. Ograniczyć do 2 zdjęcia per listing, max 6 listings per batch.
Zależności: Stage 1, działający Ollama. Ryzyko: Wysokie — LLM jest niedeterministyczny, JSON parse errors zdarzają się. Sprint: 5-6 dni.

Stage 4 — Scoring Refinement (Tydzień 5)
Cel: Scoring jest dokładny, interpretable, i daje realne signal inwestycyjny.

Taski:

Zaimplementować prostą wersję ML predict bez joblib: weighted KNN lub linear regression na danych z listings i transaction_prices. Jeśli baza ma > 200 ofert — trenuj inline przy starcie, persist do DB jako JSON parametry.
Dodać anomaly_score — odchylenie ceny od ±2σ dla dzielnicy. Bardzo tanie obliczeniowo, duże znaczenie inwestycyjne.
Dodać days_since_price_drop — jeśli historia cen pokazuje obniżkę, bonus do scoringu. Wymaga sprawdzenia listing_history.
Kalibracja wag: zebrać feedback (gdy użytkownik kliknie "kupione" lub "nie interesuje" → supervised signal). Na razie: dokument z uzasadnieniem obecnych wag, żeby można było je tuningować świadomie.
Zależności: Stage 1, Stage 2 (żeby mieć danych). Sprint: 3-4 dni.

Stage 5 — Frontend (Tydzień 6)
Cel: UI jest użyteczny, szybki, i prezentuje bogate dane.

Taski:

Naprawić CSS (Stage 0 zrobił find-replace). Ujednolicić design system: card, card-accent, btn-primary, btn-ghost — wszystko z CSS vars.
Hunt page — jest dobry. Dodać: counter "ofert od ostatniego hunta", progress bar z eta (based on portal counts).
Listing card — dodać anomaly_score badge, days_since_price_drop jeśli > 0.
Stats page — naprawić wykresy (używać poprawnych klas CSS), dodać tabela "Top 10 okazji tego tygodnia", wykres "Nowe oferty per dzień".
Alerts page — dodać CRUD dla watchlist: create alert (nazwa, condition, min_score), toggle active, last_triggered timestamp. To jest core feature dla power users.
ListingDetail — historia cen z recharts działa, dodać mapę z Nominatim tile (leaflet.js, nie potrzeba API key), dodać "Porównaj z RCN" sekcję z gauge chart.
Zależności: Stage 0, Stage 1. Sprint: 5-6 dni, może częściowo równolegle ze Stage 3.

Stage 6 — Monitoring i Optymalizacja (Tydzień 7-8)
Cel: System jest obserwowalny, stabilny, gotowy na długotrwałe działanie.

Taski:

Dodać /health/detailed endpoint: DB connection count, pending AI count, last scrape timestamp per portal, Ollama status (ping), RCN coverage %.
Dodać structured logging (structlog lub python-json-logger) — aktualny logging to %s format strings, trudny do parsowania.
Dodać Prometheus metrics (opcjonalnie): scrape_duration_seconds, listings_saved_total, llm_analysis_duration_seconds, score_distribution_histogram.
Scheduled health check: jeśli przez 24h nie było scrape — wyślij Telegram alert na specjalny chat z diagnozą.
Playwright smoke test (opcjonalnie): raz na dobę uruchom headless browser, wejdź na stronę, sprawdź że listings się ładują.
Sprint: 4-5 dni.

6. Proponowany Stack Technologiczny
Warstwa	Obecny	Rekomendowany
Backend	FastAPI	FastAPI (zostać)
DB driver	psycopg2 (brak pool)	psycopg2 + ThreadedConnectionPool
AI Queue	asyncio.Queue in-process	asyncio.Queue v1, Redis v2
Scraping	httpx sync	httpx async (docelowo)
LLM	Ollama lokalne	Ollama + OpenAI fallback
Vision	moondream (OOM)	wyłączone lub OpenAI Vision
Frontend	React 19 + Vite	zostać
CSS	Tailwind 3 + CSS vars	zostać, naprawić klasy
Charts	recharts	zostać
Proxy	brak	webshare.io free (optional)
Observability	print/logging	structlog + /health/detailed
Testing	brak	pytest + httpx TestClient
7. Model Danych
Kluczowe zmiany w schemat
sql
-- listings: dodać kolumny
ALTER TABLE listings ADD COLUMN IF NOT EXISTS preliminary_score FLOAT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS score_version INT DEFAULT 1;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS anomaly_score FLOAT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS llm_error_count INT DEFAULT 0;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS price_drop_days INT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS last_enriched_at TIMESTAMP;

-- hunt_jobs: nowa tabela dla persystencji
CREATE TABLE IF NOT EXISTS hunt_jobs (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL,
    config JSONB NOT NULL,
    started_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP,
    total_scraped INT DEFAULT 0,
    total_saved INT DEFAULT 0,
    total_ai_analyzed INT DEFAULT 0,
    error TEXT,
    portals_counts JSONB DEFAULT '{}'
);

-- price_alerts: dla anomalii
CREATE TABLE IF NOT EXISTS price_alerts (
    id SERIAL PRIMARY KEY,
    listing_id INT REFERENCES listings(id),
    alert_type TEXT, -- 'price_drop', 'new_high_score', 'anomaly'
    old_value FLOAT,
    new_value FLOAT,
    triggered_at TIMESTAMP DEFAULT NOW(),
    sent_at TIMESTAMP
);
Snapshot strategy
listing_history jest zapisywana przy każdym upsert gdzie cena się zmieniła (dodać warunek WHEN price IS DISTINCT FROM EXCLUDED.price). Aktualnie zapisywana zawsze — generuje duplikaty.

8. Strategia Skalowania
Tysiące ofert: PostgreSQL z indeksami radzi sobie z 100k ofert bez problemu. JSONB kolumny (images, features, llm_analysis) powinny mieć GIN indeks jeśli filtrujemy po nich.

Częste aktualizacje: Scraping co 6h dla głównych portali = ~4 razy dziennie. Przy 500 ofertach per run = 2000 nowych rekordów dziennie. Bez problemu dla PostgreSQL.

Parallel processing: run_hunt_async() już używa asyncio.gather() per portal. Bottleneck jest rate limiting per portal (1-2s per request). Przy 3 stronach per portal × 6 portali = 18 requestów × 1.5s avg = 27s scraping. To jest OK.

Rate limits: Nominatim 1 req/s, Deweloperuch ~1.2s per page. Respectowane w kodzie.

Retry strategy: Obecna dla Deweloperuch (exponential backoff 4 próby) jest dobra. Brakuje dla scraperów Otodom/OLX przy 403.

Caching: rcn_cache dict in-memory per batch — wystarczy dla v1. Dla v2: Redis z TTL=1h dla get_rcn_benchmark() results.

Cost optimization: Ollama lokalne = $0 dla LLM. Główny koszt: electricity dla GPU lub czas CPU. Dla qwen2.5:7b na CPU: ~30-60s per listing. Top 20 = 10-20 minut. Akceptowalne.

9. Strategia AI
Element	Metoda	Uzasadnienie
price_per_m2 anomaly	Heurystyka (±2σ)	Szybkie, deterministyczne, wystarczające
market_position	SQL median	Dokładne, bez AI
rcn_gap	Porównanie mediany	Dane transakcyjne są ground truth
text analysis	LLM (Ollama)	Opis ma nuance którego keyword matching nie łapie
condition detection	LLM z prompt	"stan: do remontu" może być ukryte w opisie
urgency signals	LLM	"pilna sprzedaż" w różnych formach
photo condition	Vision AI (opcjonalnie)	High value, high cost — feature flag
price prediction	Linear regression na market stats	ML model wymaga danych, regression działa od 0
similarity search	Nie wdrażać w v1	Over-engineering, zamiast tego filtrowanie SQL
embeddings	Nie wdrażać	Potrzeba pgvector, zbędna złożoność na tym etapie
Kluczowa zasada: LLM używaj tylko tam gdzie structured parsing zawodzi. Opis nieruchomości to idealny use case (niestrukturyzowany tekst, różne formaty, ukryta informacja). Ceny, daty, metraże — SQL i math.

10. Finalna Rekomendacja
Przebudować natychmiast
DB connection pool — jeden dzień, krytyczny
CSS klasy w Stats/Settings — godzina, widoczne crashe
Deduplikacja — jeden dzień, dane są niespójne
Zostawić bez zmian
backend/model.py — architektura scoringu jest dobra
backend/scrapers/deweloperuch.py — najlepszy moduł, nie ruszać
backend/hunt_manager.py — SSE działa, flow jest OK
backend/nlp/llm_scorer.py — prompt jest dobry
Frontend Hunt.jsx — dobry UI, dobre live updates
Usunąć
dashboard/ (Streamlit) — dead code, konfuzja dla developera
backend/debug_*.py, backend/diag_*.py, backend/test_*.py, backend/force_ingest.py — pliki dev w katalogu produkcyjnym
backend/models/model.py (jeśli istnieje) — duplicate
Przepisać od zera
backend/db.py — za długi (600+ linii), brak pool, mieszanie odpowiedzialności. Podzielić na db/connection.py, db/listings.py, db/market.py, db/alerts.py.
Scrapers Morizon/Gratka/Domiporta — szkieletowe i niefunkcjonalne. Albo naprawić z prawdziwym testowaniem, albo usunąć z PORTAL_SCRAPERS do czasu naprawy.
Rekomendowana kolejność działań
Stage 0 (3-4 dni) → Stage 1 + Stage 2 równolegle (5 dni) → Stage 3 (5-6 dni) → Stage 4 + Stage 5 równolegle (6 dni) → Stage 6 (4 dni).

Łącznie: 5-6 tygodni do wersji produkcyjnej gotowej na długotrwałe działanie.

Quick Wins
Fix CSS klas w Stats.jsx — 1h, usuwa błędy renderowania
DB connection pool — 1 dzień, krytyczna stabilność
Retry na 403 w scraperach — 2h, +20% skuteczności scrapingu
Skrócić LLM timeout 120s → 45s — 10 minut, szybsza kolejka AI
Usunąć pliki debug z repo — 30 minut, czystszy codebase
Dodać validate_listing() — 2h, lepsze dane
Wyłączyć martwe portale z PORTAL_SCRAPERS — 30 minut, mniej false negatives w logach
High Risk Areas
LLM pipeline przy Ollama timeout — jeden hanging request może zablokować całą fazę AI hunta
403 scraping bez retry — Otodom/OLX mogą przestać działać po zmianie Cloudflare rules
Brak persystencji stanu joba — restart podczas hunta = użytkownik widzi spinner na zawsze
RCN geocoding Nominatim — rate limit 1 req/s przy dużej bazie = godziny na uzupełnienie dzielnic
Tech Debt
db.py jako monolityczny plik 600+ linii
Synchroniczne httpx.Client w async context przez run_in_executor
Brak typów (mypy) w całym backendzie
Brak testów jednostkowych dla krytycznych funkcji (scoring, dedup, parsing)
Podwójny UI (Streamlit legacy)
force_ingest.py i pliki debug w katalogu produkcyjnym
requirements.txt zawiera streamlit, folium, streamlit-folium — 200MB+ niepotrzebnych zależności w image backendowym
Co Może Zabić Ten Projekt Produkcyjnie
1. Otodom i OLX zmieniają strukturę JSON — cały parser przestaje działać, 0 ofert. Brak alertu o tym. Potrzebny monitoring listings_count per portal per day.

2. Ollama OOM — qwen2.5:7b potrzebuje ~6GB RAM. Na maszynie z 8GB + system + Postgres = edge case. moondream dodatkowo. Cała AI pipeline pada cicho (timeout), użytkownik widzi score bez AI boost ale nie wie dlaczego.

3. Connection exhaustion — brak pool, przy 10 concurrent requests do API każdy tworzy nowe połączenie PG. PostgreSQL ma default max_connections=100. Przy intensywnym użyciu scheduler + API + hunt = crash.

4. Deweloperuch zmienia API — jedyne źródło danych RCN. Brak fallback. Jeśli endpoint zmieni strukturę JSON, rcn_benchmark = NULL dla wszystkich, scoring degeneruje.

5. Akumulacja llm_analysis = {"error": "llm_failed"} — bez llm_error_count limitu, scheduler próbuje w nieskończoność te same oferty. Kolejka się nie opróżnia, nowe oferty nie dostają analizy.

