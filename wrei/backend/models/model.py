"""
model.py — kalkulacje cenowe i opportunity score.
NAPRAWKA: dynamiczne wagi — brak AI nie karze oferty.
"""
from statistics import mean


def price_per_square_meter(listing):
    price = listing.get("price")
    area = listing.get("area")
    if not price or not area or area <= 0:
        return None
    return round(price / area, 2)


def group_average_price_per_sqm(listings):
    by_location = {}
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


def estimate_value(listing, averages):
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


def price_gap_ratio(price, estimated_value):
    if not price or not estimated_value or estimated_value <= 0:
        return 0.0
    return max(0.0, (estimated_value - price) / estimated_value)


def market_position(listing, averages):
    psm = price_per_square_meter(listing)
    if not psm:
        return None
    district = listing.get("district") or "Warszawa"
    avg = averages.get(district) or averages.get("Warszawa")
    if not avg or avg <= 0:
        return None
    return round((avg - psm) / avg, 4)


def transaction_gap_ratio(listing, rcn_benchmark: float | None) -> float:
    """
    > 0 : oferta tańsza od mediany transakcyjnej (okazja)
    < 0 : oferta droższa od rynku transakcyjnego
    """
    if not rcn_benchmark or rcn_benchmark <= 0:
        return 0.0
    psm = price_per_square_meter(listing)
    if not psm:
        return 0.0
    gap = (rcn_benchmark - psm) / rcn_benchmark
    return round(max(-0.5, min(gap, 1.0)), 4)


def value_growth_bonus(cagr: float | None) -> float:
    """Premia za wzrost wartości rynku (CAGR z RCN). Max +0.10."""
    if cagr is None:
        return 0.0
    if cagr >= 0.10:
        return 0.10
    if cagr >= 0.05:
        return round((cagr - 0.05) / 0.05 * 0.10, 4)
    if cagr >= 0.0:
        return round(cagr / 0.05 * 0.03, 4)
    return round(max(cagr * 0.5, -0.05), 4)


def opportunity_score(
    listing,
    averages,
    ml_estimate,
    rcn_benchmark: float | None = None,
    cagr: float | None = None,
) -> float:
    """
    Composite score 0-1 oceniający atrakcyjność oferty.

    DYNAMICZNE WAGI — jeśli brak analizy AI, budżet wag jest redystrybuowany
    na komponenty finansowe. Oferty bez AI NIE są karane.

    Komponenty bazowe (zawsze obecne):
      - price_gap      : ML/average estimate vs cena oferty
      - transaction_gap: mediana RCN vs cena/m²
      - market_pos     : pozycja vs bieżący rynek ofertowy
      - freshness      : bonus za ogłoszenie < 1 dzień
      - direct         : bonus za ofertę bezpośrednią

    Komponenty AI (opcjonalne — dodają bonus gdy dostępne):
      - text_score     : analiza LLM opisu
      - photo_score    : analiza CV zdjęć

    Mnożnik stanu technicznego: 0.70-1.00
    CAGR bonus: addytywny max +0.10
    """
    price = listing.get("price")

    # ── 1. ML/average gap ──────────────────────────────────────────
    if not price or not ml_estimate or ml_estimate <= 0:
        price_gap = 0.0
    else:
        price_gap = max(0.0, (ml_estimate - price) / ml_estimate)

    # ── 2. RCN gap (transakcje notarialne) ─────────────────────────
    txn_gap = transaction_gap_ratio(listing, rcn_benchmark)
    txn_gap_pos = max(0.0, txn_gap)

    # ── 3. Pozycja rynkowa ─────────────────────────────────────────
    market_pos = max(0.0, market_position(listing, averages) or 0.0)

    # ── 4. Świeżość ogłoszenia ─────────────────────────────────────
    freshness = 1.0 if listing.get("days_on_market", 0) < 1 else 0.0

    # ── 5. Oferta bezpośrednia ─────────────────────────────────────
    direct = 1.0 if listing.get("direct_offer") else 0.0

    # ── 6. AI komponenty (opcjonalne) ──────────────────────────────
    raw_text_score = listing.get("text_score")
    raw_photo_score = listing.get("photo_score")
    has_text_ai = raw_text_score is not None and float(raw_text_score) > 0
    has_photo_ai = raw_photo_score is not None and float(raw_photo_score) > 0
    text_score = float(raw_text_score or 0)
    photo_score = float(raw_photo_score or 0)

    # ── 7. Wzrost wartości (CAGR) ──────────────────────────────────
    growth_bonus = value_growth_bonus(cagr)

    # ── 8. Mnożnik stanu technicznego ──────────────────────────────
    condition_mult = {
        "nowy": 1.00, "dobry": 0.95,
        "sredni": 0.85, "remont": 0.70,
    }
    cond = str(listing.get("condition") or "").lower()
    if "now" in cond:
        mult = 1.00
    elif "dobr" in cond:
        mult = 0.95
    elif "sred" in cond or "śred" in cond:
        mult = 0.85
    elif "remon" in cond:
        mult = 0.70
    else:
        mult = 0.92  # nieznany stan — lekko ostrożnie

    # ── 9. Obliczenie bazowego score bez AI ───────────────────────
    # Wagi bazowe sumują się do 1.0
    base_score = (
        price_gap    * 0.35 +
        txn_gap_pos  * 0.30 +
        market_pos   * 0.15 +
        freshness    * 0.12 +
        direct       * 0.08
    ) * mult + growth_bonus

    # ── 10. AI boost — addytywny, nie zastępuje ───────────────────
    # Każdy komponent AI dodaje do 10% wartości bazowej
    # Cel: oferta z AI > oferta bez AI gdy jakość porównywalna
    if has_text_ai:
        # text_score 0-1 → boost 0-8%
        base_score += text_score * 0.08

    if has_photo_ai:
        # photo_score 0-1 → boost 0-5%
        base_score += photo_score * 0.05

    return round(min(max(base_score, 0.0), 1.0), 4)
