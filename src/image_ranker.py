"""
Uses a Hugging Face image-aesthetic-scoring model to rank a property's
photos from best to worst, so we can pick a genuinely "best" RankedImage
instead of arbitrarily using whichever photo the source marked as main.

Model: cafeai/cafe_aesthetic -- a small, CPU-friendly image classifier
that scores how aesthetically pleasing a photo looks. Downloads once
(~350MB) from Hugging Face's hub the first time it's used, then it's
cached locally (see hf_cache/ volume mount) -- no GPU, no API key,
no paid account needed.

This ranks purely on visual "does it look good" -- it does not consider
the property's description, amenities, or room content at all.
"""
import io
import requests
from PIL import Image
from transformers import pipeline

_classifier = None


def _get_classifier():
    """Loads the model once and reuses it -- loading it per-image would be very slow."""
    global _classifier
    if _classifier is None:
        _classifier = pipeline("image-classification", model="cafeai/cafe_aesthetic")
    return _classifier


def _score_image(image_url: str) -> float:
    """Downloads one image and returns an aesthetic score between 0 and 1."""
    response = requests.get(image_url, timeout=10)
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content)).convert("RGB")

    classifier = _get_classifier()
    results = classifier(image)
    # results look like: [{'label': 'aesthetic', 'score': 0.87}, {'label': 'not_aesthetic', 'score': 0.13}]
    return next((r["score"] for r in results if r["label"] == "aesthetic"), 0.0)


def rank_images(image_urls: list) -> list:
    """
    Takes a list of image URLs, returns them sorted best-to-worst by
    aesthetic score. Skips any image that fails to download or score
    (broken URL, timeout, etc.) rather than crashing the whole ranking --
    a single bad photo shouldn't block ranking the rest.
    """
    scored = []
    for url in image_urls:
        try:
            score = _score_image(url)
            scored.append((url, score))
        except Exception as e:
            print(f"Skipping {url}: {e}")

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [url for url, _ in scored]