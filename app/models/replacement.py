"""
replacement_tickets table.
Schema source: schema.sql L693–724
"""

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import ReplacementTicketStatus


class ReplacementTicket(Base):
    __tablename__ = "replacement_tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    complaint_id = Column(
        Integer,
        ForeignKey("complaints.id", ondelete="SET NULL"),
        nullable=True,
    )
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
    requested_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_caretaker_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    replacement_caretaker_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason = Column(Text, nullable=False)
    status = Column(
        Enum(ReplacementTicketStatus, values_callable=lambda e: [x.value for x in e]),
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
        Index("idx_replacements_complaint", "complaint_id"),
        Index("idx_replacements_booking", "booking_id"),
        Index("idx_replacements_status", "status"),
        Index("fk_replacements_family", "family_user_id"),
        Index("fk_replacements_requested_by", "requested_by_user_id"),
        Index("fk_replacements_original", "original_caretaker_user_id"),
        Index("fk_replacements_new", "replacement_caretaker_user_id"),
        Index("fk_replacements_resolved_by", "resolved_by"),
    )

    # ── Relationships ──
    complaint = relationship("Complaint", back_populates="replacement_tickets")
