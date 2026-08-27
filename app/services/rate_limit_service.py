"""
WeCare — Rate Limit Service (STEP 9)

Mirrors helpers/rate_limit exactly.
DB-backed rate limiting via `rate_limits` table.
Disabled in APP_ENV=local (matching behavior).
"""

import time
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import APIException


def _rate_limit_enabled() -> bool:
    """
    Route: rate_limit_enabled() — rate_limit L15-32
    """
    settings = get_settings()
    return settings.rate_limit_active


def _rate_limit_key(key: str | None = None) -> str:
    """
    Route: rate_limit_key() — rate_limit L6-13
    """
    if key:
        return key.strip().lower()
    return "unknown"


def enforce_rate_limit(
    db: Session,
    action: str,
    key: str | None = None,
    max_attempts: int = 5,
    window_seconds: int = 900,
    block_seconds: int = 900,
    ip: str | None = None,
) -> None:
    """
    Route: enforce_rate_limit() — rate_limit L34-83

    Raises APIException(429) if rate limited.
    """
    if not _rate_limit_enabled():
        return

    rate_key = _rate_limit_key(key or ip)
    now = int(time.time())

    row = db.execute(
        text(
            "SELECT id, attempts, window_start, blocked_until FROM rate_limits "
            "WHERE rate_key = :key AND action = :action LIMIT 1"
        ),
        {"key": rate_key, "action": action},
    ).mappings().first()

    # Check if currently blocked
    if row and row["blocked_until"]:
        blocked_ts = row["blocked_until"]
        if isinstance(blocked_ts, str):
            blocked_ts = datetime.strptime(blocked_ts, "%Y-%m-%d %H:%M:%S")
        if isinstance(blocked_ts, datetime):
            if blocked_ts.timestamp() > now:
                raise APIException(
                    "Too many attempts. Please try again later.",
                    status_code=429,
                )

    # Window expired or first attempt — reset
    if not row:
        db.execute(
            text(
                "INSERT INTO rate_limits (rate_key, action, attempts, window_start, blocked_until) "
                "VALUES (:key, :action, 1, NOW(), NULL) "
                "ON DUPLICATE KEY UPDATE attempts = 1, window_start = NOW(), blocked_until = NULL"
            ),
            {"key": rate_key, "action": action},
        )
        db.commit()
        return

    window_start = row["window_start"]
    if isinstance(window_start, str):
        window_start = datetime.strptime(window_start, "%Y-%m-%d %H:%M:%S")
    if isinstance(window_start, datetime):
        if window_start.timestamp() + window_seconds < now:
            db.execute(
                text(
                    "INSERT INTO rate_limits (rate_key, action, attempts, window_start, blocked_until) "
                    "VALUES (:key, :action, 1, NOW(), NULL) "
                    "ON DUPLICATE KEY UPDATE attempts = 1, window_start = NOW(), blocked_until = NULL"
                ),
                {"key": rate_key, "action": action},
            )
            db.commit()
            return

    # Increment attempts
    attempts = int(row["attempts"]) + 1
    blocked_until = None
    if attempts > max_attempts:
        blocked_until = datetime.fromtimestamp(now + block_seconds).strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        text(
            "UPDATE rate_limits SET attempts = :attempts, blocked_until = :blocked WHERE id = :id"
        ),
        {"attempts": attempts, "blocked": blocked_until, "id": row["id"]},
    )
    db.commit()

    if blocked_until:
        raise APIException(
            "Too many attempts. Please try again later.",
            status_code=429,
        )


def clear_rate_limit(
    db: Session,
    action: str,
    key: str | None = None,
) -> None:
    """
    Route: clear_rate_limit() — rate_limit L85-95
    """
    if not _rate_limit_enabled():
        return

    rate_key = _rate_limit_key(key)
    db.execute(
        text("DELETE FROM rate_limits WHERE rate_key = :key AND action = :action"),
        {"key": rate_key, "action": action},
    )
    db.commit()
