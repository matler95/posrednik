from backend.model import (
    group_average_price_per_sqm,
    market_position,
    opportunity_score,
    price_gap_ratio,
    price_per_square_meter,
)
from backend.ml.predictor import predict_value
from backend.nlp.extractor import extract_structured_features

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


def text_score_from_llm(llm_analysis: dict) -> float:
    if not llm_analysis or "error" in llm_analysis:
        return 0.0
    investment = llm_analysis.get("investment_score", 5) / 10
    negotiation = llm_analysis.get("negotiation_potential", 5) / 10
    red_flag_penalty = len(llm_analysis.get("red_flags", [])) * 0.05
    urgency_bonus = 0.1 if llm_analysis.get("urgency_signals") else 0.0
    return round(max(0.0, min((investment * 0.6 + negotiation * 0.4) + urgency_bonus - red_flag_penalty, 1.0)), 4)


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
        
        # Ekstrakcja cech ze spacy jesli brakuje
        if not listing.get("features"):
            listing["features"] = extract_structured_features(listing.get("description", ""))
            
        # Obliczenie text_score
        llm_analysis = listing.get("llm_analysis")
        if llm_analysis and "error" not in llm_analysis:
            listing["text_score"] = text_score_from_llm(llm_analysis)
            listing["keywords"] = llm_analysis.get("green_flags", []) + llm_analysis.get("red_flags", [])
        else:
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
