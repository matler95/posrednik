WREI — Plan kompletny
Stack techniczny
WarstwaTechnologiaBackendFastAPI + Python 3.12Baza danychPostgreSQL 15Scrapinghttpx (async) + BeautifulSoup + NEXT_DATAML wycenascikit-learn (GradientBoosting)NLP preprocessingspaCy pl_core_news_smLLM scoringOllama (qwen2.5:7b)CV zdjęciaCLIP (pre-filter) + Ollama Vision (llava:7b)SchedulerAPSchedulerAlertyTelegram Bot APIDashboardStreamlit → React (Faza 6)KonteneryzacjaDocker Compose

Faza 1 — Stabilizacja i rozszerzenie scraperów
Cel: wiarygodne dane z 4+ portali, brak crashy, solidna baza
1.1 Naprawa bugów krytycznych

psycopg2 vs psycopg — ujednolicić na psycopg2-binary w całym projekcie
Morizon — zarejestrować w PORTAL_SCRAPERS i AVAILABLE_PORTALS
OLX area — wyciągać z tytułu regexem (55m², 55 m2); jeśli brak → lazy fetch strony detalu
OLX portal field — dodać "portal": "olx" do każdego listingu
Otodom direct_offer — obecna logika (agency is None) niepewna; weryfikować przez pole advertType

1.2 Nowe portale
Gratka (gratka.pl/nieruchomosci/mieszkania/warszawa)

BeautifulSoup, struktura zbliżona do Morizon
Filtry przez query params: cena-od, cena-do, powierzchnia-od

Domiporta (domiporta.pl)

__NEXT_DATA__ jak Otodom — parser analogiczny

Nieruchomosci-online (nieruchomosci-online.pl)

Publiczne REST API JSON — najłatwiejszy do integracji

Każdy portal jako osobny moduł w scrapers/, auto-rejestracja:
python# scrapers/__init__.py — auto-discovery
import pkgutil, importlib
for _, name, _ in pkgutil.iter_modules(__path__):
    module = importlib.import_module(f".{name}", __package__)
    if hasattr(module, "available") and hasattr(module, "search"):
        PORTAL_SCRAPERS[module.available()] = module.search
        AVAILABLE_PORTALS.append(module.available())
1.3 Solidność scraperów

httpx zamiast requests (async-ready, lepszy timeout handling)
Exponential backoff + jitter — 3 próby, czekaj 2^n + random(0,1)s
Rotacja User-Agent z listy 10 realnych przeglądarek
Per-portal rate limiting — token bucket, konfigurowalne opóźnienie
Opcjonalne proxy pool przez PROXY_LIST env var
Zapis surowego HTML do /tmp/wrei_debug/ przy błędzie parsowania

1.4 Rozbudowa schematu DB
sql-- Rozszerzenie tabeli listings
ALTER TABLE listings ADD COLUMN images JSONB;          -- URLe zdjęć
ALTER TABLE listings ADD COLUMN features JSONB;        -- balkon, garaż, etc.
ALTER TABLE listings ADD COLUMN floor INT;
ALTER TABLE listings ADD COLUMN total_floors INT;
ALTER TABLE listings ADD COLUMN year_built INT;
ALTER TABLE listings ADD COLUMN heating TEXT;
ALTER TABLE listings ADD COLUMN condition TEXT;        -- nowy/dobry/remont
ALTER TABLE listings ADD COLUMN building_type TEXT;   -- blok/kamienica/apartament
ALTER TABLE listings ADD COLUMN ownership TEXT;        -- własność/spółdzielcze
ALTER TABLE listings ADD COLUMN llm_analysis JSONB;   -- wynik Ollama (Faza 3)
ALTER TABLE listings ADD COLUMN photo_analysis JSONB; -- wynik CV (Faza 4)
ALTER TABLE listings ADD COLUMN first_seen TIMESTAMP DEFAULT NOW();
ALTER TABLE listings ADD COLUMN days_on_market INT;

-- Nowe tabele
CREATE TABLE market_stats (
    id SERIAL PRIMARY KEY,
    district TEXT,
    rooms INT,
    condition TEXT,
    avg_price_per_m2 FLOAT,
    median_price_per_m2 FLOAT,
    p25_price_per_m2 FLOAT,
    p75_price_per_m2 FLOAT,
    sample_count INT,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE portals (
    name TEXT PRIMARY KEY,
    enabled BOOLEAN DEFAULT TRUE,
    last_scraped TIMESTAMP,
    listings_last_run INT,
    error_rate FLOAT
);

CREATE TABLE watchlist (
    id SERIAL PRIMARY KEY,
    name TEXT,
    filters JSONB,
    alert_threshold FLOAT DEFAULT 0.15,
    channels JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
1.5 Testy

pytest + httpx async client
Mocki HTML dla każdego scrapera (zapisane snapshoty stron)
Test parsowania dla 5 przykładowych ogłoszeń per portal


Faza 2 — Model wyceny ML
Cel: wycena niezależna od aktualnej partii danych, oparta na historii
2.1 Budowa historycznej bazy cenowej
listing_history już istnieje — rozbudować:
sqlALTER TABLE listing_history ADD COLUMN district TEXT;
ALTER TABLE listing_history ADD COLUMN rooms INT;
ALTER TABLE listing_history ADD COLUMN condition TEXT;
ALTER TABLE listing_history ADD COLUMN price_per_m2 FLOAT;
ALTER TABLE listing_history ADD COLUMN building_type TEXT;
ALTER TABLE listing_history ADD COLUMN floor INT;
ALTER TABLE listing_history ADD COLUMN year_built INT;
Każdy save_listings() → insert do listing_history (snapshot ceny w czasie).
Agregaty market_stats przeliczane co 24h przez APScheduler.
Minimum 30 próbek per segment; fallback na szerszy segment (dzielnica → Warszawa).
2.2 Model ML
Cechy wejściowe:
pythonfeatures = [
    "area",                    # metraż
    "rooms",                   # liczba pokoi
    "floor_ratio",             # piętro / liczba pięter
    "year_built",              # rok budowy
    "condition_encoded",       # nowy=3, dobry=2, średni=1, remont=0
    "building_type_encoded",   # apartament=3, kamienica=2, blok=1
    "has_balcony",
    "has_parking",
    "has_elevator",
    "has_storage",
    "district_encoded",        # target encoding po medianie ceny
    "ownership_encoded",       # własność=1, spółdzielcze=0
]
Model: GradientBoostingRegressor (interpretowalny, nie wymaga GPU, działa na 1000+ próbkach)
Pipeline:
python# backend/ml/trainer.py
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingRegressor
import joblib

pipeline = Pipeline([
    ("scaler", StandardScaler()),
    ("model", GradientBoostingRegressor(n_estimators=200, max_depth=4))
])
# Zapis: models/wycena_YYYYMMDD.joblib
# Symlink: models/wycena_latest.joblib
Walidacja: MAE < 10% wartości na zbiorze testowym; jeśli nie przejdzie → fallback na market_stats.
Trening co niedzielę o 02:00 przez APScheduler. Minimalnie 200 próbek żeby trenować.
2.3 Nowy composite score
pythondef opportunity_score(listing, market_stats, ml_estimate):
    # Składowe
    price_gap     = max(0, (ml_estimate - listing.price) / ml_estimate)  # 0-1
    market_pos    = market_position(listing, market_stats)                # 0-1
    freshness     = 1.0 if listing.days_on_market < 1 else 0.0           # bonus za świeżość
    direct        = 0.1 if listing.direct_offer else 0.0
    text_score    = listing.text_score or 0.0                            # Faza 3
    photo_score   = listing.photo_score or 0.0                           # Faza 4

    # Mnożnik stanu
    condition_mult = {"nowy": 1.0, "dobry": 0.95, "sredni": 0.85, "remont": 0.70}
    mult = condition_mult.get(listing.condition, 0.90)

    raw = (
        price_gap     * 0.40 +
        market_pos    * 0.20 +
        freshness     * 0.10 +
        direct        * 0.10 +
        text_score    * 0.10 +
        photo_score   * 0.10
    ) * mult

    return round(min(max(raw, 0.0), 1.0), 4)

Faza 3 — Analiza tekstu (NLP + Ollama)
Cel: wyciągnąć cechy i ocenić jakość ogłoszenia z opisu
3.1 spaCy — preprocessing (szybki, lokalny)
Odpalany synchronicznie przed Ollama, wyciąga liczby i fakty:
python# backend/nlp/extractor.py
import spacy
nlp = spacy.load("pl_core_news_sm")

def extract_structured_features(text: str) -> dict:
    doc = nlp(text)
    return {
        "floor":        extract_floor(doc),       # "4 piętro", "IV p."
        "year_built":   extract_year(doc),         # "z 1998 roku"
        "area_mention": extract_area(doc),         # weryfikacja vs scraper
        "has_balcony":  "balkon" in text.lower(),
        "has_garage":   any(w in text.lower() for w in ["garaż", "parking", "miejsce postojowe"]),
        "has_elevator": any(w in text.lower() for w in ["winda", "windą"]),
        "has_storage":  any(w in text.lower() for w in ["piwnica", "komórka", "schowek"]),
        "has_garden":   any(w in text.lower() for w in ["ogród", "ogródek", "taras"]),
    }
3.2 Ollama — głęboka analiza (async, tylko dla kandydatów)
Trigger: ogłoszenie przechodzi wstępny scoring price_gap > 0.08.
python# backend/nlp/llm_scorer.py
import httpx, json

OLLAMA_URL = "http://ollama:11434/api/chat"
MODEL = "qwen2.5:7b"

PROMPT = """Jesteś doświadczonym pośrednikiem nieruchomości w Warszawie z 15-letnim doświadczeniem.
Przeanalizuj ogłoszenie i odpowiedz WYŁĄCZNIE poprawnym JSON, bez żadnego tekstu przed ani po:

{
  "condition": "nowy|dobry|sredni|remont",
  "urgency_signals": ["lista sygnałów pilnej sprzedaży"],
  "red_flags": ["lista ostrzeżeń"],
  "green_flags": ["lista atutów"],
  "renovation_cost_per_m2": null lub liczba całkowita w PLN,
  "location_quality": 0-10,
  "investment_score": 0-10,
  "negotiation_potential": 0-10,
  "summary": "2-3 zdania po polsku — ocena dla kupującego"
}

Dane ogłoszenia:
Tytuł: {title}
Dzielnica: {district}
Cena: {price} PLN | Metraż: {area}m² | Pokoje: {rooms}
Opis: {description}"""

async def analyze_listing(listing: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(OLLAMA_URL, json={
            "model": MODEL,
            "messages": [{"role": "user", "content": PROMPT.format(**listing)}],
            "stream": False,
            "format": "json"
        })
    return json.loads(response.json()["message"]["content"])
Strategia wykonania:

FastAPI BackgroundTasks — nie blokuje /search
Wynik zapisywany do listings.llm_analysis
Raz przeanalizowane → nie analizowane ponownie (cache w DB)
Timeout 30s; przy błędzie → None, scoring działa bez LLM

3.3 Text score do composite
pythondef text_score_from_llm(llm_analysis: dict) -> float:
    if not llm_analysis:
        return 0.0
    investment = llm_analysis.get("investment_score", 5) / 10
    negotiation = llm_analysis.get("negotiation_potential", 5) / 10
    red_flag_penalty = len(llm_analysis.get("red_flags", [])) * 0.05
    urgency_bonus = 0.1 if llm_analysis.get("urgency_signals") else 0.0
    return round(max(0.0, min((investment * 0.6 + negotiation * 0.4) + urgency_bonus - red_flag_penalty, 1.0)), 4)

Faza 4 — Analiza zdjęć (CLIP + Ollama Vision)
Cel: automatyczna ocena stanu mieszkania ze zdjęć
4.1 Pobieranie zdjęć
Scraper zapisuje URL-e do listings.images JSONB. Worker pobiera i zapisuje lokalnie:
python# backend/cv/fetcher.py
async def fetch_images(listing_id, image_urls, max_images=5):
    path = Path(f"/data/images/{listing_id}")
    path.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient() as client:
        for i, url in enumerate(image_urls[:max_images]):
            response = await client.get(url)
            (path / f"{i}.jpg").write_bytes(response.content)
4.2 CLIP — pre-filter zdjęć
Odrzucenie zdjęć nieużytecznych (rzut, plan piętra, okładka z logo) zanim trafią do LLaVA:
python# backend/cv/clip_filter.py
from transformers import CLIPProcessor, CLIPModel
import torch

model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

REJECT_LABELS = ["floor plan", "blueprint", "logo", "map", "diagram"]
ACCEPT_LABELS = ["apartment interior", "room photo", "kitchen", "bathroom", "living room"]

def is_useful_photo(image) -> bool:
    inputs = processor(text=REJECT_LABELS + ACCEPT_LABELS, images=image, return_tensors="pt")
    logits = model(**inputs).logits_per_image.softmax(dim=1)[0]
    reject_score = logits[:len(REJECT_LABELS)].max().item()
    return reject_score < 0.4
4.3 Ollama Vision — analiza stanu
python# backend/cv/vision_scorer.py
import base64, httpx, json

MODEL = "llava:7b"

PROMPT = """Jesteś ekspertem od oceny nieruchomości. Przeanalizuj to zdjęcie mieszkania.
Odpowiedz WYŁĄCZNIE poprawnym JSON:
{
  "condition": "nowy|dobry|sredni|remont",
  "bright": true|false,
  "furnished": true|false,
  "visible_issues": ["lista problemów widocznych na zdjęciu"],
  "premium_features": ["lista cech premium"],
  "confidence": 0-1,
  "score": 0-10
}"""

async def analyze_photo(image_path: str) -> dict:
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post("http://ollama:11434/api/chat", json={
            "model": MODEL,
            "messages": [{"role": "user", "content": PROMPT, "images": [image_b64]}],
            "stream": False,
            "format": "json"
        })
    return json.loads(response.json()["message"]["content"])

async def analyze_listing_photos(listing_id: int) -> dict:
    images_dir = Path(f"/data/images/{listing_id}")
    results = []
    for img_path in sorted(images_dir.glob("*.jpg"))[:5]:
        image = Image.open(img_path)
        if is_useful_photo(image):
            result = await analyze_photo(str(img_path))
            if result.get("confidence", 0) > 0.5:
                results.append(result)

    if not results:
        return {}

    # Agregacja wyników z wielu zdjęć
    avg_score = sum(r["score"] for r in results) / len(results)
    all_issues = [issue for r in results for issue in r.get("visible_issues", [])]
    conditions = [r["condition"] for r in results]
    dominant_condition = max(set(conditions), key=conditions.count)

    return {
        "condition": dominant_condition,
        "photo_score": round(avg_score / 10, 4),
        "visible_issues": list(set(all_issues)),
        "photos_analyzed": len(results),
    }

Faza 5 — Automatyzacja i alerty
Cel: apka działa 24/7, użytkownik dostaje powiadomienia o okazjach
5.1 Scheduler — pełny harmonogram
pythonjobs = [
    # Scrapowanie
    ("otodom",        "0 6,12,18 * * *",  {"pages": 5}),
    ("olx",           "30 6,12,18 * * *", {"pages": 3}),
    ("gratka",        "0 7,13,19 * * *",  {"pages": 3}),
    ("domiporta",     "30 7,13,19 * * *", {"pages": 2}),
    ("nieruch_online","0 8,14,20 * * *",  {"pages": 2}),

    # Analiza i ML
    ("llm_queue",     "*/10 * * * *",     {}),   # przetwarza kolejkę Ollama co 10 min
    ("photo_queue",   "*/15 * * * *",     {}),   # przetwarza zdjęcia co 15 min
    ("stats_update",  "0 3 * * *",        {}),   # market_stats co noc
    ("ml_retrain",    "0 2 * * 0",        {}),   # retrain modelu co niedzielę

    # Alerty
    ("alert_check",   "*/15 * * * *",     {}),   # sprawdź alerty co 15 min
    ("daily_digest",  "0 8 * * *",        {}),   # dzienny raport na Telegram
]
5.2 System alertów
Alerty trzymane w tabeli alerts jako wyrażenia Python (sandbox eval):
python# backend/alerts/evaluator.py
SAFE_BUILTINS = {}
SAFE_NAMES = {"score", "price", "area", "district", "direct_offer",
              "rooms", "price_per_m2", "condition", "days_on_market"}

def evaluate_alert(expression: str, listing: dict) -> bool:
    context = {k: listing.get(k) for k in SAFE_NAMES}
    try:
        return bool(eval(expression, {"__builtins__": SAFE_BUILTINS}, context))
    except Exception:
        return False

# Przykłady wyrażeń w UI:
# "score > 0.30 and district == 'Mokotów'"
# "price < 600000 and area > 50 and direct_offer == True"
# "price_per_m2 < 12000 and rooms >= 3"
# "condition == 'remont' and score > 0.40"
5.3 Kanały powiadomień
python# backend/alerts/channels.py

async def send_telegram(listing, alert_name):
    text = f"""🏠 *Nowa okazja: {alert_name}*
📍 {listing['district']} | {listing['rooms']} pok. | {listing['area']}m²
💰 {listing['price']:,} PLN ({listing['price_per_m2']:.0f} PLN/m²)
📊 Score: {listing['score']*100:.1f}%
{'✅ Oferta bezpośrednia' if listing['direct_offer'] else '🏢 Biuro nieruchomości'}
🔗 {listing['url']}"""
    # POST do Telegram Bot API

async def send_daily_digest(opportunities):
    # Top 5 okazji dnia, podsumowanie rynku
    # Wysyłka o 8:00
5.4 CRUD alertów przez API
GET    /alerts           — lista alertów
POST   /alerts           — nowy alert
PUT    /alerts/{id}      — edycja
DELETE /alerts/{id}      — usunięcie
POST   /alerts/{id}/test — test na ostatnich 100 ogłoszeniach
5.5 Watchlist
POST   /watchlist        — zapisz wyszukiwanie
GET    /watchlist        — lista zapisanych wyszukiwań
DELETE /watchlist/{id}

Faza 6 — Dashboard
Cel: profesjonalny interfejs, przydatny dla kupującego i inwestora
6.1 Streamlit — rozbudowa (szybka droga, ~3 dni)

Mapa — Folium/Plotly z pinezkami ogłoszeń, kolorowanie po score
Karty okazji — zamiast tabeli: zdjęcie + kluczowe dane + score gauge
Wykresy rynkowe — histogram cen per dzielnica, scatter price vs area, trend tygodniowy
Panel alertów — CRUD bezpośrednio w UI
Historia ceny — line chart dla pojedynczego ogłoszenia
LLM summary — wyświetlanie analizy Ollama przy ogłoszeniu

6.2 React (docelowo, ~1 tydzień)
Nowe endpointy FastAPI:
GET /listings            — paginacja, filtry, sortowanie
GET /listings/{id}       — szczegóły + historia + analiza
GET /opportunities       — top okazje
GET /stats/market        — statystyki rynkowe
GET /stats/districts     — per dzielnica
Stack frontendu:

React + Vite
shadcn/ui + Tailwind
Recharts (wykresy)
Leaflet (mapa)
TanStack Query (fetching/cache)


Harmonogram implementacji
Tydzień 1:  Faza 1 — stabilizacja, 4 portale, solidne scrapowanie
Tydzień 2:  Faza 2 — ML wycena, historyczna baza, nowy scoring
Tydzień 3:  Faza 3 — NLP (spaCy) + Ollama text scoring
Tydzień 4:  Faza 4 — CLIP filter + Ollama Vision
Tydzień 5:  Faza 5 — scheduler, alerty, Telegram digest
Tydzień 6:  Faza 6 — dashboard Streamlit rozbudowa
Tydzień 7+: Faza 6 — React frontend (opcjonalnie)