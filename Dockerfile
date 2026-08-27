# WeCare FastAPI Backend — Production Dockerfile for Railway / Container Platforms
FROM python:3.11-slim

# Avoid buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Install system runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code and database assets
COPY . .

# Ensure upload directories exist
RUN mkdir -p uploads/profiles uploads/caretaker_docs uploads/complaints

EXPOSE 8000

# Run database auto-migration and launch uvicorn
CMD ["sh", "-c", "python -m scripts.init_db && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
