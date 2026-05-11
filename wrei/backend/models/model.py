"""
model.py — kalkulacje cenowe i composite opportunity score.
Dynamiczne wagi: brak AI nie karze oferty.
"""
from statistics import mean


def price_per_square_meter(listing: dict) -> float | None:
    price = listing.get("price")
    area = listing.get("area")
    if not price or not area or area <= 0:
        return None
    return round(price / area, 2)


def group_average_price_per_sqm(listings: list[dict]) -> dict[str, float]:
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
    if not price or not estimated_value or estimated_value <= 0:
        return 0.0
    return max(0.0, (estimated_value - price) / estimated_value)


def market_position(listing: dict, averages: dict) -> float | None:
    psm = price_per_square_meter(listing)
    if not psm:
        return None
    district = listing.get("district") or "Warszawa"
    avg = averages.get(district) or averages.get("Warszawa")
    if not avg or avg <= 0:
        return None
    return round((avg - psm) / avg, 4)


def transaction_gap_ratio(listing: dict, rcn_benchmark: float | None) -> float:
    """
    > 0 : oferta tańsza od mediany transakcyjnej (okazja)
    < 0 : oferta droższa niż realne transakcje
    """
    if not rcn_benchmark or rcn_benchmark <= 0:
        return 0.0
    psm = price_per_square_meter(listing)
    if not psm:
        return 0.0
    gap = (rcn_benchmark - psm) / rcn_benchmark
    return round(max(-0.5, min(gap, 1.0)), 4)


def value_growth_bonus(cagr: float | None) -> float:
    """Premia za wzrost rynku (CAGR z RCN). Max +0.10, min -0.05."""
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
    listing: dict,
    averages: dict,
    ml_estimate: int | None,
    rcn_benchmark: float | None = None,
    cagr: float | None = None,
) -> float:
    """
    Composite score 0-1.

    Wagi bazowe (sumują się do 1.0, zawsze obecne):
      price_gap    0.35  — ML/average estimate vs cena
      txn_gap      0.30  — mediana RCN vs cena/m²
      market_pos   0.15  — pozycja vs bieżące oferty
      freshness    0.12  — bonus nowe ogłoszenie (<1 dzień)
      direct       0.08  — oferta bezpośrednia

    AI boost (addytywny, nie zastępuje):
      text_score   +max 8%
      photo_score  +max 5%

    Mnożnik stanu technicznego: 0.70–1.00
    CAGR bonus: addytywny max +0.10
    """
    price = listing.get("price")

    # 1. ML/average gap
    if not price or not ml_estimate or ml_estimate <= 0:
        price_gap = 0.0
    else:
        price_gap = max(0.0, (ml_estimate - price) / ml_estimate)

    # 2. RCN gap (transakcje notarialne)
    txn_gap = transaction_gap_ratio(listing, rcn_benchmark)
    txn_gap_pos = max(0.0, txn_gap)

    # 3. Pozycja rynkowa
    market_pos = max(0.0, market_position(listing, averages) or 0.0)

    # 4. Świeżość
    freshness = 1.0 if (listing.get("days_on_market") or 0) < 1 else 0.0

    # 5. Bezpośrednia
    direct = 1.0 if listing.get("direct_offer") else 0.0

    # 6. AI komponenty (opcjonalne)
    raw_text = listing.get("text_score")
    raw_photo = listing.get("photo_score")
    has_text = raw_text is not None and float(raw_text) > 0
    has_photo = raw_photo is not None and float(raw_photo) > 0
    text_score = float(raw_text or 0)
    photo_score = float(raw_photo or 0)

    # 7. Wzrost wartości rynku
    growth_bonus = value_growth_bonus(cagr)

    # 8. Mnożnik stanu technicznego
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

    # Wynik bazowy
    base = (
        price_gap    * 0.35
        + txn_gap_pos * 0.30
        + market_pos  * 0.15
        + freshness   * 0.12
        + direct      * 0.08
    ) * mult + growth_bonus

    # AI boost
    if has_text:
        base += text_score * 0.08
    if has_photo:
        base += photo_score * 0.05

    return round(min(max(base, 0.0), 1.0), 4)
