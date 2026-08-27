"""
rate_limits table.
Schema source: schema.sql L676–688
"""

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)

from app.core.database import Base


class RateLimit(Base):
    __tablename__ = "rate_limits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rate_key = Column(String(190), nullable=False)
    action = Column(String(80), nullable=False)
    attempts = Column(Integer, nullable=False, server_default=text("1"))
    window_start = Column(DateTime, nullable=False)
    blocked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("rate_key", "action", name="uq_rate_key_action"),
        Index("idx_rate_blocked_until", "blocked_until"),
    )
