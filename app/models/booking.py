"""
bookings table — 51 columns.
Schema source: schema.sql L89–164
"""

from sqlalchemy import (
    BigInteger,
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
    Time,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import (
    BookingPaymentStatus,
    BookingRefundStatus,
    BookingStatus,
    PayoutStatus,
    RequestPriority,
)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
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
    patient_id = Column(
        Integer,
        ForeignKey("patient_details.id", ondelete="SET NULL"),
        nullable=True,
    )

    service_type = Column(String(100), nullable=False)
    booking_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    address = Column(Text, nullable=False)
    location_latitude = Column(Numeric(10, 7), nullable=True)
    location_longitude = Column(Numeric(10, 7), nullable=True)
    notes = Column(Text, nullable=True)

    request_priority = Column(
        Enum(RequestPriority, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'normal'"),
    )
    status = Column(
        Enum(BookingStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        server_default=text("'pending'"),
    )

    # ── Cancellation fields ──
    cancelled_by = Column(String(30), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # ── Decline fields ──
    decline_reason_code = Column(String(50), nullable=True)
    decline_reason_label = Column(String(120), nullable=True)
    decline_note = Column(Text, nullable=True)

    responded_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by_user_id = Column(Integer, nullable=True)
    cancelled_by_role = Column(String(30), nullable=True)
    cancel_reason_code = Column(String(50), nullable=True)
    cancel_reason_label = Column(String(100), nullable=True)
    cancel_note = Column(Text, nullable=True)

    # ── Refund fields ──
    refund_percentage = Column(Numeric(5, 2), nullable=False, server_default=text("0.00"))
    refund_amount = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    cancellation_fee = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    refund_status = Column(
        Enum(BookingRefundStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'not_applicable'"),
    )
    refund_eligible = Column(Integer, nullable=False, server_default=text("0"))

    # ── Pricing fields ──
    total_amount = Column(Numeric(10, 2), nullable=True, server_default=text("0.00"))
    pricing_tier_id = Column(BigInteger, nullable=True)
    pricing_tier = Column(String(30), nullable=True)
    skill_level = Column(String(30), nullable=True)
    customer_hourly_rate = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    caretaker_hourly_rate = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    platform_commission_hourly = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    total_customer_amount = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    caretaker_earning_amount = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    platform_commission_amount = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    care_points_earned = Column(Integer, nullable=False, server_default=text("0"))
    total_hours = Column(Numeric(6, 2), nullable=False, server_default=text("0.00"))

    payment_status = Column(
        Enum(BookingPaymentStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        server_default=text("'pending'"),
    )

    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )
    completed_at = Column(DateTime, nullable=True)

    # ── Payout fields ──
    payout_status = Column(
        Enum(PayoutStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'not_applicable'"),
    )
    payout_hold_until = Column(DateTime, nullable=True)
    payout_paid_at = Column(DateTime, nullable=True)
    payout_id = Column(Integer, nullable=True)
    paid_amount = Column(Numeric(10, 2), nullable=True, server_default=text("0.00"))
    remaining_amount = Column(Numeric(10, 2), nullable=True, server_default=text("0.00"))

    # ── Indexes (schema.sql L144–160) ──
    __table_args__ = (
        Index("family_user_id", "family_user_id"),
        Index("caretaker_user_id", "caretaker_user_id"),
        Index("patient_id", "patient_id"),
        Index("idx_booking_payout_status", "payout_status"),
        Index("idx_booking_payout_hold_until", "payout_hold_until"),
        Index("idx_booking_completed_at", "completed_at"),
        Index("idx_booking_payout_id", "payout_id"),
        Index("idx_booking_pricing_tier", "pricing_tier"),
        Index("idx_booking_caretaker_earning", "caretaker_earning_amount"),
        Index("idx_booking_pricing_tier_id", "pricing_tier_id"),
        Index("idx_booking_skill_level", "skill_level"),
        Index("idx_booking_cancelled_at", "cancelled_at"),
        Index("idx_bookings_cancel_reason_code", "cancel_reason_code"),
        Index("idx_bookings_refund_status", "refund_status"),
        Index("idx_bookings_cancelled_by_user", "cancelled_by_user_id"),
        Index("idx_bookings_request_priority", "request_priority"),
        Index("idx_bookings_responded_at", "responded_at"),
    )

    # ── Relationships ──
    family_user = relationship(
        "User",
        back_populates="family_bookings",
        foreign_keys=[family_user_id],
    )
    caretaker_user = relationship(
        "User",
        back_populates="caretaker_bookings",
        foreign_keys=[caretaker_user_id],
    )
    patient = relationship("PatientDetail", back_populates="bookings")
    visit_tracking = relationship("VisitTracking", back_populates="booking")
    visit_notes = relationship("VisitNote", back_populates="booking")
    visit_activity_logs = relationship("VisitActivityLog", back_populates="booking")
    checklist_tasks = relationship("BookingChecklistTask", back_populates="booking")
    payments = relationship("Payment", back_populates="booking")
    refunds = relationship("BookingRefund", back_populates="booking")
    complaints = relationship("Complaint", back_populates="booking")
    reviews = relationship("Review", back_populates="booking")
    otp_codes = relationship("OtpCode", back_populates="booking")
    sos_alerts = relationship("SosAlert", back_populates="booking")
