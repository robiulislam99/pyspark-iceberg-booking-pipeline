"""
Per-image analysis: aesthetic score (0-10) + room-type label.

Two separate Hugging Face models are used, since they do different jobs:
- cafeai/cafe_aesthetic: scores how visually pleasing a photo looks
  (0-1 internally, rescaled to 0-10 here per the requested output range).
- openai/clip-vit-base-patch32, used in "zero-shot" mode: matches a photo
  against an arbitrary list of text labels (bedroom, balcony, etc.)
  without ever being trained on those specific categories. This is the
  only realistic option here, since there's no pre-trained model that
  already knows this exact label set -- zero-shot lets us hand it any
  label list at call time instead.

Both models download once from Hugging Face's hub (~350MB + ~600MB) the
first time they're used, then are cached (see hf_cache/ volume mount) --
no GPU, no API key, no paid account needed.
"""
import io
import requests
from PIL import Image
from transformers import pipeline

ROOM_LABELS = ["bedroom", "balcony", "bathroom", "swimming pool", "house"]

_aesthetic_classifier = None
_room_classifier = None


def _get_aesthetic_classifier():
    global _aesthetic_classifier
    if _aesthetic_classifier is None:
        _aesthetic_classifier = pipeline("image-classification", model="cafeai/cafe_aesthetic")
    return _aesthetic_classifier


def _get_room_classifier():
    global _room_classifier
    if _room_classifier is None:
        _room_classifier = pipeline("zero-shot-image-classification", model="openai/clip-vit-base-patch32")
    return _room_classifier


def _download_image(image_url: str) -> Image.Image:
    response = requests.get(image_url, timeout=10)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content)).convert("RGB")


def _score_aesthetic(image: Image.Image) -> float:
    """Returns aesthetic score rescaled to 0-10 (model's native output is 0-1)."""
    classifier = _get_aesthetic_classifier()
    results = classifier(image)
    raw_score = next((r["score"] for r in results if r["label"] == "aesthetic"), 0.0)
    return round(raw_score * 10, 2)


def _classify_room(image: Image.Image, labels: list = ROOM_LABELS) -> tuple:
    """Returns (top_label, confidence) -- confidence is 0-1, CLIP's own similarity score."""
    classifier = _get_room_classifier()
    results = classifier(image, candidate_labels=labels)
    # results are sorted best-to-worst already: [{'label': 'bedroom', 'score': 0.81}, ...]
    top = results[0]
    return top["label"], round(top["score"], 4)


def analyze_image(image_url: str, labels: list = ROOM_LABELS) -> dict:
    """
    Downloads one image once, runs both models against it, returns:
      {"url": ..., "aesthetic_score": 0-10, "label": "bedroom", "label_confidence": 0-1}
    Raises on download/decode failure -- callers should catch and skip,
    same pattern as the rest of this pipeline.
    """
    image = _download_image(image_url)
    aesthetic_score = _score_aesthetic(image)
    label, label_confidence = _classify_room(image, labels)
    return {
        "url": image_url,
        "aesthetic_score": aesthetic_score,
        "label": label,
        "label_confidence": label_confidence,
    }


def analyze_images(image_urls: list, labels: list = ROOM_LABELS) -> list:
    """
    Analyzes every image, skipping any that fail to download/decode
    (broken URL, expired signed link, timeout, etc.) rather than
    crashing the whole batch -- one bad photo shouldn't block the rest.
    Returns a list of dicts sorted best-to-worst by aesthetic_score.
    """
    results = []
    for url in image_urls:
        try:
            results.append(analyze_image(url, labels))
        except Exception as e:
            print(f"Skipping {url}: {e}")

    results.sort(key=lambda r: r["aesthetic_score"], reverse=True)
    return results


def rank_images_with_scores(image_urls: list) -> list:
    """
    Backward-compatible: aesthetic-only ranking, (url, score) tuples,
    score on the ORIGINAL 0-1 scale -- kept as-is since s3_document_mapper.py
    and earlier debugging commands already rely on this exact shape/scale.
    """
    scored = []
    for url in image_urls:
        try:
            image = _download_image(url)
            classifier = _get_aesthetic_classifier()
            results = classifier(image)
            raw_score = next((r["score"] for r in results if r["label"] == "aesthetic"), 0.0)
            scored.append((url, raw_score))
        except Exception as e:
            print(f"Skipping {url}: {e}")

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def rank_images(image_urls: list) -> list:
    """
    Takes a list of image URLs, returns them sorted best-to-worst by
    aesthetic score (0-1 scale). Unchanged behavior -- still what
    s3_document_mapper.py calls for RankedImage/RankedImages.
    """
    scored = rank_images_with_scores(image_urls)
    return [url for url, _ in scored]