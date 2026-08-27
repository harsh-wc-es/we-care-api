"""
payments + booking_refunds tables.
Schema source: schema.sql L558–586 (payments), L591–625 (booking_refunds)
"""

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import (
    PaymentMethod,
    PaymentStatus,
    PaymentType,
    PaymentVerificationStatus,
    RefundStatus,
)


class Payment(Base):
    __tablename__ = "payments"

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
    caretaker_user_id = Column(Integer, nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(
        Enum(PaymentMethod, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'cash'"),
    )
    transaction_id = Column(String(255), nullable=True)
    gateway_transaction_reference = Column(String(255), nullable=True)
    # longtext with JSON CHECK — schema.sql L567
    gateway_response_json = Column(LONGTEXT, nullable=True)
    status = Column(
        Enum(PaymentStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        server_default=text("'pending'"),
    )
    verification_status = Column(
        Enum(PaymentVerificationStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'pending'"),
    )
    paid_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    failure_reason = Column(String(255), nullable=True)
    idempotency_key = Column(String(191), nullable=True, unique=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    payment_type = Column(
        Enum(PaymentType, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        server_default=text("'advance'"),
    )
    total_amount = Column(Numeric(10, 2), nullable=True, server_default=text("0.00"))
    remaining_amount = Column(Numeric(10, 2), nullable=True, server_default=text("0.00"))

    __table_args__ = (
        Index("booking_id", "booking_id"),
        Index("family_user_id", "family_user_id"),
        Index("idx_payments_verification_status", "verification_status"),
        Index("idx_payments_gateway_reference", "gateway_transaction_reference"),
    )

    # ── Relationships ──
    booking = relationship("Booking", back_populates="payments")
    refund = relationship("BookingRefund", back_populates="payment", uselist=False)


class BookingRefund(Base):
    __tablename__ = "booking_refunds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
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
    payment_id = Column(
        Integer,
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    paid_amount = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    refund_amount = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    refund_percentage = Column(Numeric(5, 2), nullable=False, server_default=text("0.00"))
    refund_method = Column(String(50), nullable=True)
    refund_transaction_id = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(
        Enum(RefundStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'pending'"),
    )
    admin_note = Column(Text, nullable=True)
    processed_by_admin_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("idx_booking_refunds_booking", "booking_id"),
        Index("idx_booking_refunds_family", "family_user_id"),
        Index("idx_booking_refunds_caretaker", "caretaker_user_id"),
        Index("idx_booking_refunds_payment", "payment_id"),
        Index("idx_booking_refunds_status", "status"),
        Index("idx_booking_refunds_created_at", "created_at"),
        Index("fk_booking_refunds_admin", "processed_by_admin_id"),
    )

    # ── Relationships ──
    booking = relationship("Booking", back_populates="refunds")
    payment = relationship("Payment", back_populates="refund")
