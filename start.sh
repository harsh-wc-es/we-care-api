#!/bin/sh
set -e

echo "==> Running WeCare database auto-initialization..."
python -m scripts.init_db || true

echo "==> Starting Uvicorn ASGI server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
