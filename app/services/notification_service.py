"""
WeCare — Notification Service

Mirrors helpers/notifications.
"""

import json
import logging
import math
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException

logger = logging.getLogger(__name__)


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notification_type: str,
    related_type: Optional[str] = None,
    related_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """
    Route: create_notification() — helpers/notifications L15-46
    """
    try:
        meta_json = json.dumps(metadata) if metadata else None
        result = db.execute(
            text(
                "INSERT INTO notifications "
                "(user_id, title, message, type, related_type, related_id, metadata, is_read) "
                "VALUES (:user_id, :title, :message, :type, :related_type, :related_id, :metadata, 0)"
            ),
            {
                "user_id": int(user_id),
                "title": str(title).strip(),
                "message": str(message).strip(),
                "type": str(notification_type).strip(),
                "related_type": str(related_type).strip() if related_type else None,
                "related_id": int(related_id) if related_id is not None else None,
                "metadata": meta_json,
            },
        )
        return result.lastrowid
    except Exception as e:
        logger.error(f"notification_create_failed: {e}")
        return None


def notify_caretaker_approved(db: Session, caretaker_user_id: int) -> None:
    """
    Route: notify_caretaker_approved() — helpers/notifications L254-264
    """
    create_notification(
        db=db,
        user_id=int(caretaker_user_id),
        title="Profile approved",
        message="Your caretaker profile has been approved.",
        notification_type="caretaker_approved",
        related_type="caretaker_profile",
        related_id=int(caretaker_user_id),
    )


def notify_caretaker_rejected(db: Session, caretaker_user_id: int, reason: str) -> None:
    """
    Route: notify_caretaker_rejected() — helpers/notifications L266-277
    """
    create_notification(
        db=db,
        user_id=int(caretaker_user_id),
        title="Profile rejected",
        message="Your caretaker profile needs attention.",
        notification_type="caretaker_rejected",
        related_type="caretaker_profile",
        related_id=int(caretaker_user_id),
        metadata={"reason": str(reason).strip()},
    )


def notification_booking(db: Session, booking_id: int) -> Optional[Dict[str, Any]]:
    """
    Route: notification_booking() — helpers/notifications L63-77
    """
    row = db.execute(
        text(
            "SELECT b.id, b.family_user_id, b.caretaker_user_id, b.patient_id, b.service_type, "
            "       p.patient_name "
            "FROM bookings b "
            "LEFT JOIN patient_details p ON p.id = b.patient_id "
            "WHERE b.id = :bid "
            "LIMIT 1"
        ),
        {"bid": int(booking_id)},
    ).fetchone()

    if not row:
        return None
    return dict(row._mapping)


def notification_admin_user_ids(db: Session) -> list[int]:
    """
    Route: notification_admin_user_ids() — helpers/notifications L79-83
    """
    rows = db.execute(
        text("SELECT id FROM users WHERE role = 'admin' AND is_active = 1")
    ).fetchall()
    return [int(r[0]) for r in rows]


def notify_booking_created(db: Session, booking_id: int) -> None:
    """
    Route: notify_booking_created() — helpers/notifications L85-102
    """
    booking = notification_booking(db, booking_id)
    if not booking or not booking.get("caretaker_user_id"):
        return

    create_notification(
        db=db,
        user_id=int(booking["caretaker_user_id"]),
        title="New care request",
        message="You have a new booking request.",
        notification_type="booking_created",
        related_type="booking",
        related_id=int(booking_id),
        metadata={"booking_id": int(booking_id)},
    )


def notify_booking_accepted(db: Session, booking_id: int) -> None:
    """
    Route: notify_booking_accepted() — helpers/notifications L104-121
    """
    booking = notification_booking(db, booking_id)
    if not booking:
        return

    create_notification(
        db=db,
        user_id=int(booking["family_user_id"]),
        title="Booking accepted",
        message="Your caretaker accepted the booking request.",
        notification_type="booking_accepted",
        related_type="booking",
        related_id=int(booking_id),
        metadata={"booking_id": int(booking_id)},
    )


def notify_booking_declined(db: Session, booking_id: int) -> None:
    """
    Route: notify_booking_declined() — helpers/notifications L123-140
    """
    booking = notification_booking(db, booking_id)
    if not booking:
        return

    create_notification(
        db=db,
        user_id=int(booking["family_user_id"]),
        title="Booking declined",
        message="Your caretaker declined the booking request.",
        notification_type="booking_declined",
        related_type="booking",
        related_id=int(booking_id),
        metadata={"booking_id": int(booking_id)},
    )


def notify_booking_cancelled(
    db: Session, booking_id: int, metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Route: notify_booking_cancelled() — helpers/notifications L142-173
    """
    booking = notification_booking(db, booking_id)
    if not booking:
        return

    base_metadata = {"booking_id": int(booking_id), "status": "cancelled"}
    if metadata:
        base_metadata.update(metadata)

    create_notification(
        db=db,
        user_id=int(booking["family_user_id"]),
        title="Booking cancelled",
        message="Your booking has been cancelled.",
        notification_type="booking_cancelled",
        related_type="booking",
        related_id=int(booking_id),
        metadata=base_metadata,
    )

    if booking.get("caretaker_user_id"):
        create_notification(
            db=db,
            user_id=int(booking["caretaker_user_id"]),
            title="Booking cancelled",
            message="A booking assigned to you was cancelled.",
            notification_type="booking_cancelled",
            related_type="booking",
            related_id=int(booking_id),
            metadata=base_metadata,
        )


def notify_visit_started(db: Session, booking_id: int) -> None:
    """
    Route: notify_visit_started() — helpers/notifications L175-192
    """
    booking = notification_booking(db, booking_id)
    if not booking:
        return

    create_notification(
        db=db,
        user_id=int(booking["family_user_id"]),
        title="Visit started",
        message="Your caretaker has started the visit.",
        notification_type="visit_started",
        related_type="booking",
        related_id=int(booking_id),
        metadata={"booking_id": int(booking_id)},
    )


def notify_visit_completed(db: Session, booking_id: int) -> None:
    """
    Route: notify_visit_completed() — helpers/notifications L194-211
    """
    booking = notification_booking(db, booking_id)
    if not booking:
        return

    create_notification(
        db=db,
        user_id=int(booking["family_user_id"]),
        title="Visit completed",
        message="Your care visit has been completed.",
        notification_type="visit_completed",
        related_type="booking",
        related_id=int(booking_id),
        metadata={"booking_id": int(booking_id)},
    )


def notify_admins_caretaker_cancelled(
    db: Session,
    booking_id: int,
    caretaker_user_id: int,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Route: notify_admins_caretaker_cancelled() — api/v1/booking/caretaker_cancel_booking L40-59
    """
    admin_ids = notification_admin_user_ids(db)
    meta = {
        "booking_id": int(booking_id),
        "caretaker_user_id": int(caretaker_user_id),
        "requires_replacement_review": True,
    }
    if metadata:
        meta.update(metadata)

    for admin_id in admin_ids:
        create_notification(
            db=db,
            user_id=admin_id,
            title="Caretaker cancelled booking",
            message="A caretaker cancelled an upcoming accepted booking.",
            notification_type="booking_cancelled",
            related_type="booking",
            related_id=int(booking_id),
            metadata=meta,
        )


def notify_sos_created(db: Session, sos_id: int) -> None:
    """
    Route: notify_sos_created() — helpers/notifications L213-252
    """
    row = db.execute(
        text(
            "SELECT s.id, s.user_id, s.booking_id, u.role AS creator_role, "
            "       b.family_user_id, b.caretaker_user_id "
            "FROM sos_alerts s "
            "INNER JOIN users u ON u.id = s.user_id "
            "LEFT JOIN bookings b ON b.id = s.booking_id "
            "WHERE s.id = :sos_id "
            "LIMIT 1"
        ),
        {"sos_id": int(sos_id)},
    ).fetchone()

    if not row:
        return

    recipients = []
    creator_role = getattr(row, "creator_role", None)
    family_user_id = getattr(row, "family_user_id", None)
    caretaker_user_id = getattr(row, "caretaker_user_id", None)
    booking_id = getattr(row, "booking_id", None)

    if creator_role == "caretaker" and family_user_id:
        recipients.append(int(family_user_id))
    if creator_role == "family" and caretaker_user_id:
        recipients.append(int(caretaker_user_id))

    admin_ids = notification_admin_user_ids(db)
    recipients.extend(admin_ids)

    # Deduplicate while preserving order
    unique_recipients = []
    for r in recipients:
        if r and r not in unique_recipients:
            unique_recipients.append(r)

    for uid in unique_recipients:
        create_notification(
            db=db,
            user_id=uid,
            title="SOS alert",
            message="An SOS alert needs attention.",
            notification_type="sos_created",
            related_type="sos",
            related_id=int(sos_id),
            metadata={
                "sos_id": int(sos_id),
                "booking_id": int(booking_id) if booking_id is not None else None,
            },
        )


def notify_complaint_updated(db: Session, complaint_id: int) -> None:
    """
    Route: notify_complaint_updated() — helpers/notifications L300-319
    """
    row = db.execute(
        text("SELECT family_user_id, status FROM complaints WHERE id = :cid LIMIT 1"),
        {"cid": int(complaint_id)},
    ).fetchone()
    if not row:
        return

    fam_id = getattr(row, "family_user_id", None)
    status = getattr(row, "status", "")
    if fam_id:
        create_notification(
            db=db,
            user_id=int(fam_id),
            title="Complaint updated",
            message="Your complaint status was updated.",
            notification_type="complaint_updated",
            related_type="complaint",
            related_id=int(complaint_id),
            metadata={
                "complaint_id": int(complaint_id),
                "status": str(status.value if hasattr(status, "value") else status),
            },
        )


def notify_replacement_updated(db: Session, replacement_id: int) -> None:
    """
    Route: notify_replacement_updated() — helpers/notifications L321-340
    """
    row = db.execute(
        text("SELECT family_user_id, status FROM replacement_tickets WHERE id = :rid LIMIT 1"),
        {"rid": int(replacement_id)},
    ).fetchone()
    if not row:
        return

    fam_id = getattr(row, "family_user_id", None)
    status = getattr(row, "status", "")
    if fam_id:
        create_notification(
            db=db,
            user_id=int(fam_id),
            title="Replacement updated",
            message="Your replacement request was updated.",
            notification_type="replacement_updated",
            related_type="replacement",
            related_id=int(replacement_id),
            metadata={
                "replacement_id": int(replacement_id),
                "status": str(status.value if hasattr(status, "value") else status),
            },
        )


# ============================================================
# Notification API endpoint services (Part 10)
# ============================================================


def get_my_notifications(
    db: Session,
    current_user: Dict[str, Any],
    page: int = 1,
    limit: int = 20,
    unread_only: Any = "false",
    notification_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/notification/my_notifications
    """
    user_id = int(current_user["id"])
    page = max(1, int(page or 1))
    limit = max(1, min(100, int(limit or 20)))
    offset = (page - 1) * limit

    unread_str = str(unread_only or "").strip().lower()
    is_unread = unread_str in ["true", "1", "yes"]

    where_clauses = ["user_id = :user_id"]
    params: Dict[str, Any] = {"user_id": user_id}

    if is_unread:
        where_clauses.append("is_read = 0")

    if notification_type and str(notification_type).strip():
        where_clauses.append("type = :type")
        params["type"] = str(notification_type).strip()

    where_sql = " AND ".join(where_clauses)

    count_row = db.execute(
        text(f"SELECT COUNT(*) FROM notifications WHERE {where_sql}"),
        params,
    ).fetchone()
    total = int(count_row[0]) if count_row else 0

    query_params = {**params, "limit": limit, "offset": offset}
    rows = db.execute(
        text(
            f"SELECT id, user_id, title, message, type, related_type, related_id, metadata, is_read, created_at "
            f"FROM notifications "
            f"WHERE {where_sql} "
            f"ORDER BY id DESC "
            f"LIMIT :limit OFFSET :offset"
        ),
        query_params,
    ).fetchall()

    items = []
    for r in rows:
        meta_val = r.metadata
        metadata_dict = {}
        if meta_val:
            try:
                decoded = json.loads(meta_val) if isinstance(meta_val, str) else meta_val
                if isinstance(decoded, dict):
                    metadata_dict = decoded
            except Exception:
                metadata_dict = {}

        created_str = r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at)

        items.append({
            "id": int(r.id),
            "user_id": int(r.user_id),
            "title": str(r.title),
            "message": str(r.message),
            "type": str(r.type),
            "related_type": r.related_type,
            "related_id": int(r.related_id) if r.related_id is not None else None,
            "metadata": metadata_dict,
            "is_read": bool(r.is_read),
            "created_at": created_str,
        })

    unread_count_row = db.execute(
        text("SELECT COUNT(*) FROM notifications WHERE user_id = :user_id AND is_read = 0"),
        {"user_id": user_id},
    ).fetchone()
    unread_count = int(unread_count_row[0]) if unread_count_row else 0

    return {
        "items": items,
        "unread_count": unread_count,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": math.ceil(total / limit) if limit > 0 else 0,
        },
    }


def mark_notification_read(
    db: Session,
    current_user: Dict[str, Any],
    notification_id: Any,
) -> Dict[str, Any]:
    """
    Route: api/v1/notification/mark_read
    """
    user_id = int(current_user["id"])
    if not notification_id:
        raise APIException(
            message="Validation failed",
            errors={"notification_id": ["Notification id is required"]},
            status_code=400,
        )
    try:
        nid = int(notification_id)
    except (ValueError, TypeError):
        raise APIException(
            message="Validation failed",
            errors={"notification_id": ["Notification id must be an integer"]},
            status_code=400,
        )

    result = db.execute(
        text("UPDATE notifications SET is_read = 1 WHERE id = :id AND user_id = :user_id"),
        {"id": nid, "user_id": user_id},
    )
    db.commit()

    if result.rowcount == 0:
        raise APIException(message="Notification not found", status_code=404)

    return {
        "notification_id": nid,
        "is_read": True,
    }


def mark_all_notifications_read(
    db: Session,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route: api/v1/notification/mark_all_read
    """
    user_id = int(current_user["id"])
    result = db.execute(
        text("UPDATE notifications SET is_read = 1 WHERE user_id = :user_id AND is_read = 0"),
        {"user_id": user_id},
    )
    db.commit()

    return {
        "updated_count": int(result.rowcount),
    }


def admin_create_notification(
    db: Session,
    admin_user: Dict[str, Any],
    user_id: Any,
    title: Optional[str],
    message: Optional[str],
) -> Dict[str, Any]:
    """
    Route: api/v1/notification/create_notification
    """
    if not user_id or not title or not message:
        raise APIException(
            message="User id, title and message are required",
            status_code=400,
        )
    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        raise APIException(
            message="User id, title and message are required",
            status_code=400,
        )

    user_row = db.execute(
        text("SELECT id FROM users WHERE id = :uid AND is_active = 1"),
        {"uid": uid},
    ).fetchone()
    if not user_row:
        raise APIException(message="User not found", status_code=404)

    notification_id = create_notification(
        db=db,
        user_id=uid,
        title=str(title).strip(),
        message=str(message).strip(),
        notification_type="admin_announcement",
        related_type="admin_announcement",
        related_id=None,
        metadata={"created_by": int(admin_user["id"])},
    )
    db.commit()

    return {
        "notification_id": notification_id,
    }


def register_device_token(
    db: Session,
    current_user: Dict[str, Any],
    device_token: Optional[str],
    platform: Optional[str],
    app_type: Optional[str],
) -> Dict[str, Any]:
    """
    Route: api/v1/notification/register_device
    """
    user_id = int(current_user["id"])
    d_token = str(device_token or "").strip()
    p_form = str(platform or "").strip().lower()
    a_type = str(app_type or current_user.get("role") or "").strip().lower()

    errors: Dict[str, List[str]] = {}
    if not d_token:
        errors["device_token"] = ["Device token is required"]
    if p_form not in ["android", "ios", "web"]:
        errors["platform"] = ["Platform must be android, ios, or web"]
    if a_type not in ["family", "caretaker", "admin"]:
        errors["app_type"] = ["App type must be family, caretaker, or admin"]

    if errors:
        raise APIException(
            message="Validation failed",
            errors=errors,
            status_code=400,
        )

    db.execute(
        text(
            "INSERT INTO notification_device_tokens "
            "(user_id, device_token, platform, app_type, is_active, last_used_at) "
            "VALUES (:user_id, :device_token, :platform, :app_type, 1, NOW()) "
            "ON DUPLICATE KEY UPDATE "
            "user_id = VALUES(user_id), "
            "platform = VALUES(platform), "
            "app_type = VALUES(app_type), "
            "is_active = 1, "
            "last_used_at = NOW(), "
            "updated_at = NOW()"
        ),
        {
            "user_id": user_id,
            "device_token": d_token,
            "platform": p_form,
            "app_type": a_type,
        },
    )
    db.commit()

    return {
        "device_token": d_token,
        "platform": p_form,
        "app_type": a_type,
        "is_active": True,
    }


def remove_device_token(
    db: Session,
    current_user: Dict[str, Any],
    device_token: Optional[str],
) -> Dict[str, Any]:
    """
    Route: api/v1/notification/remove_device
    """
    user_id = int(current_user["id"])
    d_token = str(device_token or "").strip()

    if not d_token:
        raise APIException(
            message="Validation failed",
            errors={"device_token": ["Device token is required"]},
            status_code=400,
        )

    db.execute(
        text(
            "UPDATE notification_device_tokens "
            "SET is_active = 0, updated_at = NOW() "
            "WHERE user_id = :user_id AND device_token = :device_token"
        ),
        {"user_id": user_id, "device_token": d_token},
    )
    db.commit()

    return {
        "device_token": d_token,
        "is_active": False,
    }


def notify_payout_processed(db: Session, payout_id: int) -> None:
    """
    Route: notify_payout_processed() — helpers/notifications L279-298
    """
    row = db.execute(
        text("SELECT caretaker_user_id, amount FROM caretaker_payouts WHERE id = :id LIMIT 1"),
        {"id": int(payout_id)},
    ).mappings().first()
    if not row:
        return

    create_notification(
        db=db,
        user_id=int(row["caretaker_user_id"]),
        title="Payout processed",
        message="Your weekly payout has been marked as paid.",
        notification_type="payout_processed",
        related_type="payout",
        related_id=int(payout_id),
        metadata={"payout_id": int(payout_id), "amount": float(row["amount"])},
    )
    try:
        db.commit()
    except Exception:
        pass






