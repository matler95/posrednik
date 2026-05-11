"""
Vision Scorer — analizuje zdjęcia nieruchomości przez Ollama (moondream).
Pipeline: fetch photos → CLIP filter → moondream analysis → aggregate score.

Model: moondream (1.7GB RAM, działa na CPU)
Ollama API: multimodal endpoint z base64-encoded images.
"""
import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from statistics import mean

import httpx

from backend.cv.clip_filter import filter_photos
from backend.cv.fetcher import fetch_listing_photos, get_cached_photos

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/api/chat")
VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "moondream")

VISION_PROMPT = """Analyze this real estate property photo and respond ONLY with valid JSON:
{
  "scene_type": "living_room|bedroom|kitchen|bathroom|exterior|balcony|hallway|other",
  "condition": "new|good|average|renovation_needed",
  "condition_score": 7,
  "positive_features": ["list of visible positives, e.g. 'natural light', 'modern finishes'"],
  "negative_features": ["list of visible issues, e.g. 'peeling paint', 'old bathroom'"],
  "estimated_renovation_pct": 0
}
condition_score: 1-10 (10 = brand new, 1 = complete renovation needed)
estimated_renovation_pct: % of property value needed for renovation (0 if not needed)"""


async def _analyze_image_with_vision(image_path: Path, client: httpx.AsyncClient) -> dict | None:
    """Wysyła jedno zdjęcie do Ollama moondream i zwraca parsowany JSON."""
    try:
        img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        payload = {
            "model": VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": VISION_PROMPT,
                "images": [img_b64],
            }],
            "stream": False,
            "format": "json",
        }
        resp = await client.post(OLLAMA_URL, json=payload, timeout=60.0)
        if resp.status_code != 200:
            logger.warning("[Vision] Ollama błąd %d dla %s", resp.status_code, image_path.name)
            return None

        content = resp.json().get("message", {}).get("content", "{}")
        content = content.strip()
        start = content.find("{"); end = content.rfind("}")
        if start != -1 and end != -1:
            content = content[start:end+1]
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("[Vision] Błąd parsowania JSON dla %s", image_path.name)
        return None
    except Exception as exc:
        logger.warning("[Vision] Błąd analizy %s: %s", image_path.name, exc)
        return None


def _aggregate_photo_results(results: list[dict]) -> dict:
    """
    Agreguje wyniki analizy wielu zdjęć do jednego skrótu.
    Oblicza photo_score (0.0 - 1.0).
    """
    valid = [r for r in results if r and "condition_score" in r]
    if not valid:
        return {"photo_score": 0.0, "condition": "unknown", "photos_analyzed": 0}

    avg_score = mean(r.get("condition_score", 5) for r in valid)
    photo_score = round((avg_score - 1) / 9, 4)  # normalizacja 1-10 → 0-1

    # Zbierz wszystkie cechy
    positives = []
    negatives = []
    conditions = []
    for r in valid:
        positives.extend(r.get("positive_features", []))
        negatives.extend(r.get("negative_features", []))
        if r.get("condition"):
            conditions.append(r["condition"])

    # Dominujący stan
    dominant_condition = max(set(conditions), key=conditions.count) if conditions else "unknown"

    # Estymacja remontu
    reno_pct = mean(r.get("estimated_renovation_pct", 0) for r in valid)

    return {
        "photo_score": photo_score,
        "condition": dominant_condition,
        "avg_condition_score": round(avg_score, 2),
        "photos_analyzed": len(valid),
        "positive_features": list(dict.fromkeys(positives))[:8],  # deduplicate
        "negative_features": list(dict.fromkeys(negatives))[:6],
        "estimated_renovation_pct": round(reno_pct, 1),
        "raw_results": valid,
    }


async def analyze_listing_photos(listing_id: int, image_urls: list[str]) -> dict:
    """
    Pełny pipeline CV dla jednego ogłoszenia:
    1. Pobierz zdjęcia (lub użyj cache)
    2. Filtruj przez CLIP
    3. Analizuj przez moondream
    4. Agreguj wyniki

    Zwraca słownik z photo_score i szczegółami.
    """
    # 1. Pobierz lub użyj cache
    cached = get_cached_photos(listing_id)
    if not cached and image_urls:
        cached = await fetch_listing_photos(listing_id, image_urls)

    if not cached:
        logger.info("[Vision] listing %d: brak zdjęć", listing_id)
        return {"photo_score": 0.0, "condition": "unknown", "photos_analyzed": 0}

    # 2. CLIP filter (odrzuć rzuty, loga, mapy)
    filtered = filter_photos(cached)
    logger.info("[Vision] listing %d: %d zdjęć po CLIP filter (było %d)", listing_id, len(filtered), len(cached))

    # 3. Analiza Vision (max 4 zdjęcia per listing)
    to_analyze = filtered[:4]
    async with httpx.AsyncClient() as client:
        tasks = [_analyze_image_with_vision(p, client) for p in to_analyze]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_results = [r for r in results if isinstance(r, dict)]

    # 4. Agregacja
    analysis = _aggregate_photo_results(valid_results)
    logger.info("[Vision] listing %d: photo_score=%.3f condition=%s",
                listing_id, analysis["photo_score"], analysis["condition"])
    return analysis


async def process_photo_queue(batch_size: int = 3):
    """
    Scheduler entry-point: analizuje batch_size ofert z najwyższym score
    które jeszcze nie mają photo_analysis.
    """
    from backend.db import get_listings_for_photo_analysis, save_photo_analysis

    listings = get_listings_for_photo_analysis(limit=batch_size)
    if not listings:
        logger.info("[Vision] Brak ofert do analizy zdjęć.")
        return

    logger.info("[Vision] Analiza %d ofert...", len(listings))
    for listing in listings:
        listing_id = listing["id"]
        images = listing.get("images") or []
        # images to JSONB — lista URL-i lub słowników z kluczem 'url'
        urls = []
        for img in images:
            if isinstance(img, str):
                urls.append(img)
            elif isinstance(img, dict):
                urls.append(img.get("url") or img.get("src") or "")
        urls = [u for u in urls if u]

        try:
            analysis = await analyze_listing_photos(listing_id, urls)
            save_photo_analysis(listing_id, analysis)
        except Exception:
            logger.exception("[Vision] Błąd dla listing %d", listing_id)
