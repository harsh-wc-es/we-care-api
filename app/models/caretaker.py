"""
caretaker_profiles (48 cols) + caretaker_availability tables.
Schema source: schema.sql L234–296, L169–180
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
    AvailabilityChangedBy,
    AvailabilityReason,
    AvailabilityStatus,
    Gender,
    VerificationStatus,
)


class CaretakerProfile(Base):
    __tablename__ = "caretaker_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    full_name = Column(String(100), nullable=True)
    gender = Column(
        Enum(Gender, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
    )
    date_of_birth = Column(Date, nullable=True)
    experience_years = Column(Integer, nullable=True, server_default=text("0"))
    qualification = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    hourly_rate = Column(Numeric(10, 2), nullable=True, server_default=text("0.00"))

    # ── Pricing tier fields ──
    pricing_tier_id = Column(BigInteger, nullable=True)
    pricing_tier = Column(String(30), nullable=True)
    skill_level = Column(String(30), nullable=True)
    customer_hourly_rate = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    caretaker_hourly_rate = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    platform_commission_hourly = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    commission_percentage = Column(Numeric(5, 2), nullable=False, server_default=text("0.00"))
    payout_priority = Column(Integer, nullable=False, server_default=text("0"))
    pricing_override_enabled = Column(Integer, nullable=False, server_default=text("0"))

    # ── Address fields ──
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)

    # ── Status fields ──
    availability_status = Column(
        Enum(AvailabilityStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        server_default=text("'offline'"),
    )
    verification_status = Column(
        Enum(VerificationStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        server_default=text("'pending'"),
    )
    is_banned = Column(Integer, nullable=False, server_default=text("0"))
    is_available = Column(Integer, nullable=False, server_default=text("0"))

    # ── Availability system (hardened — helpers/availability) ──
    manual_availability_enabled = Column(Integer, nullable=False, server_default=text("0"))
    availability_reason = Column(
        Enum(AvailabilityReason, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'manual_off'"),
    )
    availability_locked_by_admin = Column(Integer, nullable=False, server_default=text("0"))
    availability_locked_note = Column(Text, nullable=True)
    availability_locked_at = Column(DateTime, nullable=True)
    availability_locked_by_user_id = Column(BigInteger, nullable=True)
    availability_auto_restored_at = Column(DateTime, nullable=True)
    availability_changed_at = Column(DateTime, nullable=True)
    availability_changed_by = Column(
        Enum(AvailabilityChangedBy, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'caretaker'"),
    )
    # Optimistic locking version — incremented on every availability change
    availability_version = Column(Integer, nullable=False, server_default=text("1"))
    availability_updated_at = Column(DateTime, nullable=True)
    last_active_at = Column(DateTime, nullable=True)

    # ── Rating fields ──
    rating = Column(Numeric(3, 2), nullable=True, server_default=text("0.00"))
    total_reviews = Column(Integer, nullable=True, server_default=text("0"))

    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    # ── Admin action fields ──
    rejection_reason = Column(Text, nullable=True)
    ban_reason = Column(Text, nullable=True)
    banned_at = Column(DateTime, nullable=True)
    banned_by_admin_id = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by_admin_id = Column(Integer, nullable=True)

    # ── Indexes (schema.sql L284–294) ──
    __table_args__ = (
        Index("user_id", "user_id"),
        Index("idx_caretaker_pricing_tier", "pricing_tier"),
        Index("idx_caretaker_skill_level", "skill_level"),
        Index("idx_caretaker_pricing_tier_id", "pricing_tier_id"),
        Index("idx_caretaker_pricing_override", "pricing_override_enabled"),
        Index("idx_caretaker_is_available", "is_available"),
        Index("idx_caretaker_availability_updated_at", "availability_updated_at"),
        Index("idx_caretaker_availability_reason", "availability_reason"),
        Index("idx_caretaker_last_active_at", "last_active_at"),
        Index("idx_caretaker_admin_locked", "availability_locked_by_admin"),
        Index("idx_caretaker_verification_status", "verification_status"),
    )

    # ── Relationships ──
    user = relationship("User", back_populates="caretaker_profile")


class CaretakerAvailability(Base):
    __tablename__ = "caretaker_availability"

    id = Column(Integer, primary_key=True, autoincrement=True)
    caretaker_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    available_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_available = Column(Integer, nullable=True, server_default=text("1"))
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("caretaker_user_id", "caretaker_user_id"),
    )
