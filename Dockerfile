FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN useradd --create-home --uid 10001 app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY wildrift ./wildrift
COPY static ./static
COPY data/tips.json data/item_aliases.json data/profile.default.json ./data/

# Download the current patch's data into the image, so the app is ready as soon as it starts.
RUN python -m wildrift.wildriftfire --force \
    && chown -R app:app /app/data /app/static

USER app
EXPOSE 8000

# Render sets $PORT; default to 8000 elsewhere.
CMD ["sh", "-c", "uvicorn wildrift.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
