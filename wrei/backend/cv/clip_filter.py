"""
CLIP pre-filter — odrzuca zdjęcia które nie są wnętrzami/elewacjami mieszkania.
Używa openai/clip-vit-base-patch32 na CPU (PyTorch bez CUDA).
Filtruje: rzuty techniczne, loga, banery, mapy, zdjęcia placów budowy.

Wymagania (odkomentuj w requirements.txt):
    transformers
    torch  (pip install torch --index-url https://download.pytorch.org/whl/cpu)
    Pillow
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Kategorie które AKCEPTUJEMY
ACCEPT_LABELS = [
    "a photo of a living room interior",
    "a photo of a bedroom interior",
    "a photo of a kitchen interior",
    "a photo of a bathroom interior",
    "a photo of an apartment interior",
    "a photo of a building exterior",
    "a photo of an apartment balcony",
]

# Kategorie które ODRZUCAMY
REJECT_LABELS = [
    "a floor plan or architectural drawing",
    "a map or street view",
    "a logo or advertisement banner",
    "a construction site or unfinished building",
    "text and typography only",
    "a diagram or chart",
]

ALL_LABELS = ACCEPT_LABELS + REJECT_LABELS
_model = None
_processor = None


def _load_model():
    global _model, _processor
    if _model is not None:
        return _model, _processor
    try:
        from transformers import CLIPProcessor, CLIPModel
        logger.info("[CLIP] Ładowanie modelu openai/clip-vit-base-patch32...")
        _processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        _model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        _model.eval()
        logger.info("[CLIP] Model załadowany.")
        return _model, _processor
    except ImportError:
        logger.warning("[CLIP] transformers/torch niedostępne — pre-filter wyłączony")
        return None, None


def is_property_photo(image_path: Path, threshold: float = 0.25) -> bool:
    """
    Zwraca True jeśli zdjęcie wygląda jak wnętrze/elewacja mieszkania.
    threshold: minimalne prawdopodobieństwo dla etykiet ACCEPT vs REJECT.
    Przy błędzie lub braku modelu — domyślnie True (passthrough).
    """
    model, processor = _load_model()
    if model is None:
        return True  # fallback: nie filtruj

    try:
        from PIL import Image
        import torch

        image = Image.open(image_path).convert("RGB")
        inputs = processor(text=ALL_LABELS, images=image, return_tensors="pt", padding=True)

        with torch.no_grad():
            outputs = model(**inputs)
            probs = outputs.logits_per_image.softmax(dim=1)[0].tolist()

        n_accept = len(ACCEPT_LABELS)
        accept_score = sum(probs[:n_accept])
        reject_score = sum(probs[n_accept:])

        result = accept_score > reject_score and accept_score > threshold
        logger.debug("[CLIP] %s → accept=%.3f reject=%.3f → %s",
                     image_path.name, accept_score, reject_score, "OK" if result else "ODRZUCONE")
        return result
    except Exception as exc:
        logger.warning("[CLIP] Błąd analizy %s: %s", image_path, exc)
        return True  # passthrough przy błędzie


def filter_photos(photo_paths: list[Path]) -> list[Path]:
    """
    Filtruje listę ścieżek, zwraca tylko zdjęcia które przeszły CLIP.
    Zawsze zwraca min. 1 zdjęcie (pierwsze) jeśli wszystkie odrzucone.
    """
    if not photo_paths:
        return []

    accepted = [p for p in photo_paths if is_property_photo(p)]
    if not accepted:
        logger.debug("[CLIP] Wszystkie zdjęcia odrzucone — zwracam pierwsze jako fallback")
        return photo_paths[:1]

    return accepted
