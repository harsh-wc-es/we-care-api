"""
visit_tracking + visit_notes + visit_activity_logs tables.
Schema source: schema.sql L824–883
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class VisitTracking(Base):
    __tablename__ = "visit_tracking"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    caretaker_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    check_in_time = Column(DateTime, nullable=True)
    check_out_time = Column(DateTime, nullable=True)
    check_in_lat = Column(String(50), nullable=True)
    check_in_lng = Column(String(50), nullable=True)
    check_out_lat = Column(String(50), nullable=True)
    check_out_lng = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("booking_id", "booking_id"),
        Index("caretaker_user_id", "caretaker_user_id"),
    )

    # ── Relationships ──
    booking = relationship("Booking", back_populates="visit_tracking")
    visit_notes = relationship("VisitNote", back_populates="visit")
    activity_logs = relationship("VisitActivityLog", back_populates="visit")


class VisitNote(Base):
    __tablename__ = "visit_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    visit_id = Column(
        Integer,
        ForeignKey("visit_tracking.id", ondelete="SET NULL"),
        nullable=True,
    )
    caretaker_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    note = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("idx_visit_notes_booking", "booking_id"),
        Index("idx_visit_notes_visit", "visit_id"),
        Index("idx_visit_notes_caretaker", "caretaker_user_id"),
    )

    # ── Relationships ──
    booking = relationship("Booking", back_populates="visit_notes")
    visit = relationship("VisitTracking", back_populates="visit_notes")


class VisitActivityLog(Base):
    __tablename__ = "visit_activity_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    visit_id = Column(
        Integer,
        ForeignKey("visit_tracking.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_role = Column(String(30), nullable=False)
    activity_type = Column(String(60), nullable=False)
    message = Column(String(255), nullable=False)
    metadata_ = Column("metadata", Text, nullable=True)  # 'metadata' is reserved
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("idx_visit_activity_booking", "booking_id"),
        Index("idx_visit_activity_visit", "visit_id"),
        Index("idx_visit_activity_actor", "actor_user_id"),
        Index("idx_visit_activity_type", "activity_type"),
    )

    # ── Relationships ──
    booking = relationship("Booking", back_populates="visit_activity_logs")
    visit = relationship("VisitTracking", back_populates="activity_logs")
