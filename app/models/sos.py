"""
sos_alerts table.
Schema source: schema.sql L749–763
"""

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import SosAlertStatus


class SosAlert(Base):
    __tablename__ = "sos_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
    )
    message = Column(Text, nullable=True)
    latitude = Column(String(50), nullable=True)
    longitude = Column(String(50), nullable=True)
    status = Column(
        Enum(SosAlertStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        server_default=text("'open'"),
    )
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("user_id", "user_id"),
        Index("booking_id", "booking_id"),
    )

    # ── Relationships ──
    user = relationship("User", back_populates="sos_alerts")
    booking = relationship("Booking", back_populates="sos_alerts")
