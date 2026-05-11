# Raport z Realizacji Projektu: WREI Real Estate AI

## 1. Cel Projektu
Budowa zintegrowanej platformy analitycznej do automatycznej identyfikacji okazji inwestycyjnych na rynku nieruchomości (Warszawa i inne miasta), opartej na danych transakcyjnych (RCN) oraz zaawansowanej analizie AI (LLM & Vision).

## 2. Architektura Systemu
System został wdrożony w oparciu o architekturę mikroserwisową w kontenerach Docker:
- **Backend (FastAPI)**: Rdzeń systemu obsługujący scraping, logikę biznesową i scoring.
- **Baza Danych (PostgreSQL 15)**: Przechowywanie ofert, danych historycznych RCN i analiz AI.
- **Dashboard (Streamlit)**: Interfejs użytkownika z mapami, wykresami i filtrami.
- **Ollama (Host)**: Serwer AI obsługujący modele `qwen2.5` (analiza tekstu) oraz `moondream` (analiza zdjęć).

## 3. Zrealizowane Moduły i Funkcjonalności

### A. Pipeline Danych Transakcyjnych (RCN)
- **Integracja z Deweloperuch**: Pobieranie realnych cen sprzedaży nieruchomości.
- **Automatyczne Statystyki**: System wylicza mediany cen dla miast i dzielnic.
- **Analiza Trendów**: Wyliczanie CAGR (skumulowany roczny wskaźnik wzrostu) oraz luki ofertowo-transakcyjnej.
- **Freshness Sync**: Skonfigurowano głęboki pobór danych (do 100 stron wstecz), aby zapewnić aktualność bazy.

### B. Wieloportalowy Scraper
- **Obsługa Portali**: Otodom, OLX i inne.
- **Wyciąganie Danych**: Ceny, metraże, opisy, a także **zdjęcia** (naprawiono błąd braku linków do mediów).
- **Detekcja Ofert Bezpośrednich**: Automatyczne flagowanie ogłoszeń od osób prywatnych.

### C. Silnik AI Scoringu
- **LLM Scorer (Qwen2.5)**: Analizuje opisy ofert pod kątem ukrytych wad, potencjału inwestycyjnego i wiarygodności.
- **Vision Scorer (Moondream)**: (W trakcie optymalizacji RAM) Analiza zdjęć pod kątem stanu technicznego (do remontu vs nowe).
- **Hybrid Score**: Finalna punktacja (0-100%) łącząca parametry finansowe (luka RCN) z opinią AI.

### D. Interaktywny Dashboard
- **Filtry Inwestycyjne**: Szukanie po cenie, metrażu, dzielnicy i minimalnym progu "score".
- **Mapa Ofert**: Wizualizacja okazji na mapie Warszawy (z geocodingiem dzielnic).
- **Karty Okazji**: Przejrzysty podgląd z podsumowaniem AI i porównaniem do cen rynkowych.

## 4. Kluczowe Naprawy i Optymalizacje
- **Docker Networking**: Dodano `extra_hosts` (host-gateway), aby kontenery stabilnie komunikowały się z Ollamą na Windowsie.
- **Baza Danych**: Rozszerzono schemat o kolumny analityczne (`rcn_benchmark`, `transaction_gap`, `cagr_5y`).
- **Stabilność API**: Zwiększono timeouty i zoptymalizowano wielkość paczek danych (batch size), co wyeliminowało błędy `ReadTimeout` przy pobieraniu dużych zbiorów RCN.

## 5. Instrukcja Obsługi

### Uruchomienie:
```powershell
docker-compose up -d
```

### Podstawowe Operacje:
1. **Dashboard**: Dostępny pod adresem `http://localhost:8501`.
2. **Aktualizacja RCN**: W menu bocznym dashboardu przycisk "Załaduj dane RCN" (zalecane raz na tydzień).
3. **Nowy Crawl**: Przycisk "Uruchom crawl" pobiera najświeższe ogłoszenia z rynku.

## 6. Dalszy Rozwój (Roadmap)
1. **Pełna Integracja Telegram**: Automatyczne powiadomienia o ofertach ze score > 30%.
2. **Geocoding w tle**: Dalsze uzupełnianie brakujących dzielnic dla historycznych rekordów RCN (Nominatim).
3. **Optymalizacja Vision**: Przejście na lżejszy model wizyjny (np. Qwen2-VL) dla słabszych jednostek RAM.

---
*Projekt zrealizowany i zwalidowany: 11.05.2026*
