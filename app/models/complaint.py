"""
complaints table.
Schema source: schema.sql L348–372
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
from app.models.enums import ComplaintStatus


class Complaint(Base):
    __tablename__ = "complaints"

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
    subject = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    proof_file = Column(String(255), nullable=True)
    status = Column(
        Enum(ComplaintStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'open'"),
    )
    admin_note = Column(Text, nullable=True)
    resolved_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("idx_complaints_booking", "booking_id"),
        Index("idx_complaints_family", "family_user_id"),
        Index("idx_complaints_status", "status"),
        Index("fk_complaints_caretaker", "caretaker_user_id"),
        Index("fk_complaints_resolved_by", "resolved_by"),
    )

    # ── Relationships ──
    booking = relationship("Booking", back_populates="complaints")
    replacement_tickets = relationship("ReplacementTicket", back_populates="complaint")
