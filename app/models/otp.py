"""
otp_codes + otp_verifications tables.
Schema source: schema.sql L462–512
"""

from sqlalchemy import (
    BigInteger,
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
from app.models.enums import OtpPurpose, OtpVerificationPurpose


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    # bigint(20) unsigned — matches pending_users.id type
    pending_user_id = Column(
        BigInteger().with_variant(BigInteger, "mysql"),
        ForeignKey("pending_users.id", ondelete="CASCADE"),
        nullable=True,
    )
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=True,
    )
    email = Column(String(150), nullable=True)
    purpose = Column(
        Enum(OtpPurpose, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    otp_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    resend_available_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, server_default=text("0"))
    max_attempts = Column(Integer, nullable=False, server_default=text("5"))
    used_at = Column(DateTime, nullable=True)
    metadata_ = Column("metadata", Text, nullable=True)  # 'metadata' is reserved
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("idx_otp_user_purpose", "user_id", "purpose"),
        Index("idx_otp_booking_purpose", "booking_id", "purpose"),
        Index("idx_otp_email_purpose", "email", "purpose"),
        Index("idx_otp_expires_at", "expires_at"),
        Index("idx_otp_codes_pending_user", "pending_user_id"),
    )

    # ── Relationships ──
    user = relationship("User", back_populates="otp_codes")
    pending_user = relationship("PendingUser", back_populates="otp_codes")
    booking = relationship("Booking", back_populates="otp_codes")


class OtpVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    login_identifier = Column(String(190), nullable=False)
    purpose = Column(
        Enum(OtpVerificationPurpose, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    otp_hash = Column(String(255), nullable=False)
    attempts = Column(Integer, nullable=False, server_default=text("0"))
    max_attempts = Column(Integer, nullable=False, server_default=text("5"))
    expires_at = Column(DateTime, nullable=False)
    resend_available_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    used_at = Column(DateTime, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("idx_otp_verifications_user", "user_id"),
        Index("idx_otp_verifications_login_purpose", "login_identifier", "purpose"),
        Index("idx_otp_verifications_expires_at", "expires_at"),
    )
