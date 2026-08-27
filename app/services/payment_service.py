"""
WeCare — Payment & Refund Service (Part 10)

Migrates helpers/payment + helpers/refunds + api/v1/payment/*

CRITICAL: Payment transaction semantics must exactly mirror - SELECT FOR UPDATE to lock booking row
- Validate eligibility AFTER obtaining the lock
- Idempotency check within the transaction
- Insert payment row
- Update booking amounts atomically
- Commit or rollback on any failure

Refund endpoints in Part 10 are READ-ONLY.
Do NOT implement refund creation, approval, rejection, or processing.
"""

import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException

logger = logging.getLogger(__name__)


# ============================================================
# Payment helper functions — exact parity
# Migrated from helpers/payment
# ============================================================


PAYMENT_ALLOWED_METHODS = ["card", "upi", "netbanking", "wallet", "cash", "insurance", "other"]


def normalize_payment_method(method: Any) -> str:
    """Route: normalize_payment_method() — helpers/payment L8-11"""
    return str(method or "").strip().lower()


def validate_payment_method(method: Any) -> Dict[str, Any]:
    """Route: validate_payment_method() — helpers/payment L13-38"""
    method = normalize_payment_method(method)

    if method == "":
        return {
            "valid": False,
            "method": method,
            "errors": {"payment_method": ["Payment method is required"]},
        }

    if method not in PAYMENT_ALLOWED_METHODS:
        return {
            "valid": False,
            "method": method,
            "errors": {
                "payment_method": [
                    "Payment method must be one of: " + ", ".join(PAYMENT_ALLOWED_METHODS)
                ]
            },
        }

    return {"valid": True, "method": method, "errors": {}}


def payment_customer_total(booking: Dict[str, Any]) -> float:
    """
    Route: payment_customer_total() — helpers/payment L40-48

    Exact logic:
        $snapshotTotal = (float)($booking["total_customer_amount"] ?? 0);
        if ($snapshotTotal > 0) { return round($snapshotTotal, 2); }
        return round((float)($booking["total_amount"] ?? 0), 2);

    DO NOT independently reimplement this.
    This preserves the exact fallback, null, zero, and numeric-conversion behavior.
    """
    snapshot_total = float(booking.get("total_customer_amount") or 0)
    if snapshot_total > 0:
        return round(snapshot_total, 2)

    return round(float(booking.get("total_amount") or 0), 2)


def payment_validate_money_state(booking: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Route: payment_validate_money_state() — helpers/payment L50-68"""
    total = payment_customer_total(booking)
    paid = round(float(booking.get("paid_amount") or 0), 2)

    if total <= 0:
        return {
            "status": 409,
            "message": "Booking payment amount is invalid",
            "errors": {"booking_id": ["Booking does not have a valid customer payment amount"]},
        }

    if paid < 0 or paid > total:
        return {
            "status": 409,
            "message": "Booking payment state is inconsistent",
            "errors": {"booking_id": ["Booking has an inconsistent paid amount"]},
        }

    return None


def payment_blocked_status_error(booking: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Route: payment_blocked_status_error() — helpers/payment L70-83"""
    booking_status = str(booking.get("status") or "").lower()
    payment_status = str(booking.get("payment_status") or "").lower()

    blocked_booking = ["cancelled", "declined", "disputed", "refunded"]
    blocked_payment = ["refunded", "failed"]

    if booking_status in blocked_booking or payment_status in blocked_payment:
        return {
            "status": 409,
            "message": "Payment is not allowed for this booking",
            "errors": {
                "status": [
                    "Payment is blocked for cancelled, declined, disputed, refunded, or failed bookings"
                ]
            },
        }

    return None


def validate_advance_payment_eligibility(booking: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Route: validate_advance_payment_eligibility() — helpers/payment L85-104"""
    state_error = payment_validate_money_state(booking)
    if state_error:
        return state_error

    blocked_error = payment_blocked_status_error(booking)
    if blocked_error:
        return blocked_error

    if float(booking.get("paid_amount") or 0) > 0:
        return {
            "status": 409,
            "message": "Advance payment already done",
            "errors": {"booking_id": ["Advance payment has already been completed for this booking"]},
        }

    return None


def validate_remaining_payment_eligibility(booking: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Route: validate_remaining_payment_eligibility() — helpers/payment L106-143"""
    state_error = payment_validate_money_state(booking)
    if state_error:
        return state_error

    blocked_error = payment_blocked_status_error(booking)
    if blocked_error:
        return blocked_error

    allowed_statuses = ["confirmed", "caretaker_arrived", "in_progress", "completed"]
    booking_status = str(booking.get("status") or "").lower()
    if booking_status not in allowed_statuses:
        return {
            "status": 409,
            "message": "Remaining payment is not allowed yet",
            "errors": {
                "status": [
                    "Remaining payment is allowed only after booking is confirmed, caretaker arrived, in progress, or completed"
                ]
            },
        }

    total = payment_customer_total(booking)
    paid = round(float(booking.get("paid_amount") or 0), 2)
    remaining = round(max(0, total - paid), 2)

    if paid <= 0:
        return {
            "status": 409,
            "message": "Advance payment required first",
            "errors": {"booking_id": ["Advance payment must be completed before remaining payment"]},
        }

    if remaining <= 0 or str(booking.get("payment_status") or "").lower() == "paid":
        return {
            "status": 409,
            "message": "No remaining payment found",
            "errors": {"booking_id": ["Remaining payment has already been completed for this booking"]},
        }

    return None


def payment_idempotency_key(data: Dict[str, Any], request_headers: Optional[Dict[str, str]] = None) -> Optional[str]:
    """
    Route: payment_idempotency_key() — helpers/payment L145-149

    Extracts from body idempotency_key or HTTP_IDEMPOTENCY_KEY header.
    Truncates to 191 chars. Returns None if empty.
    """
    key = str(data.get("idempotency_key") or "").strip()
    if not key and request_headers:
        key = str(request_headers.get("idempotency-key") or "").strip()
    return key[:191] if key else None


# ============================================================
# Refund helper functions — exact parity
# Migrated from helpers/refunds (read-only portions)
# ============================================================

REFUND_STATUSES = ["pending", "approved", "rejected", "processed", "failed"]


def refund_iso(dt_value: Any) -> Optional[str]:
    """Route: refund_iso() — helpers/refunds L10-18"""
    if not dt_value:
        return None
    if isinstance(dt_value, datetime):
        return dt_value.isoformat()
    try:
        parsed = datetime.fromisoformat(str(dt_value))
        return parsed.isoformat()
    except (ValueError, TypeError):
        return None


def refund_format_money(value: Any) -> float:
    """Route: refund_format_money() — helpers/refunds L144-147"""
    return round(float(value or 0), 2)


def refund_validate_status_filter(status: Any) -> Optional[str]:
    """
    Route: refund_validate_status_filter() — helpers/refunds L149-157

    Returns: None (no filter), valid status string, or "__invalid__"
    """
    status = str(status or "").strip().lower()
    if status == "" or status == "all":
        return None
    return status if status in REFUND_STATUSES else "__invalid__"


# ============================================================
# Payment service functions
# ============================================================


def pay_advance(
    db: Session,
    family_user: Dict[str, Any],
    booking_id: Any,
    payment_method: Any,
    transaction_id: Optional[str],
    idempotency_key: Optional[str],
) -> Dict[str, Any]:
    """
    Route: api/v1/payment/pay_advance

    CRITICAL: Transaction with SELECT FOR UPDATE → validate → insert → update → commit.
    """
    # ── Input validation ──
    errors: Dict[str, List[str]] = {}

    try:
        booking_id_int = int(booking_id)
        if booking_id_int <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errors["booking_id"] = ["Valid booking id is required"]

    method_validation = validate_payment_method(payment_method)
    if not method_validation["valid"]:
        errors.update(method_validation["errors"])

    if errors:
        raise APIException(message="Validation failed", errors=errors, status_code=400)

    booking_id_int = int(booking_id)
    payment_method_norm = method_validation["method"]
    user_id = int(family_user["id"])

    # ── Transaction — exact semantics ──
    connection = db.connection()
    try:
        # Lock booking row (SELECT ... FOR UPDATE)
        row = db.execute(
            text(
                "SELECT id, family_user_id, caretaker_user_id, status, total_amount, total_customer_amount, "
                "paid_amount, remaining_amount, payment_status "
                "FROM bookings "
                "WHERE id = :bid AND family_user_id = :fid "
                "FOR UPDATE"
            ),
            {"bid": booking_id_int, "fid": user_id},
        ).fetchone()

        if not row:
            raise APIException(message="Booking not found", status_code=404)

        booking = dict(row._mapping)

        # Validate eligibility (after lock, as does)
        eligibility_error = validate_advance_payment_eligibility(booking)
        if eligibility_error:
            raise APIException(
                message=eligibility_error["message"],
                errors=eligibility_error.get("errors"),
                status_code=eligibility_error["status"],
            )

        # Idempotency check (within transaction)
        if idempotency_key is not None:
            dup = db.execute(
                text("SELECT id FROM payments WHERE idempotency_key = :key LIMIT 1"),
                {"key": idempotency_key},
            ).fetchone()
            if dup:
                raise APIException(
                    message="Duplicate payment request",
                    errors={"idempotency_key": ["This payment request has already been processed"]},
                    status_code=409,
                )

        # Calculate amounts
        total_amount = payment_customer_total(booking)
        advance_amount = round(total_amount * 0.5, 2)
        remaining_amount = round(total_amount - advance_amount, 2)
        p_status = "pending" if remaining_amount > 0 else "paid"
        verification = "not_required" if payment_method_norm == "cash" else "verified"

        # Insert payment row
        result = db.execute(
            text(
                "INSERT INTO payments "
                "(booking_id, family_user_id, caretaker_user_id, amount, payment_method, "
                "transaction_id, status, paid_at, payment_type, total_amount, remaining_amount, "
                "gateway_transaction_reference, verification_status, verified_at, idempotency_key) "
                "VALUES (:booking_id, :family_user_id, :caretaker_user_id, :amount, :payment_method, "
                ":transaction_id, 'success', NOW(), 'advance', :total_amount, :remaining_amount, "
                ":gateway_ref, :verification_status, NOW(), :idempotency_key)"
            ),
            {
                "booking_id": booking_id_int,
                "family_user_id": user_id,
                "caretaker_user_id": booking.get("caretaker_user_id"),
                "amount": advance_amount,
                "payment_method": payment_method_norm,
                "transaction_id": transaction_id,
                "total_amount": total_amount,
                "remaining_amount": remaining_amount,
                "gateway_ref": transaction_id,
                "verification_status": verification,
                "idempotency_key": idempotency_key,
            },
        )
        payment_id = result.lastrowid

        # Update booking amounts
        db.execute(
            text(
                "UPDATE bookings "
                "SET paid_amount = :paid, remaining_amount = :remaining, payment_status = :ps "
                "WHERE id = :bid"
            ),
            {
                "paid": advance_amount,
                "remaining": remaining_amount,
                "ps": p_status,
                "bid": booking_id_int,
            },
        )

        db.commit()

    except APIException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Advance payment failed: {e}")
        raise APIException(message="Advance payment failed", status_code=500)

    return {
        "payment_id": payment_id,
        "booking_id": booking_id_int,
        "payment_type": "advance",
        "total_amount": total_amount,
        "advance_paid": advance_amount,
        "remaining_amount": remaining_amount,
        "payment_status": p_status,
        "payment_method": payment_method_norm,
        "verification_status": verification,
    }


def pay_remaining(
    db: Session,
    family_user: Dict[str, Any],
    booking_id: Any,
    payment_method: Any,
    transaction_id: Optional[str],
    idempotency_key: Optional[str],
) -> Dict[str, Any]:
    """
    Route: api/v1/payment/pay_remaining

    CRITICAL: Transaction with SELECT FOR UPDATE → validate → insert → update → commit.
    """
    # ── Input validation ──
    errors: Dict[str, List[str]] = {}

    try:
        booking_id_int = int(booking_id)
        if booking_id_int <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errors["booking_id"] = ["Valid booking id is required"]

    method_validation = validate_payment_method(payment_method)
    if not method_validation["valid"]:
        errors.update(method_validation["errors"])

    if errors:
        raise APIException(message="Validation failed", errors=errors, status_code=400)

    booking_id_int = int(booking_id)
    payment_method_norm = method_validation["method"]
    user_id = int(family_user["id"])

    # ── Transaction — exact semantics ──
    connection = db.connection()
    try:
        # Lock booking row
        row = db.execute(
            text(
                "SELECT id, family_user_id, caretaker_user_id, status, total_amount, total_customer_amount, "
                "paid_amount, remaining_amount, payment_status "
                "FROM bookings "
                "WHERE id = :bid AND family_user_id = :fid "
                "FOR UPDATE"
            ),
            {"bid": booking_id_int, "fid": user_id},
        ).fetchone()

        if not row:
            raise APIException(message="Booking not found", status_code=404)

        booking = dict(row._mapping)

        # Validate eligibility (after lock)
        eligibility_error = validate_remaining_payment_eligibility(booking)
        if eligibility_error:
            raise APIException(
                message=eligibility_error["message"],
                errors=eligibility_error.get("errors"),
                status_code=eligibility_error["status"],
            )

        # Idempotency check
        if idempotency_key is not None:
            dup = db.execute(
                text("SELECT id FROM payments WHERE idempotency_key = :key LIMIT 1"),
                {"key": idempotency_key},
            ).fetchone()
            if dup:
                raise APIException(
                    message="Duplicate payment request",
                    errors={"idempotency_key": ["This payment request has already been processed"]},
                    status_code=409,
                )

        # Calculate amounts
        total_amount = payment_customer_total(booking)
        paid_amount = float(booking.get("paid_amount") or 0)
        remaining_amount = round(max(0, total_amount - paid_amount), 2)
        verification = "not_required" if payment_method_norm == "cash" else "verified"

        # Insert payment row
        result = db.execute(
            text(
                "INSERT INTO payments "
                "(booking_id, family_user_id, caretaker_user_id, amount, payment_method, "
                "transaction_id, status, paid_at, payment_type, total_amount, remaining_amount, "
                "gateway_transaction_reference, verification_status, verified_at, idempotency_key) "
                "VALUES (:booking_id, :family_user_id, :caretaker_user_id, :amount, :payment_method, "
                ":transaction_id, 'success', NOW(), 'remaining', :total_amount, 0, "
                ":gateway_ref, :verification_status, NOW(), :idempotency_key)"
            ),
            {
                "booking_id": booking_id_int,
                "family_user_id": user_id,
                "caretaker_user_id": booking.get("caretaker_user_id"),
                "amount": remaining_amount,
                "payment_method": payment_method_norm,
                "transaction_id": transaction_id,
                "total_amount": total_amount,
                "gateway_ref": transaction_id,
                "verification_status": verification,
                "idempotency_key": idempotency_key,
            },
        )
        payment_id = result.lastrowid

        # Update booking — fully paid
        db.execute(
            text(
                "UPDATE bookings "
                "SET paid_amount = :paid, remaining_amount = 0, payment_status = 'paid' "
                "WHERE id = :bid"
            ),
            {"paid": total_amount, "bid": booking_id_int},
        )

        db.commit()

    except APIException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Remaining payment failed: {e}")
        raise APIException(message="Remaining payment failed", status_code=500)

    return {
        "payment_id": payment_id,
        "booking_id": booking_id_int,
        "payment_type": "remaining",
        "total_amount": total_amount,
        "remaining_paid": remaining_amount,
        "remaining_amount": 0,
        "payment_status": "paid",
        "payment_method": payment_method_norm,
        "verification_status": verification,
    }


def get_payment_history(
    db: Session,
    family_user: Dict[str, Any],
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """Route: api/v1/payment/payment_history"""
    user_id = int(family_user["id"])
    offset = (page - 1) * limit

    # Total spent
    row = db.execute(
        text("SELECT SUM(amount) FROM payments WHERE family_user_id = :uid AND status = 'success'"),
        {"uid": user_id},
    ).fetchone()
    total_spent = float(row[0]) if row and row[0] else 0

    # Count
    count_row = db.execute(
        text("SELECT COUNT(*) FROM payments WHERE family_user_id = :uid"),
        {"uid": user_id},
    ).fetchone()
    total = int(count_row[0]) if count_row else 0

    # History items
    rows = db.execute(
        text(
            "SELECT p.id AS payment_id, p.booking_id, p.amount, p.total_amount, p.remaining_amount, "
            "p.payment_type, p.payment_method, p.transaction_id, p.status, p.paid_at, "
            "b.service_type, b.booking_date, b.start_time, b.end_time, "
            "cp.full_name AS caretaker_name "
            "FROM payments p "
            "INNER JOIN bookings b ON b.id = p.booking_id "
            "LEFT JOIN caretaker_profiles cp ON cp.user_id = p.caretaker_user_id "
            "WHERE p.family_user_id = :uid "
            "ORDER BY p.id DESC "
            "LIMIT :lim OFFSET :off"
        ),
        {"uid": user_id, "lim": limit, "off": offset},
    ).fetchall()

    history = []
    for r in rows:
        item = dict(r._mapping)
        # display_status computed field
        pt = str(item.get("payment_type") or "")
        if pt == "advance":
            item["display_status"] = "Paid Half"
        elif pt == "remaining":
            item["display_status"] = "Paid Remaining"
        else:
            item["display_status"] = "Paid Full"

        # Convert date/time to strings
        for field in ["booking_date", "start_time", "end_time", "paid_at"]:
            val = item.get(field)
            if val is not None and not isinstance(val, str):
                item[field] = str(val)

        history.append(item)

    return {
        "total_spent": float(total_spent),
        # returns BOTH "history" and "items" with the same data
        "history": history,
        "items": history,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": math.ceil(total / limit) if limit > 0 else 0,
        },
    }


def get_payment_summary(
    db: Session,
    family_user: Dict[str, Any],
    booking_id: Any,
) -> Dict[str, Any]:
    """Route: api/v1/payment/payment_summary"""
    if not booking_id:
        raise APIException(message="Booking id is required", status_code=400)

    user_id = int(family_user["id"])

    row = db.execute(
        text(
            "SELECT b.id AS booking_id, b.service_type, b.booking_date, b.start_time, b.end_time, "
            "b.total_amount, b.total_customer_amount, b.paid_amount, b.remaining_amount, "
            "b.payment_status, cp.full_name AS caretaker_name "
            "FROM bookings b "
            "LEFT JOIN caretaker_profiles cp ON cp.user_id = b.caretaker_user_id "
            "WHERE b.id = :bid AND b.family_user_id = :fid"
        ),
        {"bid": int(booking_id), "fid": user_id},
    ).fetchone()

    if not row:
        raise APIException(message="Booking not found", status_code=404)

    booking = dict(row._mapping)

    # Exact logic: total_customer_amount ?: total_amount
    total_amount = float(booking.get("total_customer_amount") or 0) or float(booking.get("total_amount") or 0)
    paid_amount = float(booking.get("paid_amount") or 0)
    advance_amount = total_amount * 0.5
    remaining_amount = total_amount - paid_amount

    # Convert date/time to strings
    for field in ["booking_date", "start_time", "end_time"]:
        val = booking.get(field)
        if val is not None and not isinstance(val, str):
            booking[field] = str(val)

    return {
        "booking_id": booking.get("booking_id"),
        "caretaker_name": booking.get("caretaker_name"),
        "service_type": booking.get("service_type"),
        "booking_date": booking.get("booking_date"),
        "start_time": booking.get("start_time"),
        "end_time": booking.get("end_time"),
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "advance_percentage": 50,
        "advance_amount": advance_amount,
        "remaining_amount": remaining_amount,
        "payment_status": booking.get("payment_status"),
    }


def get_my_refunds(
    db: Session,
    family_user: Dict[str, Any],
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/payment/my_refunds

    READ-ONLY. No refund creation/admin processing.
    """
    user_id = int(family_user["id"])
    offset = (page - 1) * limit

    # Validate status filter
    validated_status = refund_validate_status_filter(status)
    if validated_status == "__invalid__":
        raise APIException(
            message="Validation failed",
            errors={"status": ["Status must be one of: pending, approved, rejected, processed, failed, all"]},
            status_code=400,
        )

    # Build WHERE
    where = "WHERE br.family_user_id = :uid"
    params: Dict[str, Any] = {"uid": user_id}
    if validated_status is not None:
        where += " AND br.status = :status"
        params["status"] = validated_status

    # Count
    count_row = db.execute(
        text(f"SELECT COUNT(*) FROM booking_refunds br {where}"),
        params,
    ).fetchone()
    total = int(count_row[0]) if count_row else 0

    # Items
    rows = db.execute(
        text(
            f"SELECT br.id, br.booking_id, br.paid_amount, br.refund_amount, br.refund_percentage, "
            f"br.refund_method, br.refund_transaction_id, br.reason, br.status, br.admin_note, "
            f"br.approved_at, br.rejected_at, br.processed_at, br.created_at, "
            f"b.booking_date, b.start_time, b.end_time, "
            f"p.patient_name, "
            f"cu.username AS caretaker_name "
            f"FROM booking_refunds br "
            f"INNER JOIN bookings b ON b.id = br.booking_id "
            f"LEFT JOIN patient_details p ON p.id = b.patient_id "
            f"LEFT JOIN users cu ON cu.id = br.caretaker_user_id "
            f"{where} "
            f"ORDER BY br.created_at DESC, br.id DESC "
            f"LIMIT :lim OFFSET :off"
        ),
        {**params, "lim": limit, "off": offset},
    ).fetchall()

    items = []
    for r in rows:
        rd = dict(r._mapping)
        items.append({
            "refund_id": int(rd["id"]),
            "booking_id": int(rd["booking_id"]),
            "patient_name": rd.get("patient_name") or "",
            "caretaker_name": rd.get("caretaker_name") or "",
            "booking_date": str(rd["booking_date"]) if rd.get("booking_date") else None,
            "start_time": str(rd["start_time"]) if rd.get("start_time") else None,
            "end_time": str(rd["end_time"]) if rd.get("end_time") else None,
            "paid_amount": refund_format_money(rd.get("paid_amount")),
            "refund_amount": refund_format_money(rd.get("refund_amount")),
            "refund_percentage": refund_format_money(rd.get("refund_percentage")),
            "refund_method": rd.get("refund_method"),
            "refund_transaction_id": rd.get("refund_transaction_id"),
            "status": rd.get("status"),
            "reason": rd.get("reason"),
            "admin_note": rd.get("admin_note"),
            "created_at": refund_iso(rd.get("created_at")),
            "approved_at": refund_iso(rd.get("approved_at")),
            "rejected_at": refund_iso(rd.get("rejected_at")),
            "processed_at": refund_iso(rd.get("processed_at")),
        })

    return {
        "items": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": math.ceil(total / limit) if limit > 0 else 0,
        },
    }


def get_refund_detail(
    db: Session,
    family_user: Dict[str, Any],
    refund_id: Any,
) -> Dict[str, Any]:
    """
    Route: api/v1/payment/refund_detail

    READ-ONLY single refund detail.
    """
    # Validate
    try:
        rid = int(refund_id)
        if rid < 1:
            raise ValueError
    except (TypeError, ValueError):
        raise APIException(
            message="Invalid refund id",
            errors={"id": ["Refund id must be a positive integer"]},
            status_code=400,
        )

    user_id = int(family_user["id"])

    row = db.execute(
        text(
            "SELECT br.id, br.booking_id, br.paid_amount, br.refund_amount, br.refund_percentage, "
            "br.refund_method, br.refund_transaction_id, br.reason, br.status, br.admin_note, "
            "br.approved_at, br.rejected_at, br.processed_at, br.created_at, br.updated_at, "
            "b.booking_date, b.start_time, b.end_time, "
            "p.patient_name, "
            "cu.username AS caretaker_name "
            "FROM booking_refunds br "
            "INNER JOIN bookings b ON b.id = br.booking_id "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "LEFT JOIN users cu ON cu.id = br.caretaker_user_id "
            "WHERE br.id = :rid AND br.family_user_id = :fid "
            "LIMIT 1"
        ),
        {"rid": rid, "fid": user_id},
    ).fetchone()

    if not row:
        raise APIException(message="Refund not found", status_code=404)

    rd = dict(row._mapping)
    return {
        "refund_id": int(rd["id"]),
        "booking_id": int(rd["booking_id"]),
        "patient_name": rd.get("patient_name") or "",
        "caretaker_name": rd.get("caretaker_name") or "",
        "booking_date": str(rd["booking_date"]) if rd.get("booking_date") else None,
        "start_time": str(rd["start_time"]) if rd.get("start_time") else None,
        "end_time": str(rd["end_time"]) if rd.get("end_time") else None,
        "paid_amount": refund_format_money(rd.get("paid_amount")),
        "refund_amount": refund_format_money(rd.get("refund_amount")),
        "refund_percentage": refund_format_money(rd.get("refund_percentage")),
        "refund_method": rd.get("refund_method"),
        "refund_transaction_id": rd.get("refund_transaction_id"),
        "status": rd.get("status"),
        "reason": rd.get("reason"),
        "admin_note": rd.get("admin_note"),
        "created_at": refund_iso(rd.get("created_at")),
        "approved_at": refund_iso(rd.get("approved_at")),
        "rejected_at": refund_iso(rd.get("rejected_at")),
        "processed_at": refund_iso(rd.get("processed_at")),
        "updated_at": refund_iso(rd.get("updated_at")),
    }
