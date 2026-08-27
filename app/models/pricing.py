"""
pricing_tiers + caregiver_pricing_history tables.
Schema source: schema.sql L654–671 (pricing_tiers), L301–320 (caregiver_pricing_history)
"""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)

from app.core.database import Base


class PricingTier(Base):
    __tablename__ = "pricing_tiers"

    # bigint(20) — differs from typical int(11) PK
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    skill_level = Column(String(30), nullable=True)
    customer_hourly_rate = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    caretaker_hourly_rate = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    platform_commission_hourly = Column(Numeric(10, 2), nullable=False, server_default=text("0.00"))
    commission_percentage = Column(Numeric(5, 2), nullable=False, server_default=text("0.00"))
    is_active = Column(Integer, nullable=False, server_default=text("1"))
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("idx_pricing_tiers_active", "is_active"),
        Index("idx_pricing_tiers_skill_level", "skill_level"),
    )


class CaregiverPricingHistory(Base):
    __tablename__ = "caregiver_pricing_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    caretaker_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_tier_id = Column(Integer, nullable=True)
    new_tier_id = Column(Integer, nullable=True)
    old_customer_rate_per_hour = Column(Numeric(10, 2), nullable=True)
    new_customer_rate_per_hour = Column(Numeric(10, 2), nullable=True)
    old_caregiver_rate_per_hour = Column(Numeric(10, 2), nullable=True)
    new_caregiver_rate_per_hour = Column(Numeric(10, 2), nullable=True)
    old_commission_percent = Column(Numeric(5, 2), nullable=True)
    new_commission_percent = Column(Numeric(5, 2), nullable=True)
    admin_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    admin_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("idx_caregiver_pricing_history_caretaker", "caretaker_user_id"),
        Index("idx_caregiver_pricing_history_admin", "admin_user_id"),
    )
