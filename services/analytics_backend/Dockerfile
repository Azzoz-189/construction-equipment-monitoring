FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies (paths relative to project root build context)
COPY services/analytics_backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY services/analytics_backend/src/ ./src/

# Config will be mounted via docker-compose volume

# Expose FastAPI port
EXPOSE 8000

CMD ["python", "-m", "src.main"]
