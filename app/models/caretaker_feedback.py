"""
caretaker_feedback table.
Schema source: schema.sql L325–343
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
from app.models.enums import FeedbackStatus


class CaretakerFeedback(Base):
    __tablename__ = "caretaker_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    caretaker_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating = Column(Integer, nullable=False)  # tinyint(4) in MySQL
    feedback = Column(Text, nullable=True)
    suggestion = Column(Text, nullable=True)
    is_anonymous = Column(Integer, nullable=False, server_default=text("0"))
    status = Column(
        Enum(FeedbackStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'pending'"),
    )
    admin_note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )
    reviewed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_caretaker_feedback_user", "caretaker_user_id"),
        Index("idx_caretaker_feedback_rating", "rating"),
        Index("idx_caretaker_feedback_status", "status"),
        Index("idx_caretaker_feedback_created_at", "created_at"),
    )
