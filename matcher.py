"""
matcher.py

Business rules for comparing OCR'd label text against a submitted
application. This is where the actual "verification" logic lives --
deliberately separated from OCR so the matching rules can be tuned
without touching the extraction code.

Design decisions (see DESIGN.md for full rationale):

- Brand name / class-type: FUZZY match. Per Dave Morrison's interview
  note, "STONE'S THROW" vs "Stone's Throw" should NOT be flagged as a
  mismatch -- that's the same brand name, just different casing/
  punctuation. We normalize case/whitespace/punctuation and use a
  similarity threshold rather than exact string equality.

- Government Warning statement: STRICT match. Per Jenny Park's note,
  the warning has to be exact -- correct wording, and "GOVERNMENT
  WARNING:" specifically in all caps. We check both the exact wording
  (allowing only for OCR whitespace/line-break noise) AND that the
  required prefix appears in all caps in the source image text, since
  that formatting requirement is itself part of what agents check for.

- ABV / net contents: NUMERIC match with unit normalization (e.g.
  "45%" == "45.0%", "750 mL" == "750ml").
"""

import re
from dataclasses import dataclass
from rapidfuzz import fuzz


REQUIRED_WARNING_TEXT = (
    "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK "
    "ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. "
    "(2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR "
    "OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
)

FUZZY_MATCH_THRESHOLD = 90  # 0-100; tuned to allow case/punctuation drift
                            # but still catch genuinely different names


@dataclass
class FieldResult:
    field: str
    application_value: str
    label_value: str
    status: str      # "match" | "mismatch" | "not_found"
    detail: str = ""


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip common punctuation noise."""
    text = text.lower()
    text = re.sub(r"[^\w\s%.]", "", text)   # drop punctuation except % and .
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fuzzy_field_check(field_name: str, application_value: str, ocr_text: str) -> FieldResult:
    norm_app = _normalize(application_value)
    norm_ocr = _normalize(ocr_text)

    if not norm_app:
        return FieldResult(field_name, application_value, "", "not_found",
                            "No value provided in application for this field.")

    # Search for the best matching window of text in the OCR output, since
    # the OCR text is a full label dump, not just this one field.
    score = fuzz.partial_ratio(norm_app, norm_ocr)

    if score >= FUZZY_MATCH_THRESHOLD:
        return FieldResult(field_name, application_value, application_value,
                            "match", f"Fuzzy match score: {score}")
    else:
        return FieldResult(field_name, application_value, ocr_text.strip()[:120],
                            "mismatch", f"Fuzzy match score: {score} (below threshold {FUZZY_MATCH_THRESHOLD})")


def _check_abv(application_value: str, ocr_text: str) -> FieldResult:
    """Extract a percentage figure from both sides and compare numerically."""
    def parse_pct(s):
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", s)
        return float(m.group(1)) if m else None

    app_pct = parse_pct(application_value)
    ocr_pct = parse_pct(ocr_text)

    if app_pct is None:
        return FieldResult("Alcohol Content", application_value, "", "not_found",
                            "Could not parse a % value from the application.")
    if ocr_pct is None:
        return FieldResult("Alcohol Content", application_value, "", "mismatch",
                            "No % value found on label via OCR.")
    if abs(app_pct - ocr_pct) < 0.05:
        return FieldResult("Alcohol Content", application_value, f"{ocr_pct}%",
                            "match", "ABV values match within tolerance.")
    return FieldResult("Alcohol Content", application_value, f"{ocr_pct}%",
                        "mismatch", f"Application says {app_pct}%, label OCR reads {ocr_pct}%.")


def _check_net_contents(application_value: str, ocr_text: str) -> FieldResult:
    """Extract a volume (mL) and compare, normalizing common unit spellings."""
    def parse_ml(s):
        s = s.lower().replace(" ", "")
        m = re.search(r"(\d+(?:\.\d+)?)ml", s)
        if m:
            return float(m.group(1))
        m = re.search(r"(\d+(?:\.\d+)?)l\b", s)
        if m:
            return float(m.group(1)) * 1000
        return None

    app_ml = parse_ml(application_value)
    ocr_ml = parse_ml(ocr_text)

    if app_ml is None:
        return FieldResult("Net Contents", application_value, "", "not_found",
                            "Could not parse a volume from the application.")
    if ocr_ml is None:
        return FieldResult("Net Contents", application_value, "", "mismatch",
                            "No volume found on label via OCR.")
    if abs(app_ml - ocr_ml) < 0.5:
        return FieldResult("Net Contents", application_value, f"{ocr_ml:.0f} mL",
                            "match", "Net contents match.")
    return FieldResult("Net Contents", application_value, f"{ocr_ml:.0f} mL",
                        "mismatch", f"Application says {app_ml} mL, label OCR reads {ocr_ml} mL.")


def _check_warning(ocr_text: str) -> FieldResult:
    """Strict check for the Government Warning statement.

    Two things are verified independently, per Jenny's note that people
    "get creative" with this specific field:
      1. The wording matches the required statement (allowing only for
         OCR line-break/whitespace noise -- not for paraphrasing).
      2. The literal string "GOVERNMENT WARNING:" appears in the source
         text in ALL CAPS (case-sensitive check against the raw OCR
         output, not the normalized/lowercased version used elsewhere).
    """
    normalized_ocr = re.sub(r"\s+", " ", ocr_text).strip()
    normalized_required = re.sub(r"\s+", " ", REQUIRED_WARNING_TEXT).strip()

    wording_score = fuzz.partial_ratio(normalized_required.lower(), normalized_ocr.lower())
    wording_ok = wording_score >= 97  # deliberately strict vs. the 90 used elsewhere

    caps_prefix_present = "GOVERNMENT WARNING:" in ocr_text  # case-sensitive on purpose

    if wording_ok and caps_prefix_present:
        return FieldResult("Government Warning", "(required statement)",
                            "Present, exact wording, correct capitalization",
                            "match", f"Wording similarity: {wording_score}")

    problems = []
    if not wording_ok:
        problems.append(f"wording similarity only {wording_score} (required >= 97)")
    if not caps_prefix_present:
        problems.append('"GOVERNMENT WARNING:" not found in all caps')

    return FieldResult("Government Warning", "(required statement)",
                        ocr_text.strip()[:160], "mismatch", "; ".join(problems))


def verify_label(application: dict, ocr_text: str) -> list:
    """Run all field checks and return a list of FieldResult objects.

    `application` is expected to have keys: brand_name, class_type,
    alcohol_content, net_contents. Missing keys are treated as blank.
    """
    results = []
    results.append(_fuzzy_field_check("Brand Name", application.get("brand_name", ""), ocr_text))
    results.append(_fuzzy_field_check("Class/Type", application.get("class_type", ""), ocr_text))
    results.append(_check_abv(application.get("alcohol_content", ""), ocr_text))
    results.append(_check_net_contents(application.get("net_contents", ""), ocr_text))
    results.append(_check_warning(ocr_text))
    return results


def overall_status(results: list) -> str:
    """Roll individual field results up into one overall verdict."""
    if any(r.status == "mismatch" for r in results):
        return "REJECTED"
    if any(r.status == "not_found" for r in results):
        return "NEEDS_REVIEW"
    return "APPROVED"
