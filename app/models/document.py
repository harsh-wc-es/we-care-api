"""
documents table.
Schema source: schema.sql L377–394
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
from app.models.enums import DocumentStatus


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type = Column(String(100), nullable=False)
    file_path = Column(String(255), nullable=False)
    original_file_name = Column(String(255), nullable=True)
    status = Column(
        Enum(DocumentStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
        server_default=text("'uploaded'"),
    )
    admin_note = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    reviewed_by_admin_id = Column(Integer, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    uploaded_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("user_id", "user_id"),
    )

    # ── Relationships ──
    user = relationship("User", back_populates="documents")
