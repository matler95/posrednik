from backend.model import (
    group_average_price_per_sqm,
    market_position,
    opportunity_score,
    price_gap_ratio,
    price_per_square_meter,
)
from backend.ml.predictor import predict_value

POSITIVE_KEYWORDS = [
    "okazja",
    "promocja",
    "bezpośrednio",
    "pilne",
    "do negocjacji",
    "ostatnia",
    "super cena",
]
NEGATIVE_KEYWORDS = [
    "do remontu",
    "pilny sprzedaz",
    "agent",
    "biuro",
    "pośrednik",
    "stan deweloperski",
    "ustaw",
    "ogrzanie",
]


def analyze_description(description):
    if not description or not isinstance(description, str):
        return {
            "text_bonus": 0.0,
            "text_penalty": 0.0,
            "keywords": [],
        }
    text = description.lower()
    keywords = []
    bonus = 0.0
    penalty = 0.0

    for phrase in POSITIVE_KEYWORDS:
        if phrase in text:
            keywords.append(phrase)
            bonus += 0.03

    for phrase in NEGATIVE_KEYWORDS:
        if phrase in text:
            keywords.append(phrase)
            penalty += 0.05

    bonus = min(bonus, 0.15)
    penalty = min(penalty, 0.3)
    return {"text_bonus": bonus, "text_penalty": penalty, "keywords": keywords}


def enrich_listings(listings):
    averages = group_average_price_per_sqm(listings)
    enriched = []
    for listing in listings:
        listing = listing.copy()
        listing["price_per_m2"] = listing.get("price_per_m2") or price_per_square_meter(listing)
        
        ml_est, is_ml = predict_value(listing, averages)
        listing["estimated_value"] = ml_est
        listing["is_ml_estimate"] = is_ml
        
        listing["price_gap_pct"] = price_gap_ratio(listing.get("price"), ml_est)
        listing["market_position"] = market_position(listing, averages)
        listing["direct_bonus"] = 0.05 if listing.get("direct_offer") else 0.0
        
        description_analysis = analyze_description(listing.get("description"))
        listing["text_bonus"] = description_analysis["text_bonus"]
        listing["text_penalty"] = description_analysis["text_penalty"]
        listing["text_score"] = max(0.0, min(1.0, 0.5 + description_analysis["text_bonus"] - description_analysis["text_penalty"]))
        
        listing["keywords"] = description_analysis["keywords"]
        
        listing["score"] = opportunity_score(listing, averages, ml_est)
        enriched.append(listing)
    return enriched


def find_opportunities(listings, threshold=0.15):
    opportunities = [
        {
            **listing,
            "score": round(listing.get("score", 0.0) * 100, 2),
        }
        for listing in listings
        if listing.get("score", 0.0) >= threshold
    ]
    return sorted(opportunities, key=lambda x: x["score"], reverse=True)
