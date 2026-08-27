"""
support_tickets table.
Schema source: schema.sql L768–780
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
from app.models.enums import SupportTicketStatus


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(
        Enum(SupportTicketStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        server_default=text("'open'"),
    )
    admin_reply = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("user_id", "user_id"),
    )

    # ── Relationships ──
    user = relationship("User", back_populates="support_tickets")
