"""
tokens table.
Schema source: schema.sql L785–796
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Token(Base):
    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    is_blacklisted = Column(Integer, nullable=True, server_default=text("0"))
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("user_id", "user_id"),
    )

    # ── Relationships ──
    user = relationship("User", back_populates="tokens")
