FROM python:3.11-slim

WORKDIR /app

# Install ffmpeg for video processing
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies (paths relative to project root build context)
COPY services/video_ingestion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY services/video_ingestion/src/ ./src/

# Config will be mounted via docker-compose volume
# Videos directory will be mounted via docker-compose volume

CMD ["python", "-m", "src.downloader"]
