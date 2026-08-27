"""
patient_details table.
Schema source: schema.sql L530–555

Note: UNIQUE constraint on family_user_id (one patient profile per family).
"""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import Gender


class PatientDetail(Base):
    __tablename__ = "patient_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    family_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # uq_patient_details_family_user_id
    )
    patient_name = Column(String(100), nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(
        Enum(Gender, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    medical_condition = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)
    medications = Column(Text, nullable=True)
    special_instructions = Column(Text, nullable=True)
    mobility_status = Column(String(100), nullable=True)
    care_type = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=True,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    # ── Relationships ──
    family_user = relationship("User", back_populates="patient_details")
    bookings = relationship("Booking", back_populates="patient")
