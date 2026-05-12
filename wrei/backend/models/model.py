"""
model.py — Unified scoring engine. Single source of truth.

WAŻNE: To jest jedyny plik z logiką scoringu.
backend/models/model.py zostało usunięte — importuj wyłącznie z backend.model.

Composite score 0-1:
  Baza (zawsze obecna):
    price_gap    0.35  — ML/avg estimate vs cena oferty
    txn_gap      0.30  — mediana RCN transakcji vs cena/m²
    market_pos   0.15  — pozycja vs bieżące oferty w tej samej dzielnicy
    freshness    0.12  — bonus za ogłoszenie <1 dzień
    direct       0.08  — oferta bezpośrednia

  AI boost (addytywny, nie zastępuje bazy):
    text_score   max +8%   — analiza LLM opisu
    photo_score  max +5%   — analiza CV zdjęć

  Mnożnik stanu: 0.70–1.00
  CAGR bonus: addytywny max +0.10

Fallback gdy brak RCN:
  Zamiast zerować txn_gap, używamy market_stats (mediany ofertowe)
  jako proxy benchmarku. Score jest nadal użyteczny.
"""
from statistics import mean


# ---------------------------------------------------------------------------
# Podstawowe obliczenia cenowe
# ---------------------------------------------------------------------------

def price_per_square_meter(listing: dict) -> float | None:
    price = listing.get("price")
    area = listing.get("area")
    if not price or not area or area <= 0:
        return None
    return round(price / area, 2)


def group_average_price_per_sqm(listings: list[dict]) -> dict[str, float]:
    """
    Oblicza średnią cenę/m² per dzielnica z podanej listy ofert.
    Używane jako fallback benchmark gdy brak danych RCN.
    """
    by_location: dict[str, list[float]] = {}
    for listing in listings:
        psm = price_per_square_meter(listing)
        if not psm:
            continue
        location = (
            listing.get("district")
            or listing.get("raw_location", {}).get("address", {}).get("city", {}).get("name")
            or "Warszawa"
        )
        by_location.setdefault(location, []).append(psm)
    averaged = {k: round(mean(v), 2) for k, v in by_location.items() if v}
    if averaged and "Warszawa" not in averaged:
        averaged["Warszawa"] = round(mean(averaged.values()), 2)
    return averaged


def estimate_value(listing: dict, averages: dict) -> int | None:
    if not listing.get("area"):
        return None
    district = listing.get("district") or "Warszawa"
    base_price = (
        averages.get(district)
        or averages.get("Warszawa")
        or (mean(averages.values()) if averages else None)
    )
    if not base_price:
        return None
    return round(base_price * listing["area"])


def price_gap_ratio(price: int | None, estimated_value: int | None) -> float:
    """Jak bardzo oferta jest tańsza od estymowanej wartości. 0..1."""
    if not price or not estimated_value or estimated_value <= 0:
        return 0.0
    return round(max(0.0, (estimated_value - price) / estimated_value), 4)


def market_position(listing: dict, averages: dict) -> float | None:
    """
    Pozycja cenowa vs średnia rynkowa (bieżące oferty).
    >0 = taniej niż średnia, <0 = drożej.
    """
    psm = price_per_square_meter(listing)
    if not psm:
        return None
    district = listing.get("district") or "Warszawa"
    avg = averages.get(district) or averages.get("Warszawa")
    if not avg or avg <= 0:
        return None
    return round((avg - psm) / avg, 4)


# ---------------------------------------------------------------------------
# RCN / Transakcyjne
# ---------------------------------------------------------------------------

def transaction_gap_ratio(listing: dict, rcn_benchmark: float | None) -> float:
    """
    Jak bardzo oferta jest tańsza od mediany realnych transakcji.
    > 0 : oferta poniżej rynku transakcyjnego (okazja)
    < 0 : oferta powyżej rynku transakcyjnego (przepłacona)
    Clamp: -0.5..1.0
    """
    if not rcn_benchmark or rcn_benchmark <= 0:
        return 0.0
    psm = price_per_square_meter(listing)
    if not psm:
        return 0.0
    gap = (rcn_benchmark - psm) / rcn_benchmark
    return round(max(-0.5, min(gap, 1.0)), 4)


def value_growth_bonus(cagr: float | None) -> float:
    """
    Premia za wzrost rynku (CAGR z RCN).
    CAGR >= 10%/rok → +0.10
    CAGR >= 5%/rok  → +0.00 .. +0.10 liniowo
    CAGR >= 0%      → +0.00 .. +0.03 liniowo
    CAGR < 0%       → kara do -0.05
    """
    if cagr is None:
        return 0.0
    if cagr >= 0.10:
        return 0.10
    if cagr >= 0.05:
        return round((cagr - 0.05) / 0.05 * 0.10, 4)
    if cagr >= 0.0:
        return round(cagr / 0.05 * 0.03, 4)
    return round(max(cagr * 0.5, -0.05), 4)


# ---------------------------------------------------------------------------
# Fallback benchmark gdy brak RCN
# ---------------------------------------------------------------------------

def get_market_stats_benchmark(city_slug: str, district: str | None) -> float | None:
    """
    Pobiera medianę ceny/m² z tabeli market_stats jako fallback gdy brak RCN.
    market_stats jest agregacją bieżących ofert — nie tak dobre jak RCN,
    ale pozwala uniknąć zerowania składowej txn_gap.
    """
    try:
        from backend.db import get_conn
        conn = get_conn()
        cur = conn.cursor()
        # Próba 1: konkretna dzielnica
        if district:
            cur.execute("""
                SELECT median_price_per_m2 FROM market_stats
                WHERE district = %s AND rooms IS NULL AND condition IS NULL
                  AND median_price_per_m2 IS NOT NULL
                LIMIT 1
            """, (district,))
            row = cur.fetchone()
            if row and row[0]:
                cur.close(); conn.close()
                return float(row[0])
        # Próba 2: całe miasto (district = 'Warszawa' lub podobne)
        cur.execute("""
            SELECT AVG(median_price_per_m2) FROM market_stats
            WHERE median_price_per_m2 IS NOT NULL
              AND sample_count >= 5
        """)
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and row[0]:
            return float(row[0])
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Condition multiplier
# ---------------------------------------------------------------------------

def condition_multiplier(listing: dict) -> float:
    """
    Mnożnik stanu technicznego mieszkania.
    Obniża score dla wymagających remontu, premiuje nowe.
    """
    cond = str(listing.get("condition") or "").lower()
    # LLM może zwrócić polskie lub angielskie wartości
    if any(k in cond for k in ("now", "new", "nowy", "nowe")):
        return 1.00
    if any(k in cond for k in ("dobr", "good", "very_good")):
        return 0.95
    if any(k in cond for k in ("sred", "śred", "medium", "average")):
        return 0.85
    if any(k in cond for k in ("remon", "renovation", "to_renovate", "wymag")):
        return 0.70
    return 0.92  # nieznany stan — lekko ostrożnie


# ---------------------------------------------------------------------------
# Główna funkcja scoringu
# ---------------------------------------------------------------------------

def opportunity_score(
    listing: dict,
    averages: dict,
    ml_estimate: int | None,
    rcn_benchmark: float | None = None,
    cagr: float | None = None,
    city_slug: str = "warszawa",
) -> float:
    """
    Composite opportunity score 0-1.

    Jeśli brak rcn_benchmark (NULL z DB), próbuje użyć market_stats jako fallback,
    żeby nie zerować składowej txn_gap.

    Wagi bazowe (suma = 1.0):
      price_gap  0.35
      txn_gap    0.30
      market_pos 0.15
      freshness  0.12
      direct     0.08

    AI boost (addytywny):
      text_score  max +8%
      photo_score max +5%

    Mnożnik stanu: 0.70–1.00
    CAGR bonus: addytywny max +0.10
    """
    price = listing.get("price")

    # Fallback benchmark gdy brak RCN
    effective_benchmark = rcn_benchmark
    if not effective_benchmark:
        district = listing.get("district")
        effective_benchmark = get_market_stats_benchmark(city_slug, district)

    # 1. ML/avg price gap
    if not price or not ml_estimate or ml_estimate <= 0:
        price_gap = 0.0
    else:
        price_gap = max(0.0, (ml_estimate - price) / ml_estimate)

    # 2. RCN transaction gap (tylko pozytywna część dla wagi bazowej)
    txn_gap_raw = transaction_gap_ratio(listing, effective_benchmark)
    txn_gap_pos = max(0.0, txn_gap_raw)

    # 3. Pozycja rynkowa vs bieżące oferty
    market_pos = max(0.0, market_position(listing, averages) or 0.0)

    # 4. Świeżość ogłoszenia
    days = listing.get("days_on_market") or 0
    freshness = 1.0 if days < 1 else (0.5 if days < 3 else 0.0)

    # 5. Oferta bezpośrednia
    direct = 1.0 if listing.get("direct_offer") else 0.0

    # 6. AI text score (z LLM)
    raw_text = listing.get("text_score")
    has_text = raw_text is not None and float(raw_text) > 0
    text_score = float(raw_text or 0)

    # 7. Photo score (z CV pipeline)
    raw_photo = listing.get("photo_score")
    has_photo = raw_photo is not None and float(raw_photo) > 0
    photo_score = float(raw_photo or 0)

    # 8. CAGR bonus
    growth_bonus = value_growth_bonus(cagr)

    # 9. Condition multiplier
    mult = condition_multiplier(listing)

    # Wynik bazowy
    base = (
        price_gap    * 0.35
        + txn_gap_pos * 0.30
        + market_pos  * 0.15
        + freshness   * 0.12
        + direct      * 0.08
    ) * mult + growth_bonus

    # AI boost (addytywny)
    if has_text:
        base += text_score * 0.08
    if has_photo:
        base += photo_score * 0.05

    return round(min(max(base, 0.0), 1.0), 4)


def score_breakdown(
    listing: dict,
    averages: dict,
    ml_estimate: int | None,
    rcn_benchmark: float | None = None,
    cagr: float | None = None,
    city_slug: str = "warszawa",
) -> dict:
    """
    Zwraca szczegółowy breakdown scoringu — używane w UI do wyjaśnienia score.
    """
    price = listing.get("price")
    district = listing.get("district")

    effective_benchmark = rcn_benchmark
    used_fallback = False
    if not effective_benchmark:
        effective_benchmark = get_market_stats_benchmark(city_slug, district)
        if effective_benchmark:
            used_fallback = True

    price_gap = 0.0
    if price and ml_estimate and ml_estimate > 0:
        price_gap = max(0.0, (ml_estimate - price) / ml_estimate)

    txn_gap_raw = transaction_gap_ratio(listing, effective_benchmark)
    txn_gap_pos = max(0.0, txn_gap_raw)
    market_pos = max(0.0, market_position(listing, averages) or 0.0)
    days = listing.get("days_on_market") or 0
    freshness = 1.0 if days < 1 else (0.5 if days < 3 else 0.0)
    direct = 1.0 if listing.get("direct_offer") else 0.0
    mult = condition_multiplier(listing)
    growth_bonus = value_growth_bonus(cagr)
    text_score = float(listing.get("text_score") or 0)
    photo_score = float(listing.get("photo_score") or 0)

    total = opportunity_score(listing, averages, ml_estimate, rcn_benchmark, cagr, city_slug)

    psm = price_per_square_meter(listing)
    savings = None
    if effective_benchmark and psm and listing.get("area"):
        savings = round((effective_benchmark - psm) * listing["area"])

    return {
        "total_score": total,
        "total_pct": round(total * 100, 1),
        "components": {
            "price_gap": round(price_gap * 0.35 * mult, 4),
            "txn_gap":   round(txn_gap_pos * 0.30 * mult, 4),
            "market_pos": round(market_pos * 0.15 * mult, 4),
            "freshness":  round(freshness * 0.12 * mult, 4),
            "direct":     round(direct * 0.08 * mult, 4),
            "growth_bonus": round(growth_bonus, 4),
            "text_boost": round(text_score * 0.08, 4),
            "photo_boost": round(photo_score * 0.05, 4),
        },
        "inputs": {
            "price_gap_pct": round(price_gap * 100, 1),
            "txn_gap_pct": round(txn_gap_raw * 100, 1),
            "market_pos_pct": round(market_pos * 100, 1),
            "rcn_benchmark": effective_benchmark,
            "rcn_fallback": used_fallback,
            "price_per_m2": psm,
            "estimated_savings": savings,
            "condition_mult": mult,
            "days_on_market": days,
            "is_direct": bool(listing.get("direct_offer")),
            "has_llm_analysis": text_score > 0,
            "cagr_pct": round(cagr * 100, 1) if cagr else None,
        },
    }
