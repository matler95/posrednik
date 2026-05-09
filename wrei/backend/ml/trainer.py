import logging
import os
import joblib
from datetime import datetime
from pathlib import Path

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

from backend.db import get_conn
from backend.ml.features import extract_features

logger = logging.getLogger(__name__)

MODELS_DIR = Path("backend/models")

def get_training_data():
    conn = get_conn()
    cur = conn.cursor()
    # Pobieramy z historii dla szerszego kontekstu
    cur.execute("""
        SELECT 
            price, area, rooms, floor, building_type, condition,
            district, year_built,
            score
        FROM listing_history
        WHERE price > 0 AND area > 0
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    
    # Jesli nie ma wystarczajaco w historii, bierzemy z main table
    if len(rows) < 100:
        cur.execute("""
            SELECT 
                price, area, rooms, floor, building_type, condition,
                district, year_built, total_floors, features, ownership,
                score
            FROM listings
            WHERE price > 0 AND area > 0
        """)
        cols = [d[0] for d in cur.description]
        main_rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        rows.extend(main_rows)
        
    cur.close()
    conn.close()
    return rows

def train_model():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    data = get_training_data()
    if len(data) < 50:
        logger.warning(f"[ML] Zbyt malo danych do treningu ({len(data)} próbek). Minimum to 50.")
        return False
        
    # Wyliczanie median dla target encodingu dzielnicy
    district_prices = {}
    for row in data:
        dist = row.get("district") or "Warszawa"
        psm = row["price"] / row["area"]
        district_prices.setdefault(dist, []).append(psm)
        
    district_medians = {
        dist: sorted(prices)[len(prices)//2] 
        for dist, prices in district_prices.items()
    }
    
    # Feature extraction
    X = []
    y = []
    
    for row in data:
        feats = extract_features(row)
        dist = row.get("district") or "Warszawa"
        
        # Target encoding
        feats["district_encoded"] = district_medians.get(dist, 10000.0)
        
        # Tworzenie wektora
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
            feats["district_encoded"]
        ]
        
        X.append(x_vec)
        y.append(row["price"])
        
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=42)
    
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model", GradientBoostingRegressor(n_estimators=200, max_depth=4, random_state=42))
    ])
    
    logger.info("[ML] Rozpoczynam trenowanie modelu GradientBoostingRegressor...")
    pipeline.fit(X_train, y_train)
    
    y_pred = pipeline.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    mean_price = sum(y_test) / len(y_test)
    error_pct = (mae / mean_price) * 100
    
    logger.info(f"[ML] Trening zakonczony. MAE: {mae:.2f} PLN ({error_pct:.2f}% wartosci)")
    
    if error_pct > 25.0:
        logger.warning("[ML] Model ma slaba dokladnosc, ale i tak zapisujemy (bo poczatkowa baza moze byc mala).")
        
    # Zapis
    date_str = datetime.now().strftime("%Y%m%d")
    model_path = MODELS_DIR / f"wycena_{date_str}.joblib"
    meta_path = MODELS_DIR / f"wycena_{date_str}_meta.joblib"
    
    joblib.dump(pipeline, model_path)
    joblib.dump(district_medians, meta_path)
    
    # Symlink
    latest_model = MODELS_DIR / "wycena_latest.joblib"
    latest_meta = MODELS_DIR / "wycena_latest_meta.joblib"
    
    if latest_model.exists(): latest_model.unlink()
    if latest_meta.exists(): latest_meta.unlink()
    
    # Używamy os.link w Windows / symlink lub zwykłe skopiowanie
    # Aby było bezpieczniej w dockerze i na windowsie: robimy kopię
    import shutil
    shutil.copy(model_path, latest_model)
    shutil.copy(meta_path, latest_meta)
    
    logger.info("[ML] Nowy model wyceny wdrożony.")
    return True

if __name__ == "__main__":
    train_model()
