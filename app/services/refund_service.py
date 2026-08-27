"""
WeCare — Refund Service

Mirrors helpers/refunds.
Policy calculations, snapshot synchronization, and refund record lifecycle.
Uses Decimal for all monetary arithmetic.
"""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session


def refund_statuses() -> List[str]:
    """
    Route: refund_statuses() — helpers/refunds L5-8
    """
    return ["pending", "approved", "rejected", "processed", "failed"]


def refund_format_money(value: Any) -> Decimal:
    """
    Route: refund_format_money() — helpers/refunds L144-147
    Rounds monetary value to 2 decimal places using Decimal.
    """
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def refund_iso(dt_val: Any) -> Optional[str]:
    """
    Route: refund_iso() — helpers/refunds L10-18
    Returns ISO 8601 string or None.
    """
    if not dt_val:
        return None
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            return dt_val.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        return dt_val.isoformat()
    if isinstance(dt_val, date):
        return datetime.combine(dt_val, datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    if isinstance(dt_val, str):
        val_str = dt_val.strip()
        if not val_str:
            return None
        try:
            dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            return dt.isoformat()
        except Exception:
            return val_str
    return None


def refund_policy_for_family_cancellation(hours_before_start: float) -> Tuple[Decimal, str]:
    """
    Route: refund_policy_for_family_cancellation() — helpers/refunds L20-31
    Tiered cancellation refund percentage:
      >= 24h: 100%, "Cancelled 24 or more hours before visit start"
      >= 12h: 50%, "Cancelled 12-24 hours before visit start"
      < 12h:  0%, "Cancelled less than 12 hours before visit start"
    """
    if hours_before_start >= 24.0:
        return Decimal("100.00"), "Cancelled 24 or more hours before visit start"
    if hours_before_start >= 12.0:
        return Decimal("50.00"), "Cancelled 12-24 hours before visit start"
    return Decimal("0.00"), "Cancelled less than 12 hours before visit start"


def successful_booking_payment_summary(db: Session, booking_id: int) -> Dict[str, Any]:
    """
    Route: successful_booking_payment_summary() — helpers/refunds L33-47
    Returns {'paid_amount': Decimal, 'payment_id': Optional[int]}
    """
    row = db.execute(
        text(
            "SELECT COALESCE(SUM(amount), 0) AS paid_amount, MIN(id) AS payment_id "
            "FROM payments "
            "WHERE booking_id = :bid AND status = 'success'"
        ),
        {"bid": int(booking_id)},
    ).fetchone()

    if not row:
        return {"paid_amount": Decimal("0.00"), "payment_id": None}

    m = row._mapping
    paid = refund_format_money(m["paid_amount"])
    payment_id = int(m["payment_id"]) if m["payment_id"] is not None else None

    return {
        "paid_amount": paid,
        "payment_id": payment_id,
    }


def sync_cancelled_booking_refund_snapshot(
    db: Session,
    booking_id: int,
    paid_amount: Decimal,
    refund_percentage: Decimal,
    refund_amount: Decimal,
) -> Dict[str, Any]:
    """
    Route: sync_cancelled_booking_refund_snapshot() — helpers/refunds L49-88
    Updates booking refund columns for a cancelled booking.
    """
    paid_amount = refund_format_money(paid_amount)
    refund_percentage = refund_format_money(refund_percentage)
    refund_amount = refund_format_money(refund_amount)
    refund_eligible = refund_amount > Decimal("0.00")
    refund_status = "pending" if refund_eligible else "not_applicable"

    db.execute(
        text(
            "UPDATE bookings "
            "SET paid_amount = :paid_amount, "
            "    refund_eligible = :refund_eligible, "
            "    refund_percentage = :refund_percentage, "
            "    refund_amount = :refund_amount, "
            "    refund_status = :refund_status, "
            "    updated_at = NOW() "
            "WHERE id = :booking_id AND status = 'cancelled'"
        ),
        {
            "paid_amount": str(paid_amount),
            "refund_eligible": 1 if refund_eligible else 0,
            "refund_percentage": str(refund_percentage),
            "refund_amount": str(refund_amount),
            "refund_status": refund_status,
            "booking_id": int(booking_id),
        },
    )

    return {
        "paid_amount": paid_amount,
        "refund_eligible": refund_eligible,
        "refund_percentage": refund_percentage,
        "refund_amount": refund_amount,
        "refund_status": refund_status,
    }


def create_booking_refund_if_payable(
    db: Session,
    booking: Dict[str, Any],
    paid_amount: Decimal,
    refund_percentage: Decimal,
    refund_amount: Decimal,
    payment_id: Optional[int],
    reason: Optional[str],
) -> Tuple[Optional[int], bool]:
    """
    Route: create_booking_refund_if_payable() — helpers/refunds L90-133
    Inserts a row into booking_refunds with FOR UPDATE lock if not already present.
    Returns (refund_id, created_bool).
    """
    paid_amount = refund_format_money(paid_amount)
    refund_amount = refund_format_money(refund_amount)
    refund_percentage = refund_format_money(refund_percentage)

    if paid_amount <= Decimal("0.00") or refund_amount <= Decimal("0.00"):
        return None, False

    booking_id = int(booking["id"])

    # SELECT ... FOR UPDATE to prevent duplicate refund records
    row = db.execute(
        text(
            "SELECT id FROM booking_refunds WHERE booking_id = :bid LIMIT 1 FOR UPDATE"
        ),
        {"bid": booking_id},
    ).fetchone()

    if row:
        return int(row[0]), False

    caretaker_user_id = booking.get("caretaker_user_id")
    c_uid = int(caretaker_user_id) if caretaker_user_id else None

    db.execute(
        text(
            "INSERT INTO booking_refunds "
            "(booking_id, family_user_id, caretaker_user_id, payment_id, "
            " paid_amount, refund_amount, refund_percentage, reason, status) "
            "VALUES (:booking_id, :family_user_id, :caretaker_user_id, :payment_id, "
            " :paid_amount, :refund_amount, :refund_percentage, :reason, 'pending')"
        ),
        {
            "booking_id": booking_id,
            "family_user_id": int(booking["family_user_id"]),
            "caretaker_user_id": c_uid,
            "payment_id": int(payment_id) if payment_id else None,
            "paid_amount": str(paid_amount),
            "refund_amount": str(refund_amount),
            "refund_percentage": str(refund_percentage),
            "reason": str(reason) if reason else None,
        },
    )

    result = db.execute(text("SELECT LAST_INSERT_ID() AS id")).mappings().first()
    refund_id = int(result["id"]) if result else None

    return refund_id, True


def refund_public_status(refund_id: Optional[int], refund_amount: Any) -> Optional[str]:
    """
    Route: refund_public_status() — helpers/refunds L135-142
    """
    amt = refund_format_money(refund_amount)
    if amt <= Decimal("0.00") or not refund_id:
        return None
    return "pending"


def refund_validate_status_filter(status: Any) -> Optional[str]:
    """
    Route: refund_validate_status_filter() — helpers/refunds L149-157
    """
    st = str(status or "").strip().lower()
    if not st or st == "all":
        return None
    return st if st in refund_statuses() else "__invalid__"
