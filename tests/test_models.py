"""
STEP 15c: Test that all 32 models are registered and have correct table names.
"""

from app.core.database import Base
import app.models  # noqa: F401 — register all models


EXPECTED_TABLES = [
    "admin_audit_logs",
    "booking_checklist_tasks",
    "booking_refunds",
    "bookings",
    "caregiver_pricing_history",
    "caretaker_availability",
    "caretaker_feedback",
    "caretaker_payout_items",
    "caretaker_payouts",
    "caretaker_profiles",
    "complaints",
    "documents",
    "family_profiles",
    "notification_device_tokens",
    "notifications",
    "otp_codes",
    "otp_verifications",
    "password_reset_tokens",
    "patient_details",
    "payments",
    "pending_users",
    "pricing_tiers",
    "rate_limits",
    "replacement_tickets",
    "reviews",
    "sos_alerts",
    "support_tickets",
    "tokens",
    "users",
    "visit_activity_logs",
    "visit_notes",
    "visit_tracking",
]


def test_all_32_tables_registered():
    """All 32 tables from schema.sql must be registered in Base.metadata."""
    registered = sorted(Base.metadata.tables.keys())
    assert len(registered) == 32, f"Expected 32 tables, got {len(registered)}: {registered}"


def test_expected_table_names():
    """Table names must match schema.sql exactly."""
    registered = set(Base.metadata.tables.keys())
    for table_name in EXPECTED_TABLES:
        assert table_name in registered, f"Missing table: {table_name}"


def test_bookings_has_53_columns():
    """Bookings is the heaviest table with 53 columns (schema.sql L90-142)."""
    table = Base.metadata.tables["bookings"]
    col_count = len(table.columns)
    assert col_count == 53, f"Expected 53 columns, got {col_count}"


def test_caretaker_profiles_has_48_columns():
    """CaretakerProfile has 48 columns including availability system."""
    table = Base.metadata.tables["caretaker_profiles"]
    col_count = len(table.columns)
    assert col_count == 48, f"Expected 48 columns, got {col_count}"


def test_pending_users_pk_is_biginteger():
    """pending_users.id must be bigint(20) unsigned — different from int(11)."""
    from app.models.user import PendingUser
    pk_col = PendingUser.__table__.c.id
    type_name = type(pk_col.type).__name__
    assert "BigInteger" in type_name or "BIGINT" in str(pk_col.type).upper(), (
        f"Expected BigInteger, got {type_name}"
    )


def test_pricing_tiers_pk_is_biginteger():
    """pricing_tiers.id must be bigint(20) — different from int(11)."""
    from app.models.pricing import PricingTier
    pk_col = PricingTier.__table__.c.id
    type_name = type(pk_col.type).__name__
    assert "BigInteger" in type_name or "BIGINT" in str(pk_col.type).upper(), (
        f"Expected BigInteger, got {type_name}"
    )


def test_booking_refunds_unique_booking_id():
    """booking_refunds.booking_id must be unique (one refund per booking)."""
    table = Base.metadata.tables["booking_refunds"]
    col = table.c.booking_id
    assert col.unique is True, "booking_refunds.booking_id should be unique"


def test_patient_details_unique_family_user_id():
    """patient_details.family_user_id must be unique (one patient per family)."""
    table = Base.metadata.tables["patient_details"]
    col = table.c.family_user_id
    assert col.unique is True, "patient_details.family_user_id should be unique"


def test_all_enums_are_str_enums():
    """All enum classes must inherit from str for JSON serialization."""
    from app.models import enums
    import enum as enum_module
    import inspect

    for name, obj in inspect.getmembers(enums, inspect.isclass):
        if issubclass(obj, enum_module.Enum) and obj is not enum_module.Enum:
            assert issubclass(obj, str), f"{name} must inherit from str"
