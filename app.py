"""
app.py

Flask web app for the TTB label verification prototype.

Two workflows, matching the interview notes:
  1. Single-label review  (GET/POST /)          -- the day-to-day case.
  2. Batch review         (GET/POST /batch)      -- for large importers
     dumping 200-300 applications at once (Sarah's note re: Janet in
     Seattle).

Interface goal: "my mother could figure out" (Sarah's benchmark) --
so the UI is a single page, one big upload control, plain-language
results, no nested menus.

Performance goal: sub-5-second turnaround (Sarah's hard requirement,
learned from the failed scanning-vendor pilot). Local OCR on a single
label image typically completes in well under a second on modest
hardware; see DESIGN.md for informal timing notes.
"""

import os
import time
import uuid
from flask import Flask, render_template, request, redirect, url_for

from ocr_engine import extract_text_with_confidence
from matcher import verify_label, overall_status

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB per upload


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file_storage) -> str:
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(UPLOAD_DIR, safe_name)
    file_storage.save(path)
    return path


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    # --- POST: process a single label ---
    start = time.time()

    label_file = request.files.get("label_image")
    if not label_file or label_file.filename == "":
        return render_template("index.html", error="Please choose a label image to upload.")
    if not allowed_file(label_file.filename):
        return render_template("index.html", error="Please upload a PNG or JPG image.")

    application = {
        "brand_name": request.form.get("brand_name", ""),
        "class_type": request.form.get("class_type", ""),
        "alcohol_content": request.form.get("alcohol_content", ""),
        "net_contents": request.form.get("net_contents", ""),
    }

    image_path = save_upload(label_file)
    try:
        ocr_text, confidence = extract_text_with_confidence(image_path)
        results = verify_label(application, ocr_text)
        verdict = overall_status(results)
    finally:
        # Prototype cleans up uploaded files immediately after processing --
        # no label images are retained. See DESIGN.md re: PII/retention.
        if os.path.exists(image_path):
            os.remove(image_path)

    elapsed = time.time() - start

    return render_template(
        "result.html",
        application=application,
        results=results,
        verdict=verdict,
        ocr_text=ocr_text,
        confidence=round(confidence, 1),
        elapsed=round(elapsed, 2),
    )


@app.route("/batch", methods=["GET", "POST"])
def batch():
    if request.method == "GET":
        return render_template("batch.html")

    # --- POST: process multiple labels at once ---
    # Batch mode expects one uploaded image per application, matched by
    # filename (without extension) to an "application_id" column in the
    # uploaded CSV. This keeps the batch UI to "pick a CSV, pick a folder
    # of images, click submit" -- no per-row manual entry, which is what
    # actually makes 200-300 applications tractable in one sitting.
    import csv
    import io

    csv_file = request.files.get("applications_csv")
    label_files = request.files.getlist("label_images")

    if not csv_file or csv_file.filename == "":
        return render_template("batch.html", error="Please upload the applications CSV.")
    if not label_files or label_files[0].filename == "":
        return render_template("batch.html", error="Please upload one or more label images.")

    # Build a lookup of application_id -> uploaded file, keyed by filename stem.
    images_by_id = {}
    for f in label_files:
        if allowed_file(f.filename):
            stem = f.filename.rsplit(".", 1)[0]
            images_by_id[stem] = f

    csv_text = csv_file.read().decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(csv_text))

    batch_results = []
    start = time.time()

    for row in reader:
        app_id = row.get("application_id", "").strip()
        application = {
            "brand_name": row.get("brand_name", ""),
            "class_type": row.get("class_type", ""),
            "alcohol_content": row.get("alcohol_content", ""),
            "net_contents": row.get("net_contents", ""),
        }

        matching_file = images_by_id.get(app_id)
        if not matching_file:
            batch_results.append({
                "application_id": app_id,
                "verdict": "NO_IMAGE_FOUND",
                "results": [],
            })
            continue

        image_path = save_upload(matching_file)
        try:
            ocr_text, confidence = extract_text_with_confidence(image_path)
            results = verify_label(application, ocr_text)
            verdict = overall_status(results)
        finally:
            if os.path.exists(image_path):
                os.remove(image_path)

        batch_results.append({
            "application_id": app_id,
            "verdict": verdict,
            "results": results,
            "confidence": round(confidence, 1),
        })

    elapsed = time.time() - start

    return render_template("batch_results.html", batch_results=batch_results, elapsed=round(elapsed, 2))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
