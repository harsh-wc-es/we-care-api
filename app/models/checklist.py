"""
booking_checklist_tasks table.
Schema source: schema.sql L63–84
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
from app.models.enums import ChecklistTaskStatus


class BookingChecklistTask(Base):
    __tablename__ = "booking_checklist_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    family_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    caretaker_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        Enum(ChecklistTaskStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'pending'"),
    )
    completed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("idx_tasks_booking", "booking_id"),
        Index("idx_tasks_family", "family_user_id"),
        Index("idx_tasks_caretaker", "caretaker_user_id"),
        Index("fk_tasks_completed_by", "completed_by"),
    )

    # ── Relationships ──
    booking = relationship("Booking", back_populates="checklist_tasks")
