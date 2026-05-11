from statistics import mean


def price_per_square_meter(listing):
    price = listing.get("price")
    area = listing.get("area")
    if not price or not area:
        return None
    return price / area


def group_average_price_per_sqm(listings):
    by_location = {}
    for listing in listings:
        psm = price_per_square_meter(listing)
        if not psm:
            continue
        location = listing.get("district") or listing.get("raw_location", {}).get("address", {}).get("city", {}).get("name") or "Warszawa"
        by_location.setdefault(location, []).append(psm)

    averaged = {key: round(mean(values), 2) for key, values in by_location.items() if values}
    if averaged and "Warszawa" not in averaged:
        averaged["Warszawa"] = round(mean(averaged.values()), 2)
    return averaged


def estimate_value(listing, averages):
    if not listing.get("area"):
        return None
    district = listing.get("district") or "Warszawa"
    base_price = averages.get(district) or averages.get("Warszawa") or (mean(averages.values()) if averages else None)
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
    Mierzy jak bardzo oferta jest tańsza od mediany realnych transakcji (RCN).
    Wartość > 0 oznacza, że oferta jest poniżej rynku transakcyjnego — okazja.
    Wartość < 0 oznacza, że oferta jest droższa niż realne transakcje.
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
    Premia za potencjał wzrostu wartości nieruchomości (CAGR z danych RCN).
    CAGR > 5%/rok → bonus do 0.10
    CAGR < 0% (spadek) → kara do -0.05
    """
    if cagr is None:
        return 0.0
    if cagr >= 0.10:
        return 0.10
    if cagr >= 0.05:
        return round((cagr - 0.05) / 0.05 * 0.10, 4)
    if cagr >= 0.0:
        return round(cagr / 0.05 * 0.03, 4)
    return round(max(cagr * 0.5, -0.05), 4)  # kara za rynek spadający


def opportunity_score(
    listing,
    averages,
    ml_estimate,
    rcn_benchmark: float | None = None,
    cagr: float | None = None,
) -> float:
    """
    Composite score oceniający atrakcyjność inwestycyjną oferty.

    Składowe (suma = 1.0 przy braku CAGR):
      0.30 — price_gap      : ML estimate vs cena oferty
      0.20 — transaction_gap: mediana RCN vs cena/m² oferty (realne transakcje)
      0.10 — market_pos     : średnia z bieżących ofert vs oferta
      0.08 — freshness      : bonus za świeże ogłoszenie (< 1 dzień)
      0.07 — direct         : bonus za ofertę bezpośrednią
      0.15 — text_score     : wynik analizy Ollama tekstu ogłoszenia
      0.10 — photo_score    : wynik analizy zdjęć (CLIP + llava)
    + value_growth_bonus (CAGR)  — addytywny, max +0.10

    Wynik mnożony przez condition_multiplier i clampowany do [0, 1].
    """
    price = listing.get("price")

    # 1. ML gap (ML estimate vs cena)
    if not price or not ml_estimate or ml_estimate <= 0:
        price_gap = 0.0
    else:
        price_gap = max(0.0, (ml_estimate - price) / ml_estimate)

    # 2. RCN gap (transakcje notarialne vs cena/m²)
    txn_gap = transaction_gap_ratio(listing, rcn_benchmark)
    txn_gap_clamped = max(0.0, txn_gap)  # tylko pozytywne sygnały tutaj

    # 3. Pozycja rynkowa (vs bieżące oferty)
    market_pos = market_position(listing, averages) or 0.0
    if market_pos < 0:
        market_pos = 0.0

    # 4. Świeżość
    freshness = 1.0 if listing.get("days_on_market", 0) < 1 else 0.0

    # 5. Oferta bezpośrednia
    direct = 0.07 if listing.get("direct_offer") else 0.0

    # 6. Wynik analizy tekstu (Ollama)
    text_score = listing.get("text_score") or 0.0

    # 7. Wynik analizy zdjęć (CLIP + llava)
    photo_score = listing.get("photo_score") or 0.0

    # 8. Bonus za wzrost wartości (CAGR z RCN)
    growth_bonus = value_growth_bonus(cagr)

    # Mnożnik stanu technicznego
    condition_mult = {"nowy": 1.0, "dobry": 0.95, "sredni": 0.85, "remont": 0.70}
    cond = (listing.get("condition") or "").lower()
    if "now" in cond:
        cond_key = "nowy"
    elif "dobr" in cond:
        cond_key = "dobry"
    elif "sred" in cond or "śred" in cond:
        cond_key = "sredni"
    elif "remon" in cond:
        cond_key = "remont"
    else:
        cond_key = "unknown"
    mult = condition_mult.get(cond_key, 0.90)

    raw = (
        price_gap       * 0.30
        + txn_gap_clamped * 0.20
        + market_pos    * 0.10
        + freshness     * 0.08
        + direct
        + text_score    * 0.15
        + photo_score   * 0.10
        + growth_bonus
    ) * mult

    return round(min(max(raw, 0.0), 1.0), 4)
