Diagnoza WREI — krytyczne problemy
1. Błąd krytyczny (blokuje działanie):
 Brak retry na bot-detection (403)
 Deduplikacja po URL (gubią się uaktualnienia)
 Tylko Otodom + OLX działa stabilnieRCN / Deweloperuch
 Dwa pliki model.py (backend/ i models/)
 score = 0 gdy brak RCN (NULL * 0.30 = 0)
 ML predictor zawsze zwraca (None, False)
 text_score bazuje na keyword match, nie LLMPipeline AI (LLM + Vision)
 /hunt/status odwołuje się do job.total_found
 /hunt/results nie filtruje wg hunt_config
 SSE stream nie emituje enriching_doneFrontend React
2. Problem poważny (degraduje jakość):
 District = NULL dla 90% transakcji
 Geocoding Nominatim: 1 req/s (za wolny)
 RCN benchmark zwraca NULL gdy <5 próbekSilnik scoringu
 LLM w tle — oferty pokazane bez analizy
 photo_score zawsze 0 (moondream OOM)
 Brak priorytetyzacji wg hunt config
 60s timeout Ollama często = NoneAPI / Backend endpoints
 Dwa UI: Streamlit + React (niezsynchronizowane)
 Brak widoku analizy AI inline
Plan naprawy — 4 fazy (priorytet = kolejność)Faza 1: Napraw scraping (proxy/UA rotation) + ujednolicenie model.py + fallback score gdy NULL RCNFaza 2: Geocoding z OpenStreetMap Overpass API (batch, bez rate-limit) + RCN benchmark z interpolacjąFaza 3: Synchroniczny LLM w hunt pipeline (top 20 ofert analizowane PRZED wyświetleniem)

Krytyczne (blokują core feature):
backend/model.py i backend/models/model.py to dwa różne pliki z różnymi wagami scoringu. analysis.py importuje z tego pierwszego. Wynik: opportunity_score() używa starych wag gdzie text_score ma wagę 0.15 a foto 0.10, podczas gdy nowy plik (models/) ma lepszy model z dynamicznymi wagami. Efekt: scoring jest niespójny i nieprzewidywalny.
score = 0 gdy brak RCN — transaction_gap_ratio() zwraca 0.0 gdy rcn_benchmark is None, więc 20-30% scoringu odpada dla nowych ofert bez benchmarku. Inwestor widzi oferty z score 0.05 które powinny mieć 0.25.
Geocoding Nominatim 1 req/s + 90% transakcji bez dzielnicy = RCN benchmark praktycznie nie działa dla żadnej dzielnicy poza kilkoma które trafiły przez invest_slug cache.
Poważne (degradują jakość):
LLM analiza w tle — inwestor po uruchomieniu polowania widzi oferty bez żadnej analizy AI przez 10-30 minut. Nie to jest obiecane.
/hunt/status odwołuje się do job.total_found który nie istnieje w HuntJob (jest total_scraped). Powoduje AttributeError w produkcji.

Plan przebudowy — priorytety
Faza 1 — Fundament (napraw to co jest zepsute)
1. Ujednolicenie scoringu — usunąć backend/models/model.py, zostawić jeden backend/model.py z tymi wagami:
price_gap    0.35  (ML/avg estimate vs cena oferty)
txn_gap      0.30  (RCN transakcje vs cena/m²)
market_pos   0.15  (vs bieżące oferty)
freshness    0.12  (bonus <1 dzień)
direct       0.08  (bezpośrednia)
+ AI boost: text +8%, photo +5% (addytywne, nie zastępują bazy)
Fallback score gdy brak RCN — gdy rcn_benchmark is None, nie zerować tej składowej, tylko użyć weighted fallback z market_stats (mediany dzielnicowej z tabeli market_stats zamiast z transaction_prices). To daje sensowny benchmark nawet bez RCN.
2. Napraw geocoding — zamiast Nominatim dla transakcji RCN, użyć OpenStreetMap Overpass API z batch query po nazwie inwestycji. Alternatywnie: przy imporcie RCN wyciągać dzielnicę z pola invest.name lub street_address przez prosty string matching z listą warszawskich dzielnic (wystarczy regex na "Mokotów", "Wola" itp. — 70% przypadków to da).
pythonWARSAW_DISTRICTS_PATTERNS = {
    "Mokotów": r"mokot", "Wola": r"\bwola\b", "Śródmieście": r"śródmie|srodmie",
    # ...
}
def extract_district_from_address(address: str) -> str | None:
    addr_lower = address.lower()
    for district, pattern in WARSAW_DISTRICTS_PATTERNS.items():
        if re.search(pattern, addr_lower, re.I):
            return district
    return None
To unblokuje RCN benchmarki natychmiast bez czekania na Nominatim.
3. Napraw AttributeError w /hunt/status — zmienić job.total_found na job.total_scraped.

Faza 2 — Celowane polowanie (core feature)
To jest serce aplikacji. Schemat flow:
Inwestor ustawia profil (raz, zapisany w DB)
  → Uruchom polowanie
  → Scrape równoległy (Otodom + OLX, 3-5 stron)
  → Enrich: price/m², market_pos, RCN gap (instant)
  → Zapisz do DB, wyświetl listę z preliminary score
  → TOP 20 ofert → synchroniczna analiza LLM (przed wyświetleniem)
  → Pozostałe → kolejka w tle
Kluczowa zmiana: LLM musi analizować top oferty SYNCHRONICZNIE w trakcie polowania, nie w tle. Inwestor czeka 2-3 minuty ale dostaje kompletną analizę od razu.
Zmiany w hunt_manager.py:
python# Po zapisie do DB, przed emitem "done":
top_listings = sorted(enriched, key=lambda x: x.get('score', 0), reverse=True)[:20]

# Synchroniczna analiza (nie jako background task)
job.emit("status", {"message": "🧠 Analiza AI top 20 ofert..."})
for listing in top_listings:
    analysis = await analyze_listing_with_llm(listing)
    if analysis:
        save_llm_analysis(listing["url"], analysis)
        # Aktualizuj score z text_score
        job.emit("ai_done", {...})
    await asyncio.sleep(1.5)  # rate limit

Faza 3 — Dashboard dla inwestora
Strona główna — wyniki polowania:
Każda karta oferty musi pokazywać jednocześnie:

Cena vs benchmark RCN (ile poniżej/powyżej rynku transakcyjnego)
AI Score z komponentami (RCN gap %, text_score, kondycja)
Podsumowanie LLM (2-3 zdania, red flags, green flags)
Historia ceny jeśli widziana wcześniej
Bezpośrednia/pośrednia + link do ogłoszenia

Zakładka Statystyki (insights):

Trend cenowy wg dzielnicy (z RCN quarterly data)
Luka ofertowa vs transakcyjna per dzielnica (gdzie największy potencjał negocjacji)
Rozkład score w aktualnych wynikach
Histogram cena/m² dla wybranych filtrów vs benchmark

Zakładka Ustawienia profilu:

Tylko najważniejsze: przedział cenowy, metraż, dzielnice, pokoje, portale
Zapisane w DB, persistentne


Faza 4 — Jakość danych i monitoring

Alerter Telegram: wysyłaj gdy score > próg I oferta pasuje do profilu
Retrain ML co niedzielę (ale dopiero gdy >200 ofert w DB)
Dashboard healthcheck: ile ofert, % z LLM analizą, % z RCN benchmarkiem, ostatni scrape


Co zostawić bez zmian
Scraper Otodom i OLX działają — tylko potrzebują lepszego obsługiwania 403 (retry z innym UA, exponential backoff). Reszta scraperów (Morizon, Gratka, Domiporta) to nice-to-have. Infrastruktura Docker jest dobra. APScheduler wystarczy.

Konkretne pliki do modyfikacji (w kolejności)

backend/hunt_manager.py — synchroniczna LLM dla top 20, fix AttributeError
backend/scrapers/deweloperuch.py — regex geocoding z nazwy adresu
backend/main.py — fix /hunt/status
frontend/src/pages/Hunt.jsx — redesign kart z komponentami score
frontend/src/pages/Stats.jsx — wykresy RCN gap per dzielnica
Usuń backend/models/model.py

