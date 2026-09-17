FROM python:3.11-slim

# Tesseract is a system package, not a pip package -- install it here so
# any Docker-based host (Render, Railway, Fly.io, etc.) has it available.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=5000
EXPOSE 5000

# Use gunicorn in production instead of Flask's dev server
RUN pip install --no-cache-dir gunicorn
CMD gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 30 app:app
