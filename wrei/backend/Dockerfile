FROM python:3.12-slim

WORKDIR /app

# System deps (lxml, psycopg2 native)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# spaCy model PL
RUN python -m spacy download pl_core_news_sm

# Migrations + kod
COPY backend/migrations ./backend/migrations
COPY backend ./backend

# Folder na pobrane zdjęcia (Faza 4)
RUN mkdir -p /app/photos

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
