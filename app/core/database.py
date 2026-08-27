"""
WeCare FastAPI — Database Engine, Base, and Session Factory

config/database
Preserves: utf8mb4, exception mode, timezone behavior, FETCH_ASSOC default.

Architecture decision: Synchronous SQLAlchemy 2.0
Rationale: backend is sync; 40 transactions + 19 FOR UPDATE locks are
           safest to reproduce with sync SQLAlchemy.
"""

import datetime
import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base for all WeCare models.
    All models inherit from this class.
    """
    pass


def build_engine(settings=None):
    """
    Create the SQLAlchemy engine.

    equivalent PDO attributes preserved:
    - ATTR_ERRMODE = ERRMODE_EXCEPTION  → SQLAlchemy raises by default
    - ATTR_DEFAULT_FETCH_MODE = FETCH_ASSOC → ORM returns objects
    - ATTR_EMULATE_PREPARES = false → server-side prepared statements
    """
    if settings is None:
        settings = get_settings()

    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=10,
        max_overflow=20,
        echo=settings.APP_DEBUG,
    )

    @event.listens_for(engine, "connect")
    def _set_session_timezone(dbapi_connection, connection_record):
        """
        $conn->exec("SET time_zone = " . $conn->quote(date("P")));

        behavior:
        1. env sets date_default_timezone_set(APP_TIMEZONE) → default "Asia/Kolkata"
        2. database sets MySQL session timezone to date("P") output
        3. date("P") returns the UTC offset of the process timezone

        We reproduce this by computing the offset for the configured timezone.
        """
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(settings.APP_TIMEZONE)
            offset = datetime.datetime.now(tz).strftime("%z")
            # Format +0530 → +05:30
            offset_str = f"{offset[:3]}:{offset[3:]}"
        except Exception:
            offset_str = "+05:30"  # Fallback to Asia/Kolkata default

        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET time_zone = '{offset_str}'")
        cursor.close()

    return engine


def build_session_factory(engine=None):
    """Create a sessionmaker bound to the engine."""
    if engine is None:
        engine = build_engine()
    return sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


# ── Module-level singletons (lazy initialization) ──

_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the global engine singleton."""
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory():
    """Get or create the global session factory singleton."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = build_session_factory(get_engine())
    return _SessionLocal


def reset_engine():
    """Reset engine and session factory (for testing)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
