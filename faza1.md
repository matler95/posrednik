Podsumowanie Fazy 1
Co zostało zrobione
1.1 Naprawa bugów

psycopg[binary] → psycopg2-binary — ujednolicony driver
Morizon zarejestrowany w PORTAL_SCRAPERS
OLX: area wyciągana z tytułu/tekstu regexem, dodane portal field
Otodom: direct_offer przez advertType zamiast agency is None
Wszystkie scrapery mają **kwargs — odporne na nieznane parametry

1.2 Nowe portale

Gratka — BeautifulSoup, wielostopniowy fallback selektorów
Domiporta — __NEXT_DATA__ parser z logowaniem kluczy przy braku danych
Nieruchomosci-online — REST API JSON z wieloma fallback kluczami

1.3 Solidność scraperów

httpx + tenacity — 3 próby, exponential backoff + jitter
Rotacja 7 User-Agentów z realistycznymi headerami
Token bucket rate limiter per portal (konfigurowalne opóźnienia)
Zapis debug HTML do /tmp/wrei_debug/ przy pustej odpowiedzi
Sync API (drop-in) + async API gotowe pod Fazę 3/4

1.4 Schemat DB

Migracje SQL w plikach 001_initial.sql i 002_migrate_existing.sql
System śledzenia migracji (schema_migrations)
Nowe kolumny: images, features, floor, year_built, condition, building_type, ownership, llm_analysis, photo_analysis, days_on_market
Nowe tabele: market_stats, portals, watchlist
Rozbudowane listing_history z pełnym kontekstem
Indeksy na często filtrowanych kolumnach
Nowe query helpers: get_listings(), get_listing_price_history()

