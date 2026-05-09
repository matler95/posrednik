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


def opportunity_score(listing, averages, ml_estimate):
    # Składowe
    price = listing.get("price")
    if not price or not ml_estimate or ml_estimate <= 0:
        price_gap = 0.0
    else:
        price_gap = max(0, (ml_estimate - price) / ml_estimate)  # 0-1
        
    market_pos = market_position(listing, averages) or 0.0
    if market_pos < 0: market_pos = 0.0
    
    freshness = 1.0 if listing.get("days_on_market", 0) < 1 else 0.0
    direct = 0.1 if listing.get("direct_offer") else 0.0
    text_score = listing.get("text_score") or 0.0
    photo_score = listing.get("photo_score") or 0.0

    condition_mult = {"nowy": 1.0, "dobry": 0.95, "sredni": 0.85, "remont": 0.70}
    
    # Normalize condition key
    cond = (listing.get("condition") or "").lower()
    if "now" in cond: cond_key = "nowy"
    elif "dobr" in cond: cond_key = "dobry"
    elif "sred" in cond or "śred" in cond: cond_key = "sredni"
    elif "remon" in cond: cond_key = "remont"
    else: cond_key = "unknown"
    
    mult = condition_mult.get(cond_key, 0.90)

    raw = (
        price_gap     * 0.40 +
        market_pos    * 0.20 +
        freshness     * 0.10 +
        direct        * 0.10 +
        text_score    * 0.10 +
        photo_score   * 0.10
    ) * mult

    return round(min(max(raw, 0.0), 1.0), 4)
