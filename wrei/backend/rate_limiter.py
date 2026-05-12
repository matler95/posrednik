import threading
import time
import logging

logger = logging.getLogger(__name__)

# Domyślne limity per portal (sekundy między requestami)
PORTAL_DELAYS = {
    "otodom":               1.5,
    "olx":                  1.0,
    "gratka":               2.5,   # było 2.0 — zwiększ bo mają anty-bot
    "morizon":              2.5,   # j.w.
    "domiporta":            2.0,
    "nieruchomosci_online": 1.5,   # było 1.0
    "default":              1.5,
}

class TokenBucket:
    """
    Token bucket rate limiter — thread-safe.
    rate = tokeny na sekundę (np. 0.5 = 1 request co 2s)
    burst = max tokenów naraz (pozwala na krótkie sprinty)
    """

    def __init__(self, rate: float, burst: int = 1):
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
        self._last_refill = now

    def acquire(self, block: bool = True) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            if not block:
                return False
            # Oblicz ile czekać na kolejny token
            wait = (1 - self._tokens) / self.rate
        # Czekamy poza lockiem
        time.sleep(wait)
        with self._lock:
            self._refill()
            self._tokens -= 1
            return True

    def wait(self):
        """Blokuje do momentu gdy token jest dostępny."""
        self.acquire(block=True)


class RateLimiterRegistry:
    """
    Globalny rejestr limiterów per portal.
    Singleton — jeden na cały proces.
    """

    def __init__(self):
        self._limiters: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def get(self, portal: str) -> TokenBucket:
        with self._lock:
            if portal not in self._limiters:
                delay = PORTAL_DELAYS.get(portal, PORTAL_DELAYS["default"])
                rate = 1.0 / delay  # np. delay=2s → rate=0.5 req/s
                self._limiters[portal] = TokenBucket(rate=rate, burst=2)
                logger.debug("[RateLimit] Nowy limiter dla %s: %.2f req/s", portal, rate)
            return self._limiters[portal]

    def wait(self, portal: str):
        """Wywołaj przed każdym requestem do portalu."""
        self.get(portal).wait()

    def update_delay(self, portal: str, delay: float):
        """Aktualizacja opóźnienia w runtime (np. po 429)."""
        with self._lock:
            rate = 1.0 / max(delay, 0.1)
            self._limiters[portal] = TokenBucket(rate=rate, burst=1)
            logger.info("[RateLimit] Zaktualizowano %s: delay=%.1fs", portal, delay)


# Globalny singleton
rate_limiter = RateLimiterRegistry()