import asyncio
import logging
import random
import time
from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
    RetryError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User-Agent rotation
# ---------------------------------------------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def random_headers(extra: dict | None = None) -> dict:
    headers = {**BASE_HEADERS, "User-Agent": random.choice(USER_AGENTS)}
    if extra:
        headers.update(extra)
    return headers


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

RETRYABLE_STATUS = {403, 429, 500, 502, 503, 504}
RETRYABLE_EXCEPTIONS = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)


class RetryableHTTPError(Exception):
    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        self.url = url
        super().__init__(f"HTTP {status_code} dla {url}")


def _make_retry_decorator(attempts: int = 3, min_wait: float = 2.0, max_wait: float = 30.0):
    return retry(
        retry=retry_if_exception_type((RetryableHTTPError,) + RETRYABLE_EXCEPTIONS),
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=min_wait, max=max_wait, jitter=1.5),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


# ---------------------------------------------------------------------------
# Synchroniczny klient (używany przez istniejące scrapery)
# ---------------------------------------------------------------------------

def fetch_html(
    url: str,
    extra_headers: dict | None = None,
    timeout: float = 20.0,
    attempts: int = 3,
    proxies: list[str] | None = None,
) -> str:
    """
    Pobiera HTML synchronicznie z retry, rotacją UA i opcjonalnym proxy.
    Drop-in replacement dla starego fetch_html z scraper_utils.
    """
    proxy = random.choice(proxies) if proxies else None
    headers = random_headers(extra_headers)

    @_make_retry_decorator(attempts=attempts)
    def _do_fetch():
        transport = httpx.HTTPTransport(retries=0)  # retry zarządzamy przez tenacity
        proxy_url = proxy or None

        # httpx >= 0.28 nie obsługuje proxies= — używamy mounts=
        client_kwargs = dict(
            transport=transport,
            timeout=timeout,
            follow_redirects=True,
        )
        if proxy_url:
            client_kwargs["mounts"] = {"all://": httpx.HTTPTransport(proxy=proxy_url)}

        with httpx.Client(**client_kwargs) as client:
            # Refresh headers per attempt (for UA rotation)
            current_headers = random_headers(extra_headers)
            response = client.get(url, headers=current_headers)

            if response.status_code in RETRYABLE_STATUS:
                logger.warning("[HTTP] %s → status %s, retry...", url, response.status_code)
                raise RetryableHTTPError(response.status_code, url)
            if response.status_code == 404:
                logger.warning("[HTTP] 404 Not Found: %s", url)
                return ""
            response.raise_for_status()
            return response.text

    try:
        return _do_fetch()
    except RetryError:
        logger.error("[HTTP] Wyczerpano próby dla: %s", url)
        return ""
    except Exception as e:
        logger.error("[HTTP] Nieoczekiwany błąd dla %s: %s", url, e)
        return ""


# ---------------------------------------------------------------------------
# Asynchroniczny klient (pod przyszłe async scrapery i Fazę 3/4)
# ---------------------------------------------------------------------------

async def fetch_html_async(
    url: str,
    client: httpx.AsyncClient,
    extra_headers: dict | None = None,
    attempts: int = 3,
) -> str:
    """
    Asynchroniczna wersja — używać z istniejącym httpx.AsyncClient dla connection pooling.
    """
    for attempt in range(1, attempts + 1):
        headers = random_headers(extra_headers)
        try:
            response = await client.get(url, headers=headers)
            if response.status_code in RETRYABLE_STATUS:
                wait = (attempt * 5) + random.uniform(0, 5)
                logger.warning("[HTTP async] %s → %s, retry %d/%d za %.1fs", url, response.status_code, attempt, attempts, wait)
                await asyncio.sleep(wait)
                continue
            if response.status_code == 404:
                logger.warning("[HTTP async] %s → 404", url)
                return ""
            response.raise_for_status()
            return response.text
        except RETRYABLE_EXCEPTIONS as e:
            wait = (2 ** attempt) + random.uniform(0, 1.5)
            logger.warning("[HTTP async] %s → %s, retry %d/%d za %.1fs", url, e, attempt, attempts, wait)
            await asyncio.sleep(wait)
        except Exception as e:
            logger.error("[HTTP async] Nieoczekiwany błąd %s: %s", url, e)
            return ""

    logger.error("[HTTP async] Wyczerpano próby dla: %s", url)
    return ""


async def fetch_json_async(
    url: str,
    client: httpx.AsyncClient,
    params: dict | None = None,
    extra_headers: dict | None = None,
    attempts: int = 3,
) -> dict | list | None:
    """
    Async fetch z parsowaniem JSON — dla API (nieruchomosci_online).
    """
    headers = random_headers({"Accept": "application/json", **(extra_headers or {})})

    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code in RETRYABLE_STATUS:
                wait = (2 ** attempt) + random.uniform(0, 1.5)
                await asyncio.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except RETRYABLE_EXCEPTIONS as e:
            wait = (2 ** attempt) + random.uniform(0, 1.5)
            logger.warning("[HTTP async JSON] %s → retry %d/%d: %s", url, attempt, attempts, e)
            await asyncio.sleep(wait)
        except Exception as e:
            logger.error("[HTTP async JSON] Błąd %s: %s", url, e)
            return None

    return None