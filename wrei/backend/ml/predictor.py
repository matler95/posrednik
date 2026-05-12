import logging
import joblib
from pathlib import Path

from backend.ml.features import extract_features

logger = logging.getLogger(__name__)

MODELS_DIR = Path("backend/models")
_LATEST_MODEL = None
_LATEST_META = None

def _load_model_if_needed():
    global _LATEST_MODEL, _LATEST_META
    
    model_path = MODELS_DIR / "wycena_latest.joblib"
    meta_path = MODELS_DIR / "wycena_latest_meta.joblib"
    
    if not model_path.exists() or not meta_path.exists():
        return False
        
    try:
        if _LATEST_MODEL is None:
            _LATEST_MODEL = joblib.load(model_path)
            _LATEST_META = joblib.load(meta_path)
        return True
    except Exception as e:
        logger.error(f"[ML] Nie udalo sie wczytac modelu: {e}")
        return False

# backend/ml/predictor.py — zastąp całość
def predict_value(listing, market_stats_averages=None):
    """
    Fallback hierarchy:
    1. ML model (joblib) jeśli istnieje i załadowany
    2. District median z market_stats_averages (grupowa z aktualnych ofert)
    3. Ogólna mediana Warszawa z averages
    """
    # Próba ML
    if _load_model_if_needed():
        try:
            feats = extract_features(listing)
            dist = listing.get("district") or "Warszawa"
            encoded = _LATEST_META.get(dist) or (
                sum(_LATEST_META.values()) / len(_LATEST_META) 
                if _LATEST_META else 10000.0
            )
            x_vec = [
                feats["area"], feats["rooms"], feats["floor_ratio"],
                feats["year_built"], feats["condition_encoded"],
                feats["building_type_encoded"], feats["has_balcony"],
                feats["has_parking"], feats["has_elevator"],
                feats["has_storage"], feats["ownership_encoded"], encoded
            ]
            val = _LATEST_MODEL.predict([x_vec])[0]
            return float(val), True
        except Exception as e:
            logger.debug("[ML] Predict error: %s", e)

    # Fallback: district average z bieżących ofert
    if market_stats_averages and listing.get("area"):
        district = listing.get("district") or "Warszawa"
        base_psm = (
            market_stats_averages.get(district) 
            or market_stats_averages.get("Warszawa")
        )
        if base_psm and base_psm > 0:
            estimated = round(base_psm * listing["area"])
            return estimated, False

    return None, False