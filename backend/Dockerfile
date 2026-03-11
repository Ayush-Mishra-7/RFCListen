FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

# Copy application code
COPY . .

# Create cache directory and generate the RFC index at build time
# This bakes rfc_index.json into the image so the API can serve RFC listings
# immediately on startup without needing a persistent filesystem.
RUN mkdir -p /app/cache && python scripts/update_rfc_index.py

# Expose the port (Render injects $PORT at runtime)
EXPOSE 3000

# Run the FastAPI server
# Render sets $PORT; fallback to 3000 for local development
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-3000}"]

