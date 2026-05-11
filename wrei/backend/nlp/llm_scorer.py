import httpx
import json
import logging
import os

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/api/chat")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

PROMPT = """Jesteś doświadczonym pośrednikiem nieruchomości z 15-letnim doświadczeniem na polskim rynku.
Masz dostęp do realnych danych transakcyjnych z aktów notarialnych (RCN).
Przeanalizuj ogłoszenie i odpowiedz WYŁĄCZNIE poprawnym JSON, bez żadnego tekstu przed ani po:

{{
  "condition": "nowy|dobry|sredni|remont",
  "urgency_signals": ["lista sygnałów pilnej sprzedaży, np. 'pilne', 'szybka sprzedaż'"],
  "red_flags": ["lista ostrzeżeń, np. 'brak informacji o piętrze', 'wyłącznie pośrednik'"],
  "green_flags": ["lista atutów, np. 'oferta bezpośrednia', 'nowe okna', 'blisko metra'"],
  "renovation_cost_per_m2": null,
  "location_quality": 5,
  "investment_score": 5,
  "negotiation_potential": 5,
  "price_vs_market_comment": "ocena ceny vs dane RCN (1-2 zdania)",
  "summary": "2-3 zdania po polsku — ocena dla kupującego, uwzględniająca dane rynkowe"
}}

Dane ogłoszenia:
Tytuł: {title}
Dzielnica: {district}
Cena: {price} PLN | Metraż: {area}m² | Pokoje: {rooms}
Cena/m²: {price_per_m2} PLN/m²

Dane rynkowe (RCN — realne akty notarialne):
Mediana transakcyjna dla dzielnicy: {rcn_benchmark} PLN/m²
Trend cenowy CAGR 5 lat: {cagr_pct}% rocznie
Różnica oferty vs transakcje: {transaction_gap_pct}% ({transaction_gap_sign})

Opis ogłoszenia:
{description}"""

async def analyze_listing_with_llm(listing: dict) -> dict | None:
    try:
        # Przygotuj dane rynkowe do promptu
        rcn = listing.get("rcn_benchmark")
        cagr = listing.get("cagr_5y")
        txn_gap = listing.get("transaction_gap")
        psm = listing.get("price_per_m2")

        rcn_str = f"{rcn:.0f}" if rcn else "brak danych"
        cagr_str = f"{cagr * 100:.1f}" if cagr is not None else "brak danych"
        txn_gap_pct = f"{abs(txn_gap * 100):.1f}" if txn_gap is not None else "brak danych"
        txn_sign = "taniej od transakcji ✅" if (txn_gap or 0) > 0 else "drożej od transakcji ⚠️"
        psm_str = f"{psm:.0f}" if psm else "brak"

        safe_listing = {
            "title": listing.get("title", ""),
            "district": listing.get("district", "brak dzielnicy"),
            "price": listing.get("price", ""),
            "area": listing.get("area", ""),
            "rooms": listing.get("rooms", ""),
            "price_per_m2": psm_str,
            "rcn_benchmark": rcn_str,
            "cagr_pct": cagr_str,
            "transaction_gap_pct": txn_gap_pct,
            "transaction_gap_sign": txn_sign,
            "description": (listing.get("description") or "")[:3000],  # limit do 3000 znaków
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            try:
                response = await client.post(OLLAMA_URL, json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": PROMPT.format(**safe_listing)}],
                    "stream": False,
                    "format": "json"
                })
            except httpx.ConnectError:
                logger.error(f"[LLM] Nie mozna polaczyc sie z Ollama na {OLLAMA_URL}. Upewnij sie, ze Ollama dziala na hoscie.")
                return None
            except Exception as e:
                logger.error(f"[LLM] Blad httpx podczas polaczenia z Ollama: {str(e)}")
                return None

        if response.status_code == 200:
            content = response.json().get("message", {}).get("content", "{}")


            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx+1]
            elif start_idx == -1:
                content = "{" + content + "}"

            try:
                return json.loads(content)
            except json.JSONDecodeError:
                logger.error("[LLM] Błąd parsowania JSON. Raw: %s", content[:200])
                return None
        else:
            logger.error("[LLM] Ollama błąd %d: %s", response.status_code, response.text[:200])
            return None
    except Exception as e:
        logger.error("[LLM] Błąd komunikacji z Ollama: %s", e)
        return None


async def process_llm_queue():
    from backend.db import get_listings_for_llm_analysis, save_llm_analysis
    import asyncio
    
    while True:
        listings = get_listings_for_llm_analysis(limit=5)
        if not listings:
            # logger.info("[LLM] Kolejka pusta. Czekam 30s...")
            await asyncio.sleep(30)
            continue
            
        logger.info(f"[LLM] Analiza paczki {len(listings)} ofert (z {len(listings)} w kolejce).")
        for listing in listings:
            try:
                analysis = await analyze_listing_with_llm(listing)
                if analysis:
                    save_llm_analysis(listing["url"], analysis)
                    logger.info(f"[LLM] Przeanalizowano: {listing.get('title')[:40]}...")
                else:
                    # Oznacz jako błąd, żeby nie próbować w kółko tego samego
                    save_llm_analysis(listing["url"], {"error": "timeout_or_parse_fail"})
            except Exception as e:
                logger.error(f"[LLM] Blad krytyczny petli: {e}")
            
            await asyncio.sleep(1) # Chwila oddechu dla Ollama

