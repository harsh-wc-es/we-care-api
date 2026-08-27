"""
caretaker_payouts + caretaker_payout_items tables.
Schema source: schema.sql L185–229
"""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import CaretakerPayoutStatus


class CaretakerPayout(Base):
    __tablename__ = "caretaker_payouts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    caretaker_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount = Column(Numeric(10, 2), nullable=False)
    gross_customer_amount = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    total_caretaker_earnings = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    total_platform_commission = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    week_start = Column(Date, nullable=True)
    week_end = Column(Date, nullable=True)
    status = Column(
        Enum(CaretakerPayoutStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'pending'"),
    )
    payment_method = Column(String(50), nullable=True)
    transaction_reference = Column(String(255), nullable=True)
    payment_reference = Column(String(255), nullable=True)
    admin_note = Column(Text, nullable=True)
    settled_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    settled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("idx_payout_caretaker", "caretaker_user_id"),
        Index("idx_payout_status", "status"),
        Index("fk_payout_settled_by", "settled_by"),
        Index("idx_payout_week", "week_start", "week_end"),
    )

    # ── Relationships ──
    items = relationship("CaretakerPayoutItem", back_populates="payout")


class CaretakerPayoutItem(Base):
    __tablename__ = "caretaker_payout_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    payout_id = Column(
        Integer,
        ForeignKey("caretaker_payouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # uniq_payout_booking
    )
    caretaker_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("idx_payout_items_payout", "payout_id"),
        Index("idx_payout_items_caretaker", "caretaker_user_id"),
    )

    # ── Relationships ──
    payout = relationship("CaretakerPayout", back_populates="items")
