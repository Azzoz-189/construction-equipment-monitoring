FROM python:3.11-slim

WORKDIR /app

# Copy and install dependencies (paths relative to project root build context)
COPY services/dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY services/dashboard/src/ ./src/

# Config will be mounted via docker-compose volume

EXPOSE 8501

CMD ["streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
