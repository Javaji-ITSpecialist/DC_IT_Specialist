# Design Notes

This document explains the approach, the tools chosen, and the assumptions
made — and ties each decision back to something specific in the discovery
interview notes, since those notes contained the actual requirements for
this prototype.

## Approach

The pipeline is three stages, kept in three separate files on purpose so
each can be reasoned about (and improved) independently:

1. **OCR extraction** (`ocr_engine.py`) — turn a label photo into raw text.
2. **Field comparison** (`matcher.py`) — decide whether the application data
   matches what's on the label, field by field.
3. **Web app** (`app.py` + `templates/`) — single-label and batch workflows,
   wired together with a UI simple enough to meet the usability bar
   described below.

## Key decisions, and why

**Local OCR (Tesseract) instead of a cloud vision/LLM API.**
Two notes drove this directly: Marcus mentioned the office firewall blocks
outbound traffic to a lot of domains and specifically broke the prior
scanning vendor's ML endpoint calls, and Sarah said the same pilot's 30-40
second round-trip made agents abandon it entirely in favor of doing it by
eye. A local OCR engine has no network dependency (so it can't be blocked
by the firewall in a real deployment) and, as tested, runs in under two
seconds per label on modest hardware — comfortably inside the "~5 seconds
or nobody uses it" requirement. The trade-off is that Tesseract is less
capable than a modern vision-LLM at reading heavily skewed or glare-heavy
photos; see "Known limitations."

**Fuzzy matching for Brand Name / Class-Type, strict exact matching for
the Government Warning.**
These are opposite requirements from two different interviewees, and
the code treats them as genuinely different rules rather than one generic
"similarity score":
- Dave Morrison's example — `STONE'S THROW` vs `Stone's Throw` — is
  explicitly *not* a real mismatch. `matcher.py` normalizes case and
  punctuation and uses a fuzzy-match threshold (90/100) for brand name and
  class/type, so this case passes (verified in testing — see below).
- Jenny Park's note is the opposite: the warning statement has to be
  "exact... word-for-word," and specifically the phrase
  `GOVERNMENT WARNING:` has to appear in all caps — she gave a real example
  of catching someone who used title case instead. So the warning check
  in `matcher.py` does two independent things: a near-exact wording
  comparison (threshold 97/100, intentionally much stricter than the 90
  used elsewhere) AND a case-sensitive substring check for
  `GOVERNMENT WARNING:` against the raw (non-lowercased) OCR text. Either
  one failing rejects the label on that field.

**Numeric fields (ABV, net contents) are parsed and compared as numbers,
not strings.**
"45%" vs "45.0%" or "750mL" vs "750 mL" are the same value; comparing them
as text would produce false mismatches. Both fields extract the numeric
value via regex and compare with a small tolerance, normalizing volume
units (mL vs L) along the way.

**Plain, low-density UI.**
Sarah's explicit benchmark was "my mother could figure it out" — she's 73
and only recently learned to video-call. The interface is a single form
per page, large text, high contrast, and plain-language verdicts
("Mismatch found — needs agent attention" rather than raw status codes) on
the main view, with technical detail (raw OCR text, similarity scores)
tucked behind `<details>` disclosure elements for anyone who wants to dig
in (this mainly serves agents like Jenny who are comfortable with more
detail, without cluttering the view for agents like Dave who aren't).

**Batch mode matches images to applications by filename, via a CSV.**
Sarah's note about Janet in Seattle wanting to handle 200-300 applications
at once from large importers was the direct driver for this. Rather than
building a multi-step "assign each image to each row" UI (slow, error-prone
at that volume), the batch workflow expects each label image to be named
after its `application_id` (e.g. `APP-1001.jpg`), so an importer or agent
can just select a CSV and a folder of images and get results for the whole
batch in one submission. This is a reasonable assumption for a prototype
but would need to be validated against how importers actually name their
files in practice before being used for real intake.

**No data retention.**
Marcus flagged PII and document-retention policy as real concerns for
any *production* deployment, and said not to "do anything crazy" for the
prototype. Uploaded label images are processed in memory/temp storage and
deleted immediately after the verdict is produced — nothing is logged,
stored, or sent anywhere. This is intentionally conservative for a public
take-home submission, independent of what a real production system's
retention policy would eventually look like.

## Assumptions made

- The Government Warning wording used for comparison is the standard
  federal statement; the code assumes a single fixed required statement
  rather than looking up per-product-type variants (there are some minor
  wording differences allowed for certain wine/beer categories per TTB
  guidance, which a production system would need to model explicitly).
- "Matches within tolerance" for ABV uses a small numeric tolerance
  (0.05) to absorb OCR rounding noise, not to allow genuinely different
  ABV values to pass.
- Batch mode assumes one image per application (a label has one front
  label per submission for this prototype's purposes); real submissions
  sometimes include front + back label images, which would need a
  clearer naming/pairing convention.
- No authentication or role-based access is implemented, since this is a
  standalone prototype, not an integration with COLA or any system holding
  real applicant data.

## Known limitations / explicitly out of scope

- **Perspective/glare correction** — Jenny raised this as a nice-to-have
  and explicitly flagged it as possibly out of scope for a prototype. It's
  a substantial computer-vision problem on its own (perspective
  correction, glare inpainting) and wasn't attempted here beyond basic
  grayscale + autocontrast preprocessing. The app does report an OCR
  confidence score so agents have a signal for when to distrust a result
  rather than the tool silently guessing.
- **No COLA integration** — explicitly out of scope per Marcus's notes;
  this is a standalone proof-of-concept.
- **Production-grade deployment concerns** (auth, logging, monitoring,
  horizontal scaling for peak season volume) are not implemented, since
  the brief asked for a prototype, not a production system.

## Testing performed

`matcher.py`'s rules were unit-tested directly against Dave's and Jenny's
specific examples (casing-only brand name differences pass; genuinely
different brand names fail; non-caps warning statements fail) before being
wired into the web app. The full pipeline was then exercised end-to-end
through actual HTTP requests against the running Flask app, for both the
single-label and batch routes, using four generated test labels covering:
an exact match, a casing-only difference, a genuine ABV mismatch, and a
warning-capitalization mismatch. All four produced the expected verdict.
Per-label processing time was consistently under 2 seconds.
