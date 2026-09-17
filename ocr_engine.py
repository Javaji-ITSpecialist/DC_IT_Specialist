"""
ocr_engine.py

Handles extraction of raw text from an alcohol label image using local OCR
(Tesseract via pytesseract). No network calls are made here on purpose --
see DESIGN.md for why (agency firewall blocks outbound ML endpoints, and
the prior scanning-vendor pilot failed the ~5-second latency requirement).

The extraction is deliberately "dumb": it returns all text found on the
label, plus a couple of lightweight image-preprocessing passes to improve
OCR accuracy on real-world photos (skew, low contrast, glare). Field
*interpretation* (deciding which line is the brand name, ABV, etc.) is
handled separately in matcher.py, since that's a business-rules problem,
not an OCR problem.
"""

from PIL import Image, ImageOps, ImageFilter
import pytesseract


def _preprocess(image: Image.Image) -> Image.Image:
    """Light preprocessing to help OCR on imperfect photos.

    - Convert to grayscale (color doesn't help text recognition and can
      hurt it on labels with colored backgrounds).
    - Autocontrast to reduce the impact of poor lighting / mild glare.
    - Slight sharpening to help with soft-focus phone photos.

    This is intentionally conservative. Handling severely skewed or
    glare-heavy photos robustly (per Jenny's note) is flagged as future
    work in DESIGN.md rather than solved here -- a production system would
    likely need perspective correction and glare-inpainting, which is a
    substantial computer-vision project on its own.
    """
    gray = ImageOps.grayscale(image)
    contrasted = ImageOps.autocontrast(gray, cutoff=1)
    sharpened = contrasted.filter(ImageFilter.SHARPEN)
    return sharpened


def extract_text(image_path: str) -> str:
    """Run OCR on a label image and return the raw extracted text.

    Uses Tesseract's default page segmentation. Labels are short,
    structured documents, so this is a reasonable default; --psm 6
    (assume a single uniform block of text) is used as it performs better
    than the fully-automatic mode on the tightly-packed text common on
    bottle labels.
    """
    image = Image.open(image_path)
    processed = _preprocess(image)
    config = "--psm 6"
    text = pytesseract.image_to_string(processed, config=config)
    return text


def extract_text_with_confidence(image_path: str):
    """Same as extract_text, but also returns Tesseract's average word
    confidence (0-100). Used to warn reviewers when OCR quality is low
    (e.g. due to a bad photo) rather than silently returning garbage.
    """
    image = Image.open(image_path)
    processed = _preprocess(image)
    config = "--psm 6"
    data = pytesseract.image_to_data(
        processed, config=config, output_type=pytesseract.Output.DICT
    )
    confidences = [int(c) for c in data["conf"] if c not in ("-1", -1)]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    text = pytesseract.image_to_string(processed, config=config)
    return text, avg_confidence
