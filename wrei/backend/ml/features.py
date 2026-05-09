def extract_features(listing):
    """
    Ekstrakcja cech z ogłoszenia do celów ML.
    Zwraca słownik z cechami numerycznymi.
    """
    features = {}
    
    # 1. Powierzchnia
    features["area"] = float(listing.get("area")) if listing.get("area") else 0.0
    
    # 2. Pokoje
    try:
        features["rooms"] = int(listing.get("rooms")) if listing.get("rooms") else 1
    except (ValueError, TypeError):
        features["rooms"] = 1
        
    # 3. Floor ratio
    floor = listing.get("floor")
    total_floors = listing.get("total_floors")
    if floor is not None and total_floors and total_floors > 0:
        features["floor_ratio"] = floor / total_floors
    else:
        features["floor_ratio"] = 0.5 # Wartość domyślna
        
    # 4. Rok budowy
    features["year_built"] = listing.get("year_built") or 1990
    
    # 5. Stan (condition)
    condition = (listing.get("condition") or "").lower()
    if "now" in condition:
        features["condition_encoded"] = 3
    elif "dobr" in condition:
        features["condition_encoded"] = 2
    elif "sred" in condition or "śred" in condition:
        features["condition_encoded"] = 1
    elif "remon" in condition:
        features["condition_encoded"] = 0
    else:
        features["condition_encoded"] = 2 # domyślnie dobry
        
    # 6. Typ budynku (building_type)
    bt = (listing.get("building_type") or "").lower()
    if "apartament" in bt:
        features["building_type_encoded"] = 3
    elif "kamienica" in bt:
        features["building_type_encoded"] = 2
    elif "blok" in bt:
        features["building_type_encoded"] = 1
    else:
        features["building_type_encoded"] = 1
        
    # 7. Cechy binarne
    listing_features = listing.get("features") or {}
    if isinstance(listing_features, dict):
        features["has_balcony"] = 1 if listing_features.get("balcony") or listing_features.get("balkon") else 0
        features["has_parking"] = 1 if listing_features.get("parking") or listing_features.get("garaż") else 0
        features["has_elevator"] = 1 if listing_features.get("elevator") or listing_features.get("winda") else 0
        features["has_storage"] = 1 if listing_features.get("storage") or listing_features.get("piwnica") else 0
    else:
        features["has_balcony"] = 0
        features["has_parking"] = 0
        features["has_elevator"] = 0
        features["has_storage"] = 0
        
    # 8. Własność (ownership)
    own = (listing.get("ownership") or "").lower()
    features["ownership_encoded"] = 0 if "spółdzielcz" in own or "spoldzielcz" in own else 1
    
    # 9. Dzielnica
    # Target encoding bedzie obslugiwany przez slownik median
    # Na zewnatrz tej funkcji dodamy target encoding dzielnicy
    features["district"] = listing.get("district") or "Warszawa"
    
    return features
