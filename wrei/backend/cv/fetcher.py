"""
CV Fetcher — asynchroniczne pobieranie zdjęć z URL do lokalnego cache.
Zdjęcia zapisywane jako: /app/photos/{listing_id}/{index}.jpg
"""
import asyncio
import hashlib
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

PHOTOS_DIR = Path("/app/photos")
MAX_PHOTOS_PER_LISTING = 6   # pierwsze 6 zdjęć wystarczy
DOWNLOAD_TIMEOUT = 15.0
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "image/webp,image/jpeg,image/*",
}


async def fetch_image(client: httpx.AsyncClient, url: str, dest: Path) -> bool:
    """Pobiera jedno zdjęcie. Zwraca True jeśli sukces."""
    if dest.exists() and dest.stat().st_size > 1000:
        return True  # już w cache
    try:
        resp = await client.get(url, timeout=DOWNLOAD_TIMEOUT, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return True
        logger.debug("[Fetcher] Pominięto %s (status=%d, size=%d)", url, resp.status_code, len(resp.content))
        return False
    except Exception as exc:
        logger.warning("[Fetcher] Błąd pobierania %s: %s", url, exc)
        return False


async def fetch_listing_photos(listing_id: int, image_urls: list[str]) -> list[Path]:
    """
    Pobiera do MAX_PHOTOS_PER_LISTING zdjęć dla ogłoszenia.
    Zwraca listę lokalnych ścieżek do pobranych plików.
    """
    listing_dir = PHOTOS_DIR / str(listing_id)
    listing_dir.mkdir(parents=True, exist_ok=True)

    urls = image_urls[:MAX_PHOTOS_PER_LISTING]
    paths = []

    async with httpx.AsyncClient(headers=HEADERS) as client:
        tasks = []
        for i, url in enumerate(urls):
            ext = _guess_ext(url)
            dest = listing_dir / f"{i:02d}{ext}"
            paths.append((dest, url))
            tasks.append(fetch_image(client, url, dest))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    downloaded = [p for (p, _), ok in zip(paths, results) if ok is True]
    logger.info("[Fetcher] listing %d: %d/%d zdjęć pobrano", listing_id, len(downloaded), len(urls))
    return downloaded


def _guess_ext(url: str) -> str:
    url_lower = url.lower().split("?")[0]
    for ext in [".jpg", ".jpeg", ".webp", ".png"]:
        if url_lower.endswith(ext):
            return ext
    return ".jpg"


def get_cached_photos(listing_id: int) -> list[Path]:
    """Zwraca istniejące pliki zdjęć z cache (bez pobierania)."""
    listing_dir = PHOTOS_DIR / str(listing_id)
    if not listing_dir.exists():
        return []
    return sorted(
        p for p in listing_dir.iterdir()
        if p.is_file() and p.suffix in {".jpg", ".jpeg", ".webp", ".png"}
        and p.stat().st_size > 1000
    )
