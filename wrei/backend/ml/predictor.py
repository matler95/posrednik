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

def predict_value(listing, market_stats_averages=None):
    """
    Przewiduje cenę dla ogłoszenia używając modelu ML.
    Zwraca (wartość, is_ml) gdzie is_ml=True jeśli użyto ML.
    Jeśli model niedostępny, odpala fallback na podstawie averages.
    """
    if _load_model_if_needed():
        try:
            feats = extract_features(listing)
            dist = listing.get("district") or "Warszawa"
            
            # Target encoding z wyuczonego modelu
            encoded = _LATEST_META.get(dist)
            if not encoded:
                # Jesli nie zna dzielnicy, bierzemy srednia wartosc z calego miasta (aproksymacja z wartosci znanych)
                vals = list(_LATEST_META.values())
                encoded = sum(vals) / len(vals) if vals else 10000.0
                
            x_vec = [
                feats["area"],
                feats["rooms"],
                feats["floor_ratio"],
                feats["year_built"],
                feats["condition_encoded"],
                feats["building_type_encoded"],
                feats["has_balcony"],
                feats["has_parking"],
                feats["has_elevator"],
                feats["has_storage"],
                feats["ownership_encoded"],
                encoded
            ]
            
            val = _LATEST_MODEL.predict([x_vec])[0]
            return float(val), True
        except Exception as e:
            logger.error(f"[ML] Blad podczas ewaluacji modelu dla oferty: {e}")
            
    # Fallback
    if market_stats_averages and listing.get("area"):
        district = listing.get("district") or "Warszawa"
        base_price = market_stats_averages.get(district) or market_stats_averages.get("Warszawa")
        if base_price:
            return round(base_price * listing["area"]), False
            
    return None, False
