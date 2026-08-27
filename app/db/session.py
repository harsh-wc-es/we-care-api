"""
WeCare FastAPI — Database Session Dependency

global $conn used throughout every endpoint.
FastAPI uses dependency injection instead.
"""

from typing import Generator

from sqlalchemy.orm import Session

from app.core.database import get_session_factory


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Usage in route handlers:
        def my_endpoint(db: Session = Depends(get_db)):
            ...

    every endpoint does `global $conn;` to get the PDO handle.
    This dependency provides the same — one session per request, auto-closed.
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
