"""
WeCare — System Service (Part 11)

Migrates api/v1/system/db_diagnostics.
Provides database connectivity and configuration diagnostic probes.
"""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import APIException

logger = logging.getLogger(__name__)


def get_db_diagnostics(db: Session) -> Dict[str, Any]:
    """
    Route: api/v1/system/db_diagnostics

    Strict Security Gate:
    L6-8: Accessible only when APP_DEBUG is True. Returns 404 otherwise.
    """
    settings = get_settings()

    if not settings.APP_DEBUG:
        raise APIException(message="Not found", status_code=404)

    host = settings.DB_HOST
    port = str(settings.DB_PORT)
    db_name = settings.DB_NAME or settings.DB_DATABASE
    db_user = settings.DB_USER or settings.DB_USERNAME
    db_pass = settings.DB_PASS or settings.DB_PASSWORD
    charset = settings.DB_CHARSET

    name_key = "DB_NAME" if settings.DB_NAME else ("DB_DATABASE" if settings.DB_DATABASE else None)
    user_key = "DB_USER" if settings.DB_USER else ("DB_USERNAME" if settings.DB_USERNAME else None)
    password_key = "DB_PASS" if settings.DB_PASS else ("DB_PASSWORD" if settings.DB_PASSWORD else None)

    db_connected = False
    users_table_exists = None
    admin_user_exists = None

    if db_name and db_user:
        try:
            # Probe users table
            row = db.execute(
                text(
                    "SELECT COUNT(*) AS cnt "
                    "FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() "
                    "  AND TABLE_NAME = 'users'"
                )
            ).fetchone()
            db_connected = True
            users_table_exists = bool(row and (row.cnt or 0) > 0)

            if users_table_exists:
                admin_row = db.execute(
                    text(
                        "SELECT COUNT(*) AS cnt "
                        "FROM users "
                        "WHERE email = :email AND role = 'admin'"
                    ),
                    {"email": "admin@wecare.com"},
                ).fetchone()
                admin_user_exists = bool(admin_row and (admin_row.cnt or 0) > 0)

        except Exception as e:
            logger.error(f"[db_diagnostics] Database probe failed: {e}")
            db_connected = False

    return {
        "env": {
            "loaded": True,
            "loader": "pydantic-settings",
            "location": "project_root",
        },
        "db": {
            "host": host,
            "port": port,
            "name": db_name,
            "user": db_user,
            "charset": charset,
            "password_configured": bool(db_pass),
            "name_key": name_key,
            "user_key": user_key,
            "password_key": password_key,
            "connected": db_connected,
        },
        "extensions": {
            "pdo_mysql": True,
            "mysqli": True,
        },
        "schema": {
            "users_table_exists": users_table_exists,
            "admin_user_exists": admin_user_exists,
        },
    }
