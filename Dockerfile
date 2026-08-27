# WeCare FastAPI Backend — Production Dockerfile for Railway / Container Platforms
FROM python:3.11-slim

# Avoid buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

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

# Ensure upload directories exist and start script is executable
RUN mkdir -p uploads/profiles uploads/caretaker_docs uploads/complaints && \
    chmod +x start.sh

EXPOSE 8000

# Launch through start.sh entrypoint
CMD ["./start.sh"]
