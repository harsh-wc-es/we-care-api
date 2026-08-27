"""
WeCare SQLAlchemy Models — Central Import Registry

Import all models here so that Alembic and Base.metadata
can discover every table for autogenerate migrations.
"""

# noqa: F401 — imports are used for model registration
from app.models.audit import AdminAuditLog
from app.models.booking import Booking
from app.models.caretaker import CaretakerAvailability, CaretakerProfile
from app.models.caretaker_feedback import CaretakerFeedback
from app.models.checklist import BookingChecklistTask
from app.models.complaint import Complaint
from app.models.document import Document
from app.models.family import FamilyProfile
from app.models.notification import Notification, NotificationDeviceToken
from app.models.otp import OtpCode, OtpVerification
from app.models.password_reset import PasswordResetToken
from app.models.patient import PatientDetail
from app.models.payment import BookingRefund, Payment
from app.models.payout import CaretakerPayout, CaretakerPayoutItem
from app.models.pricing import CaregiverPricingHistory, PricingTier
from app.models.rate_limit import RateLimit
from app.models.replacement import ReplacementTicket
from app.models.review import Review
from app.models.sos import SosAlert
from app.models.support import SupportTicket
from app.models.token import Token
from app.models.user import PendingUser, User
from app.models.visit import VisitActivityLog, VisitNote, VisitTracking

__all__ = [
    "AdminAuditLog",
    "Booking",
    "BookingChecklistTask",
    "BookingRefund",
    "CaretakerAvailability",
    "CaretakerFeedback",
    "CaretakerPayout",
    "CaretakerPayoutItem",
    "CaretakerProfile",
    "CaregiverPricingHistory",
    "Complaint",
    "Document",
    "FamilyProfile",
    "Notification",
    "NotificationDeviceToken",
    "OtpCode",
    "OtpVerification",
    "PasswordResetToken",
    "PatientDetail",
    "Payment",
    "PendingUser",
    "PricingTier",
    "RateLimit",
    "ReplacementTicket",
    "Review",
    "SosAlert",
    "SupportTicket",
    "Token",
    "User",
    "VisitActivityLog",
    "VisitNote",
    "VisitTracking",
]
