# Production-ready Python image for Cloud Run
# Uses python:3.12-slim (~40MB base) with minimal attack surface
FROM python:3.12-slim

# Install curl for Cloud Run health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run injects PORT env var; uvicorn binds to 0.0.0.0:$PORT
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
