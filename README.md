# TTB Label Verification Prototype

A prototype web app that checks a photographed alcohol label against the data
submitted in a TTB label application, and flags matches/mismatches for a
compliance agent to review.

Built for the take-home project described in `instructions` — see
[DESIGN.md](DESIGN.md) for the reasoning behind each technical decision and
how it ties back to the stakeholder interview notes.

## What it does

- **Single label review** (`/`): upload one label photo, type in the fields
  from the application, get an instant APPROVED / REJECTED / NEEDS REVIEW
  verdict with a field-by-field breakdown.
- **Batch review** (`/batch`): upload a CSV of applications plus a folder of
  label images (matched by filename to `application_id`), get results for
  all of them in one pass — for large importers submitting 200-300
  applications at once.

## Requirements

- Python 3.9+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed and
  on your `PATH` (this does the actual text recognition; it runs locally,
  no internet connection or API key needed)

Install Tesseract:

```bash
# Debian/Ubuntu
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract
```

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python3 app.py
```

Then open **http://localhost:5000** in a browser.

- Go to **Single Label Review** to check one label at a time.
- Go to **Batch Review** to check many at once. A sample CSV is linked
  directly on that page (`static/sample_applications.csv`), formatted to
  match the four test label images in `sample_data/`.

## Trying it out immediately

`sample_data/` includes four generated test labels you can use right away
without needing your own photos:

| File | Scenario |
|---|---|
| `APP-1001.jpg` | Everything matches — should come back **APPROVED** |
| `APP-1002.jpg` | Brand name differs only in casing (`Old Tom Distillery` vs `OLD TOM DISTILLERY`) — should still come back **APPROVED**, since this isn't a real mismatch |
| `APP-1003.jpg` | ABV on the label (40%) differs from the application (45%) — should come back **REJECTED** |
| `APP-1004.jpg` | Government Warning text is present but not in the required all-caps format — should come back **REJECTED** |

For the single-label page, type in the matching field values by hand (see
`sample_data/applications.csv` for the values used to generate each label).
For the batch page, just upload `sample_data/applications.csv` along with
all four `.jpg` files at once.

## Project layout

```
app.py              Flask routes (single + batch review)
ocr_engine.py        Local OCR extraction (Tesseract via pytesseract)
matcher.py           Field comparison / business rules (fuzzy vs. strict matching)
templates/           HTML pages (plain, high-contrast, minimal UI)
static/              Sample CSV for the batch workflow
sample_data/         Generated test label images + matching applications.csv
```

## Known limitations (by design, for a time-boxed prototype)

- No integration with the actual COLA system — this is a standalone
  proof-of-concept, as scoped in the take-home instructions.
- No perspective correction or glare removal for badly-angled/lit photos.
  Basic grayscale + autocontrast preprocessing is applied, but severely
  skewed or glare-heavy images will still produce poor OCR results (the
  app surfaces an OCR confidence score so agents know when to be
  suspicious of a result rather than trusting it blindly).
- Uploaded label images are deleted immediately after processing — none
  are stored or logged, since this is a public-facing prototype and no
  data retention/PII review has been done for it.
- No authentication. Not intended for production or for real applicant
  data.

See DESIGN.md for the full reasoning behind these trade-offs.
