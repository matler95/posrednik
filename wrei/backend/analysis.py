"""
analysis.py — enrichment pipeline: ML estimate, RCN scoring, text/photo score.
RCN cache jest współdzielony między ofertami w jednym wywołaniu enrich_listings.
"""
import logging

from backend.model import (
    group_average_price_per_sqm,
    market_position,
    opportunity_score,
    price_gap_ratio,
    price_per_square_meter,
    transaction_gap_ratio,
)
from backend.ml.predictor import predict_value
from backend.nlp.extractor import extract_structured_features

logger = logging.getLogger(__name__)

POSITIVE_KEYWORDS = [
    "okazja", "promocja", "bezpośrednio", "pilne",
    "do negocjacji", "ostatnia", "super cena",
]
NEGATIVE_KEYWORDS = [
    "do remontu", "pilny sprzedaz", "agent", "biuro",
    "pośrednik", "stan deweloperski",
]


def analyze_description(description: str) -> dict:
    if not description or not isinstance(description, str):
        return {"text_bonus": 0.0, "text_penalty": 0.0, "keywords": []}
    text = description.lower()
    keywords, bonus, penalty = [], 0.0, 0.0
    for phrase in POSITIVE_KEYWORDS:
        if phrase in text:
            keywords.append(phrase)
            bonus += 0.03
    for phrase in NEGATIVE_KEYWORDS:
        if phrase in text:
            keywords.append(phrase)
            penalty += 0.05
    return {
        "text_bonus": min(bonus, 0.15),
        "text_penalty": min(penalty, 0.3),
        "keywords": keywords,
    }


def text_score_from_llm(llm_analysis: dict) -> float:
    if not llm_analysis or "error" in llm_analysis:
        return 0.0
    investment = llm_analysis.get("investment_score", 5) / 10
    negotiation = llm_analysis.get("negotiation_potential", 5) / 10
    red_flag_penalty = len(llm_analysis.get("red_flags", [])) * 0.05
    urgency_bonus = 0.1 if llm_analysis.get("urgency_signals") else 0.0
    return round(max(0.0, min(
        (investment * 0.6 + negotiation * 0.4) + urgency_bonus - red_flag_penalty,
        1.0
    )), 4)


def photo_score_from_analysis(photo_analysis: dict) -> float:
    if not photo_analysis:
        return 0.0
    return float(photo_analysis.get("photo_score", 0.0))


def _get_rcn_data(
    city_slug: str,
    district: str | None,
    rooms: int | None,
    area: float | None = None,
    rcn_cache: dict | None = None,
) -> tuple[float | None, float | None]:
    """
    Pobiera RCN benchmark i CAGR z cache lub DB.
    rcn_cache jest słownikiem współdzielonym w obrębie jednego wywołania enrich_listings.
    """
    cache_key = (city_slug, district, rooms)
    if rcn_cache is not None and cache_key in rcn_cache:
        return rcn_cache[cache_key]
    try:
        from backend.market.trend_analyzer import get_rcn_benchmark, compute_cagr
        benchmark = get_rcn_benchmark(city_slug, district=district, rooms=rooms, area=area)
        cagr = compute_cagr(city_slug, district=district, years=5)
        result = (benchmark, cagr)
    except Exception as exc:
        logger.debug("[Analysis] RCN error for %s/%s: %s", city_slug, district, exc)
        result = (None, None)
    if rcn_cache is not None:
        rcn_cache[cache_key] = result
    return result


def enrich_listings(listings: list[dict], city_slug: str = "warszawa") -> list[dict]:
    """
    Wzbogaca oferty o:
    - price_per_m2, estimated_value, market_position
    - RCN benchmark, CAGR, transaction_gap
    - text_score (z LLM analizy lub keyword matching)
    - photo_score
    - opportunity_score

    RCN jest odpytywany raz per (city, district, rooms) dzięki cache.
    """
    averages = group_average_price_per_sqm(listings)
    rcn_cache: dict[tuple, tuple] = {}  # współdzielony cache dla całego batcha
    enriched = []

    for listing in listings:
        listing = listing.copy()

        # Price/m²
        listing["price_per_m2"] = listing.get("price_per_m2") or price_per_square_meter(listing)

        # ML estimate
        ml_est, is_ml = predict_value(listing, averages)
        listing["estimated_value"] = ml_est
        listing["is_ml_estimate"] = is_ml

        listing["price_gap_pct"] = price_gap_ratio(listing.get("price"), ml_est)
        listing["market_position"] = market_position(listing, averages)
        listing["direct_bonus"] = 0.05 if listing.get("direct_offer") else 0.0

        # NLP features
        if not listing.get("features"):
            listing["features"] = extract_structured_features(listing.get("description", ""))

        # Text score
        llm_analysis = listing.get("llm_analysis")
        if llm_analysis and isinstance(llm_analysis, dict) and "error" not in llm_analysis:
            listing["text_score"] = text_score_from_llm(llm_analysis)
            listing["keywords"] = (
                llm_analysis.get("green_flags", []) + llm_analysis.get("red_flags", [])
            )
        else:
            desc_analysis = analyze_description(listing.get("description"))
            ts = max(0.0, min(
                1.0,
                0.5 + desc_analysis["text_bonus"] - desc_analysis["text_penalty"]
            ))
            listing["text_score"] = ts
            listing["text_bonus"] = desc_analysis["text_bonus"]
            listing["text_penalty"] = desc_analysis["text_penalty"]
            listing["keywords"] = desc_analysis["keywords"]

        # Photo score
        listing["photo_score"] = photo_score_from_analysis(listing.get("photo_analysis"))

        # RCN (z cache)
        district = listing.get("district")
        try:
            rooms_int = int(listing.get("rooms") or 0) or None
        except (ValueError, TypeError):
            rooms_int = None
        try:
            area_float = float(listing.get("area") or 0) or None
        except (ValueError, TypeError):
            area_float = None

        rcn_benchmark, cagr = _get_rcn_data(
            city_slug, district, rooms_int, area_float, rcn_cache
        )
        listing["rcn_benchmark"] = rcn_benchmark
        listing["cagr_5y"] = cagr
        listing["transaction_gap"] = transaction_gap_ratio(listing, rcn_benchmark)

        # Composite score
        listing["score"] = opportunity_score(
            listing, averages, ml_est,
            rcn_benchmark=rcn_benchmark,
            cagr=cagr,
        )
        enriched.append(listing)

    return enriched


def find_opportunities(listings: list[dict], threshold: float = 0.15) -> list[dict]:
    return sorted(
        [
            {**l, "score": round(l.get("score", 0.0) * 100, 2)}
            for l in listings
            if l.get("score", 0.0) >= threshold
        ],
        key=lambda x: x["score"],
        reverse=True,
    )
