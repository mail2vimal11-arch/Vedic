FROM python:3.11-slim

LABEL maintainer="Vedic Astrology Team"
LABEL description="Jyotish — Vedic Astrology Calculator"

# System deps for pyswisseph
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r vedic && useradd -r -g vedic -d /app vedic

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create output directory
RUN mkdir -p /app/output && chown -R vedic:vedic /app

USER vedic

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')" || exit 1

# Run with Gunicorn
CMD ["gunicorn", "wsgi:app", "-c", "gunicorn_config.py"]
