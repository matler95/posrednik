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


def opportunity_score(price_gap, direct_bonus=0.0, text_bonus=0.0, text_penalty=0.0):
    score = price_gap + direct_bonus + text_bonus - text_penalty
    return round(max(0.0, min(score, 1.0)), 4)
