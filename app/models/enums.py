"""
WeCare FastAPI — All Enum Definitions

Every enum is verified against schema.sql exact values.
Python enum .value matches the MySQL ENUM string exactly.
"""

import enum


# ── users.role / pending_users.role ──
class UserRole(str, enum.Enum):
    FAMILY = "family"
    CARETAKER = "caretaker"
    ADMIN = "admin"


# ── users/family_profiles/patient_details/caretaker_profiles gender ──
class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


# ── bookings.status ──
class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DECLINED = "declined"
    CANCELLED = "cancelled"


# ── bookings.request_priority ──
class RequestPriority(str, enum.Enum):
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# ── bookings.payment_status ──
class BookingPaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


# ── bookings.refund_status ──
class BookingRefundStatus(str, enum.Enum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


# ── bookings.payout_status ──
class PayoutStatus(str, enum.Enum):
    NOT_APPLICABLE = "not_applicable"
    HOLD = "hold"
    READY_FOR_PAYOUT = "ready_for_payout"
    DISPUTED = "disputed"
    PAID = "paid"


# ── caretaker_profiles.availability_status ──
class AvailabilityStatus(str, enum.Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"


# ── caretaker_profiles.verification_status ──
class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_RESUBMISSION = "needs_resubmission"
    BANNED = "banned"


# ── caretaker_profiles.availability_reason ──
class AvailabilityReason(str, enum.Enum):
    MANUAL_OFF = "manual_off"
    MANUAL_ON = "manual_on"
    ON_VISIT = "on_visit"
    INACTIVE = "inactive"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    ADMIN_FORCED_OFF = "admin_forced_off"
    ADMIN_FORCED_ON = "admin_forced_on"


# ── caretaker_profiles.availability_changed_by ──
class AvailabilityChangedBy(str, enum.Enum):
    CARETAKER = "caretaker"
    SYSTEM = "system"
    ADMIN = "admin"


# ── caretaker_payouts.status ──
class CaretakerPayoutStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"


# ── caretaker_feedback.status ──
class FeedbackStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    ARCHIVED = "archived"


# ── complaints.status ──
class ComplaintStatus(str, enum.Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    REJECTED = "rejected"


# ── documents.status ──
class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REUPLOADED = "reuploaded"


# ── notification_device_tokens.platform ──
class DevicePlatform(str, enum.Enum):
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"


# ── notification_device_tokens.app_type ──
class AppType(str, enum.Enum):
    FAMILY = "family"
    CARETAKER = "caretaker"
    ADMIN = "admin"


# ── otp_codes.purpose ──
class OtpPurpose(str, enum.Enum):
    REGISTER_EMAIL = "register_email"
    LOGIN = "login"
    PASSWORD_RESET = "password_reset"
    VISIT_START = "visit_start"
    PASSWORD_RESET_AUTHENTICATED = "password_reset_authenticated"


# ── otp_verifications.purpose ──
class OtpVerificationPurpose(str, enum.Enum):
    FORGOT_PASSWORD = "forgot_password"


# ── payments.payment_method ──
class PaymentMethod(str, enum.Enum):
    CARD = "card"
    UPI = "upi"
    NETBANKING = "netbanking"
    WALLET = "wallet"
    CASH = "cash"
    INSURANCE = "insurance"
    OTHER = "other"


# ── payments.status ──
class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


# ── payments.verification_status ──
class PaymentVerificationStatus(str, enum.Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


# ── payments.payment_type ──
class PaymentType(str, enum.Enum):
    ADVANCE = "advance"
    REMAINING = "remaining"
    FULL = "full"


# ── booking_checklist_tasks.status ──
class ChecklistTaskStatus(str, enum.Enum):
    PENDING = "pending"
    ONGOING = "ongoing"
    COMPLETED = "completed"


# ── booking_refunds.status ──
class RefundStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"
    FAILED = "failed"


# ── replacement_tickets.status ──
class ReplacementTicketStatus(str, enum.Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


# ── sos_alerts.status ──
class SosAlertStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"


# ── support_tickets.status ──
class SupportTicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
