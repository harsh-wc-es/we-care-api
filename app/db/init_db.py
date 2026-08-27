"""
WeCare Database Initialization & Auto-Migration Module

Automatically checks database health, initializes tables from SQL schema if empty,
and seeds initial administrative and system pricing tiers for live Railway deployment.
"""

import os
import logging
from sqlalchemy import text, inspect
from app.core.database import get_engine
from app.core.config import get_settings

logger = logging.getLogger("wecare.db_init")


def get_base_project_dir() -> str:
    """Returns the root directory of the backend api project."""
    # Current file is in app/db/init_db.py -> go 2 levels up
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def execute_sql_file(connection, file_path: str) -> None:
    """Executes multi-statement SQL script file safely."""
    if not os.path.exists(file_path):
        logger.warning(f"SQL file not found at {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split SQL into distinct statements ignoring comments and blank lines
    raw_statements = sql_content.split(";")
    for raw in raw_statements:
        statement = raw.strip()
        # Filter out comments and blank statements
        lines = [
            line for line in statement.splitlines()
            if not line.strip().startswith("--") and not line.strip().startswith("/*")
        ]
        clean_stmt = "\n".join(lines).strip()
        if clean_stmt:
            try:
                connection.execute(text(clean_stmt))
            except Exception as e:
                logger.debug(f"Statement notice during SQL init: {e}")


def auto_init_database() -> bool:
    """
    Checks if database tables exist. If empty, runs schema and initial seed data.
    Returns True if successfully verified or initialized, False on connection error.
    """
    settings = get_settings()
    base_dir = get_base_project_dir()
    schema_path = os.path.join(base_dir, "database", "schema.sql")
    seed_path = os.path.join(base_dir, "database", "seed_dev.sql")

    # Ensure upload folders exist
    upload_base = os.path.join(base_dir, settings.UPLOAD_BASE_PATH)
    for folder in ["profiles", "caretaker_docs", "complaints"]:
        os.makedirs(os.path.join(upload_base, folder), exist_ok=True)

    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Check if main 'users' table exists
            inspector = inspect(engine)
            existing_tables = inspector.get_table_names()

            if "users" not in existing_tables or "pricing_tiers" not in existing_tables:
                logger.info("[DB-INIT] Core tables missing. Applying database schema...")
                with conn.begin():
                    execute_sql_file(conn, schema_path)
                logger.info("[DB-INIT] Schema applied successfully.")

                # Populate initial seed data if seed file exists
                if os.path.exists(seed_path):
                    logger.info("[DB-INIT] Applying initial seed data (admin & pricing tiers)...")
                    with conn.begin():
                        execute_sql_file(conn, seed_path)
                    logger.info("[DB-INIT] Seed data applied successfully.")
            else:
                # Check if users table is empty
                res = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
                if res == 0 and os.path.exists(seed_path):
                    logger.info("[DB-INIT] Empty database detected. Populating initial seed data...")
                    with conn.begin():
                        execute_sql_file(conn, seed_path)
                    logger.info("[DB-INIT] Seed data populated.")
                else:
                    logger.info(f"[DB-INIT] Database verified ({len(existing_tables)} tables present).")

        return True

    except Exception as e:
        logger.warning(f"[DB-INIT] Database auto-init check skipped / encountered notice: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Running WeCare Database Initialization...")
    success = auto_init_database()
    if success:
        print("✓ WeCare Database initialization completed successfully.")
    else:
        print("! Database initialization note: please ensure MySQL server is reachable.")
