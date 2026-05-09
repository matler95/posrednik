import httpx
import json
import logging
import os

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/api/chat")
MODEL = "qwen2.5:7b"

PROMPT = """Jesteś doświadczonym pośrednikiem nieruchomości w Warszawie z 15-letnim doświadczeniem.
Przeanalizuj ogłoszenie i odpowiedz WYŁĄCZNIE poprawnym JSON, bez żadnego tekstu przed ani po:

{{
  "condition": "nowy|dobry|sredni|remont",
  "urgency_signals": ["lista sygnałów pilnej sprzedaży"],
  "red_flags": ["lista ostrzeżeń"],
  "green_flags": ["lista atutów"],
  "renovation_cost_per_m2": null,
  "location_quality": 5,
  "investment_score": 5,
  "negotiation_potential": 5,
  "summary": "2-3 zdania po polsku — ocena dla kupującego"
}}

Dane ogłoszenia:
Tytuł: {title}
Dzielnica: {district}
Cena: {price} PLN | Metraż: {area}m² | Pokoje: {rooms}
Opis: {description}"""

async def analyze_listing_with_llm(listing: dict) -> dict | None:
    try:
        safe_listing = {
            "title": listing.get("title", ""),
            "district": listing.get("district", ""),
            "price": listing.get("price", ""),
            "area": listing.get("area", ""),
            "rooms": listing.get("rooms", ""),
            "description": listing.get("description", "")
        }
        
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(OLLAMA_URL, json={
                "model": MODEL,
                "messages": [{"role": "user", "content": PROMPT.format(**safe_listing)}],
                "stream": False,
                "format": "json"
            })
            
        if response.status_code == 200:
            content = response.json().get("message", {}).get("content", "{}")
            
            # Clean up markdown if present
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Additional safety: find first { and last }
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx+1]
            elif start_idx == -1 and end_idx == -1:
                # Moze byc tak ze wyplulo samo wnetrze slownika bez nawiasow klamrowych
                content = "{" + content + "}"
                
            try:
                return json.loads(content)
            except json.JSONDecodeError as je:
                logger.error(f"[LLM] Blad parsowania JSON z Ollama. Raw content: {content}")
                return None
        else:
            logger.error(f"[LLM] Ollama zwrocila blad {response.status_code}: {response.text}")
            return None
    except Exception as e:
        logger.error(f"[LLM] Blad komunikacji z Ollama: {e}")
        return None

async def process_llm_queue():
    from backend.db import get_listings_for_llm_analysis, save_llm_analysis
    import asyncio
    
    listings = get_listings_for_llm_analysis(limit=5)
    if not listings:
        logger.info("[LLM] Brak nowych ofert do analizy.")
        return
        
    logger.info(f"Rozpoczynam analizę LLM dla {len(listings)} ofert.")
    for listing in listings:
        analysis = await analyze_listing_with_llm(listing)
        if analysis:
            save_llm_analysis(listing["url"], analysis)
            logger.info(f"[LLM] Przeanalizowano pomyslnie: {listing.get('title')}")
        else:
            save_llm_analysis(listing["url"], {"error": "failed"})
            
        await asyncio.sleep(2)
