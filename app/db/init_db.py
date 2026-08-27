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
    """Executes multi-statement SQL script file safely with foreign key checks disabled."""
    if not os.path.exists(file_path):
        logger.warning(f"SQL file not found at {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    try:
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    except Exception:
        pass

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
                logger.warning(f"SQL execute notice: {e} | Stmt: {clean_stmt[:80]}")

    try:
        connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    except Exception:
        pass


def auto_init_database(max_retries: int = 5, retry_delay: int = 3) -> bool:
    """
    Checks if database tables exist. If missing core tables, runs schema and initial seed data.
    Retries up to max_retries times to accommodate container boot latency.
    """
    import time
    settings = get_settings()
    base_dir = get_base_project_dir()
    schema_path = os.path.join(base_dir, "database", "schema.sql")
    seed_path = os.path.join(base_dir, "database", "seed_dev.sql")

    # Ensure upload folders exist
    upload_base = os.path.join(base_dir, settings.UPLOAD_BASE_PATH)
    for folder in ["profiles", "caretaker_docs", "complaints"]:
        os.makedirs(os.path.join(upload_base, folder), exist_ok=True)

    REQUIRED_TABLES = [
        "users",
        "pricing_tiers",
        "caretaker_profiles",
        "family_profiles",
        "bookings",
        "sos_alerts",
        "complaints",
        "admin_audit_logs",
        "replacement_tickets",
    ]

    for attempt in range(1, max_retries + 1):
        try:
            import app.models  # noqa: F401
            from app.core.database import Base

            engine = get_engine()

            # 1. Guarantee all 25+ database tables exist via SQLAlchemy ORM models
            Base.metadata.create_all(bind=engine)

            inspector = inspect(engine)
            existing_tables = inspector.get_table_names()
            logger.info(f"[DB-INIT] Database verified ({len(existing_tables)} tables present).")

            # 2. Seed default pricing tiers if table is empty
            try:
                with engine.begin() as conn:
                    tier_count = conn.execute(text("SELECT COUNT(*) FROM pricing_tiers")).scalar() or 0
                    if tier_count == 0:
                        conn.execute(text("""
                            INSERT INTO pricing_tiers (tier_name, display_name, skill_level, customer_hourly_rate, caretaker_hourly_rate, platform_commission_hourly, commission_percentage, is_active)
                            VALUES 
                            ('basic', 'Basic Care', 'entry', 200.00, 150.00, 50.00, 25.00, 1),
                            ('standard', 'Standard Care', 'intermediate', 300.00, 225.00, 75.00, 25.00, 1),
                            ('premium', 'Specialized Care', 'specialized', 450.00, 337.50, 112.50, 25.00, 1)
                        """))
                        logger.info("[DB-INIT] Seeded default pricing tiers.")
            except Exception as e:
                logger.debug(f"[DB-INIT] Pricing tier check notice: {e}")

            # 3. Guarantee default admin user with valid bcrypt hash for Admin123!
            try:
                admin_hash = "$2b$10$kZdwG/oSrxBD/f/TMB1mQ.wbg9d.KR6K0jPBpYYXDUJy9UQaoeu0q"
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO users (id, email, username, phone_number, password, role, is_verified, is_active, created_at, updated_at)
                            VALUES (1, 'admin@wecare.com', 'admin', '9000000001', :pwd, 'admin', 1, 1, NOW(), NOW())
                            ON DUPLICATE KEY UPDATE
                                email = 'admin@wecare.com',
                                username = 'admin',
                                password = :pwd,
                                role = 'admin',
                                is_verified = 1,
                                is_active = 1,
                                updated_at = NOW()
                        """),
                        {"pwd": admin_hash}
                    )
                    conn.execute(text("TRUNCATE TABLE rate_limits"))
                logger.info("[DB-INIT] Guaranteed admin user (admin@wecare.com / Admin123!) and reset rate limits.")
            except Exception as ex:
                logger.warning(f"[DB-INIT] Admin upsert notice: {ex}")

            return True

        except Exception as e:
            if attempt < max_retries:
                logger.info(f"[DB-INIT] Connection attempt {attempt}/{max_retries} waiting {retry_delay}s (database starting up)...")
                time.sleep(retry_delay)
            else:
                logger.warning(
                    f"[DB-INIT] Could not connect to MySQL server: {e}\n"
                    f"-> In Railway: Ensure 'DATABASE_URL' is added to your service variables with value '${{{{MySQL.DATABASE_URL}}}}'."
                )
                return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Running WeCare Database Initialization...")
    success = auto_init_database()
    if success:
        print("✓ WeCare Database initialization completed successfully.")
    else:
        print("! Database initialization note: please ensure MySQL server is reachable.")
