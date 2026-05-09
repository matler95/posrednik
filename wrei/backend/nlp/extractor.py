import spacy
import logging

logger = logging.getLogger(__name__)

try:
    nlp = spacy.load("pl_core_news_sm")
except Exception as e:
    logger.warning(f"Nie udało się załadować modelu spaCy: {e}. Używam pustego modelu.")
    nlp = spacy.blank("pl")

def extract_structured_features(text: str) -> dict:
    if not text:
        return {}
        
    doc = nlp(text.lower())
    
    # Proste dopasowanie tekstowe (tokeny ze spaCy można analizować głębiej, np. lematami)
    lemmas = [token.lemma_ for token in doc]
    text_lower = text.lower()
    
    return {
        "has_balcony": any(w in lemmas for w in ["balkon", "loggia", "taras"]),
        "has_garage": any(w in lemmas for w in ["garaż", "parking", "miejsce", "postojowe"]),
        "has_elevator": any(w in lemmas for w in ["winda"]),
        "has_storage": any(w in lemmas for w in ["piwnica", "komórka", "schowek"]),
        "has_garden": any(w in lemmas for w in ["ogród", "ogródek"]),
    }
