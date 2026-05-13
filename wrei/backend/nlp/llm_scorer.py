"""
LLM Scorer — analiza opisów ogłoszeń przez Ollama (qwen2.5).
Proper background queue z rate limiting i retry.
"""
import asyncio
import httpx
import json
import logging
import os

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/api/chat")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
LLM_INTERVAL_SECONDS = float(os.getenv("LLM_INTERVAL_SECONDS", "1.0"))
LLM_BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "10"))
LLM_TIMEOUT = 45.0

PROMPT_TEMPLATE = """\
Analyze the listing and return ONLY a JSON object (no text before/after).
OUTPUT MUST BE STRICTLY IN POLISH LANGUAGE.
Example: {{"condition": "dobry", "investment_score": 8, "summary": "Mieszkanie blisko metra, dobra cena..."}}

Data:
Title: {title} | District: {district}
Price: {price} PLN | Area: {area} m2 | Rooms: {rooms} | Price/m2: {price_per_m2}
Floor: {floor_info} | Year: {year_built} | Condition Hint: {condition_hint}
RCN Benchmark: {rcn_benchmark} | CAGR 5y: {cagr_pct}% | Gap: {transaction_gap_pct}% ({transaction_gap_sign})
<description>
{description}
</description>"""


def _build_prompt(listing: dict) -> str:
    rcn = listing.get("rcn_benchmark")
    cagr = listing.get("cagr_5y")
    txn_gap = listing.get("transaction_gap") or 0
    psm = listing.get("price_per_m2")
    floor = listing.get("floor")
    total_floors = listing.get("total_floors")

    floor_info = f"{floor}/{total_floors}" if floor is not None else "brak danych"
    rcn_str = f"{rcn:.0f}" if rcn else "brak danych"
    cagr_str = f"{cagr * 100:.1f}" if cagr is not None else "brak danych"
    txn_pct = f"{abs(txn_gap * 100):.1f}" if txn_gap else "0.0"
    txn_sign = "taniej niż transakcje ✅" if txn_gap > 0 else "drożej niż transakcje ⚠️"
    psm_str = f"{psm:.0f}" if psm else "brak"

    return PROMPT_TEMPLATE.format(
        title=(listing.get("title") or "")[:100],
        district=listing.get("district") or "brak",
        price=listing.get("price") or 0,
        area=listing.get("area") or 0,
        rooms=listing.get("rooms") or "brak",
        price_per_m2=psm_str,
        condition_hint=listing.get("condition") or "nieznany",
        floor_info=floor_info,
        year_built=listing.get("year_built") or "brak",
        rcn_benchmark=rcn_str,
        cagr_pct=cagr_str,
        transaction_gap_pct=txn_pct,
        transaction_gap_sign=txn_sign,
        description=(listing.get("description") or "brak opisu")[:1500],
    )


async def analyze_listing_with_llm(listing: dict) -> dict | None:
    """Analizuje jedno ogłoszenie przez LLM. Zwraca słownik lub None."""
    prompt = _build_prompt(listing)

    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            response = await client.post(OLLAMA_URL, json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.0,
                    "num_predict": 512,
                }
            })
    except httpx.ConnectError:
        logger.error("[LLM] Nie można połączyć z Ollama na %s", OLLAMA_URL)
        return None
    except httpx.TimeoutException:
        logger.warning("[LLM] Timeout dla listing %d", listing.get("id", -1))
        return None
    except Exception as e:
        logger.error("[LLM] Błąd HTTP: %s", e)
        return None

    if response.status_code != 200:
        logger.error("[LLM] Ollama status %d", response.status_code)
        return None

    try:
        content = response.json().get("message", {}).get("content", "{}")
    except Exception as e:
        logger.error("[LLM] Błąd parsowania odpowiedzi Ollama: %s", e)
        return None

    # Cleanup markdown fence jeśli model dodał
    content = content.strip()
    for fence in ("```json", "```"):
        if content.startswith(fence):
            content = content[len(fence):]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    # Wyciągnij tylko JSON object
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1:
        content = content[start:end + 1]

    try:
        result = json.loads(content)
        # Walidacja kluczowych pól
        if not isinstance(result, dict):
            return None
        # Normalizuj investment_score do 0-10
        for key in ("investment_score", "negotiation_potential", "location_quality"):
            val = result.get(key)
            if val is not None:
                try:
                    result[key] = max(1, min(10, int(float(val))))
                except (ValueError, TypeError):
                    result[key] = 5
        return result
    except json.JSONDecodeError:
        logger.warning("[LLM] Błąd parsowania JSON dla listing %d: %s",
                       listing.get("id", -1), content[:200])
        return None


LLM_MAX_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "3"))

async def run_llm_queue_once(batch_size: int = LLM_BATCH_SIZE) -> int:
    """
    Przetwarza jeden batch ofert z kolejki LLM.
    Wykorzystuje nową kolumnę llm_error_count dla lepszego zarządzania błędami.
    """
    from backend.db import get_listings_for_llm_analysis, save_llm_analysis, increment_llm_error_count

    listings = get_listings_for_llm_analysis(limit=batch_size)
    if not listings:
        return 0

    logger.info("[LLM Queue] Analizuję batch %d ofert (concurrency=%d)...", len(listings), LLM_MAX_CONCURRENCY)
    
    # Przetwarzaj w małych batchach równolegle
    semaphore = asyncio.Semaphore(LLM_MAX_CONCURRENCY)

    async def _analyze_and_save(listing):
        async with semaphore:
            try:
                analysis = await analyze_listing_with_llm(listing)
                if analysis and "error" not in analysis:
                    save_llm_analysis(listing["url"], analysis)
                    from backend.analysis import recalculate_listing_score_in_db
                    recalculate_listing_score_in_db(listing["id"])
                    logger.debug("[LLM Queue] ✓ listing %d: score=%s",
                                 listing.get("id"), analysis.get("investment_score"))
                    return True
                else:
                    increment_llm_error_count(listing["id"])
                    logger.warning("[LLM Queue] ✗ Błąd analizy dla listing %d", listing.get("id"))
                    return False
            except Exception as e:
                logger.error("[LLM Queue] Błąd dla listing %d: %s", listing.get("id", -1), e)
                increment_llm_error_count(listing.get("id"))
                return False

    tasks = [_analyze_and_save(l) for l in listings]
    results = await asyncio.gather(*tasks)
    processed = sum(1 for r in results if r)

    return processed


async def process_llm_queue():
    """
    Ciągła pętla kolejki LLM — uruchamiana jako background task przy starcie FastAPI.
    Przetwarza oferty w partiach, czeka gdy kolejka pusta.
    """
    logger.info("[LLM Queue] Start background worker (model=%s)", MODEL)

    while True:
        try:
            processed = await run_llm_queue_once()
            if processed == 0:
                # Kolejka pusta — czekaj dłużej
                await asyncio.sleep(30)
            else:
                # Krótka pauza między batchami
                await asyncio.sleep(5)
        except Exception as e:
            logger.error("[LLM Queue] Błąd krytyczny pętli: %s", e, exc_info=True)
            await asyncio.sleep(60)
