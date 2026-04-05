FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OpenCV + ffmpeg with AV1 (dav1d) support
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies (paths relative to project root build context)
COPY services/cv_service/requirements.txt .

# Install CPU-only PyTorch first (avoids downloading 900MB+ of CUDA dependencies)
RUN pip install --no-cache-dir torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY services/cv_service/src/ ./src/

# Config will be mounted via docker-compose volume
# Videos directory will be mounted via docker-compose volume

CMD ["python", "-m", "src.main"]
