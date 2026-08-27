"""
notifications + notification_device_tokens tables.
Schema source: schema.sql L421–457
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
from app.models.enums import AppType, DevicePlatform


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(60), nullable=False, server_default=text("'admin_announcement'"))
    related_type = Column(String(60), nullable=True)
    related_id = Column(Integer, nullable=True)
    metadata_ = Column("metadata", Text, nullable=True)  # 'metadata' is reserved
    is_read = Column(Integer, nullable=True, server_default=text("0"))
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("user_id", "user_id"),
        Index("idx_notifications_type", "type"),
        Index("idx_notifications_user_read", "user_id", "is_read", "id"),
    )

    # ── Relationships ──
    user = relationship("User", back_populates="notifications")


class NotificationDeviceToken(Base):
    __tablename__ = "notification_device_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_token = Column(String(255), nullable=False, unique=True)
    platform = Column(
        Enum(DevicePlatform, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    app_type = Column(
        Enum(AppType, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    is_active = Column(Integer, nullable=False, server_default=text("1"))
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("idx_device_tokens_user", "user_id"),
        Index("idx_device_tokens_active", "is_active"),
    )

    # ── Relationships ──
    user = relationship("User", back_populates="device_tokens")
