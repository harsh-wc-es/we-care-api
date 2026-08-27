"""
users + pending_users tables.
Schema source: schema.sql L801–819 (users), L630–649 (pending_users)
"""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(100), nullable=False, unique=True)
    username = Column(String(100), nullable=False, unique=True)
    phone_number = Column(String(15), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    role = Column(
        Enum(UserRole, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    is_verified = Column(Integer, nullable=True, server_default=text("0"))
    profile_picture = Column(String(255), nullable=True)
    is_active = Column(Integer, nullable=True, server_default=text("1"))
    reset_token = Column(String(255), nullable=True)
    reset_token_expiry = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    # ── Relationships ──
    caretaker_profile = relationship(
        "CaretakerProfile", back_populates="user", uselist=False
    )
    family_profile = relationship(
        "FamilyProfile", back_populates="user", uselist=False
    )
    patient_details = relationship("PatientDetail", back_populates="family_user")
    tokens = relationship("Token", back_populates="user")
    documents = relationship("Document", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    device_tokens = relationship("NotificationDeviceToken", back_populates="user")
    otp_codes = relationship("OtpCode", back_populates="user")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user")
    sos_alerts = relationship("SosAlert", back_populates="user")
    support_tickets = relationship("SupportTicket", back_populates="user")

    # Bookings as family
    family_bookings = relationship(
        "Booking",
        back_populates="family_user",
        foreign_keys="Booking.family_user_id",
    )
    # Bookings as caretaker
    caretaker_bookings = relationship(
        "Booking",
        back_populates="caretaker_user",
        foreign_keys="Booking.caretaker_user_id",
    )


class PendingUser(Base):
    __tablename__ = "pending_users"

    # bigint(20) unsigned — differs from all other tables
    id = Column(
        BigInteger().with_variant(BigInteger, "mysql"),
        primary_key=True,
        autoincrement=True,
    )
    full_name = Column(String(150), nullable=True)
    username = Column(String(30), nullable=False, unique=True)
    email = Column(String(191), nullable=False, unique=True)
    phone_number = Column(String(20), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(
        Enum(UserRole, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    # longtext with JSON CHECK constraint
    registration_payload = Column(Text, nullable=True)
    otp_verified_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    # Relationship to OTP codes
    otp_codes = relationship("OtpCode", back_populates="pending_user")
