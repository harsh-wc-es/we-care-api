"""
CLI Entrypoint for Railway / Container Pre-Deploy Database Initialization.

Usage:
    python -m scripts.init_db
"""

import sys
import logging
from app.db.init_db import auto_init_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("init_db")

if __name__ == "__main__":
    logger.info("Starting database auto-initialization...")
    try:
        success = auto_init_database()
        if success:
            logger.info("Database initialized / verified successfully.")
            sys.exit(0)
        else:
            logger.warning("Database init could not complete (MySQL might be starting up).")
            # Don't fail the container start if the DB is still initializing in parallel
            sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error during init_db: {e}", exc_info=True)
        sys.exit(0)
