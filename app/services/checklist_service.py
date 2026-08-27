"""
WeCare — Checklist Service (Part 10)

Migrates api/v1/checklist/* + checklist helpers.
Handles booking checklist task listing, creation, and status updates.
"""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.services.care_request_service import care_request_text, care_request_datetime

logger = logging.getLogger(__name__)


def visit_live_task_status(status: Any) -> str:
    """
    Route: visit_live_task_status() — helpers/visit_live L23-31
    """
    status_str = str(status or "").strip().lower()
    if status_str == "done":
        return "completed"
    return status_str if status_str in ["pending", "ongoing", "completed"] else ""


def get_booking_tasks(
    db: Session,
    current_user: Dict[str, Any],
    booking_id: Any,
) -> Dict[str, Any]:
    """
    Route: api/v1/checklist/booking_tasks
    Role-aware access control:
    - family: must own booking
    - caretaker: booking must be assigned to caretaker and status in ('accepted','in_progress','completed')
    - admin: can view any booking
    """
    if not booking_id:
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )
    try:
        bid = int(booking_id)
        if bid <= 0:
            raise ValueError
    except (ValueError, TypeError):
        raise APIException(
            message="Validation failed",
            errors={"booking_id": ["Booking id must be an integer"]},
            status_code=400,
        )

    user_role = str(current_user.get("role") or "").lower()
    user_id = int(current_user["id"])

    if user_role == "family":
        booking_row = db.execute(
            text("SELECT id FROM bookings WHERE id = :bid AND family_user_id = :uid LIMIT 1"),
            {"bid": bid, "uid": user_id},
        ).fetchone()
    elif user_role == "caretaker":
        booking_row = db.execute(
            text(
                "SELECT id FROM bookings "
                "WHERE id = :bid AND caretaker_user_id = :uid AND status IN ('accepted','in_progress','completed') "
                "LIMIT 1"
            ),
            {"bid": bid, "uid": user_id},
        ).fetchone()
    else:
        booking_row = db.execute(
            text("SELECT id FROM bookings WHERE id = :bid LIMIT 1"),
            {"bid": bid},
        ).fetchone()

    if not booking_row:
        raise APIException(message="Booking not found", status_code=404)

    rows = db.execute(
        text(
            "SELECT id, booking_id, title, description, status, completed_by, completed_at, created_at, updated_at "
            "FROM booking_checklist_tasks "
            "WHERE booking_id = :bid "
            "ORDER BY id ASC"
        ),
        {"bid": bid},
    ).fetchall()

    tasks: List[Dict[str, Any]] = []
    for r in rows:
        raw_status = str(r.status or "pending").strip().lower()
        if raw_status == "done":
            raw_status = "completed"
        valid_status = raw_status if raw_status in ["pending", "ongoing", "completed"] else "pending"

        tasks.append({
            "task_id": int(r.id),
            "booking_id": int(r.booking_id),
            "title": care_request_text(r.title),
            "description": care_request_text(r.description),
            "status": valid_status,
            "completed_by": int(r.completed_by) if r.completed_by is not None else None,
            "completed_at": care_request_datetime(r.completed_at),
            "created_at": care_request_datetime(r.created_at),
            "updated_at": care_request_datetime(r.updated_at),
        })

    return {
        "tasks": tasks,
    }


def create_task(
    db: Session,
    family_user: Dict[str, Any],
    booking_id: Any,
    title: Optional[str],
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Route: api/v1/checklist/create_task
    """
    user_id = int(family_user["id"])
    title_str = str(title or "").strip()
    desc_str = str(description or "").strip()

    errors: Dict[str, List[str]] = {}
    if not booking_id:
        errors["booking_id"] = ["Booking id is required"]
    if not title_str:
        errors["title"] = ["Title is required"]

    if errors:
        raise APIException(
            message="Booking id and title are required",
            errors=errors,
            status_code=400,
        )

    try:
        bid = int(booking_id)
        if bid <= 0:
            raise ValueError
    except (ValueError, TypeError):
        raise APIException(
            message="Booking id and title are required",
            errors={"booking_id": ["Booking id is required"]},
            status_code=400,
        )

    booking_row = db.execute(
        text(
            "SELECT id, caretaker_user_id "
            "FROM bookings "
            "WHERE id = :bid AND family_user_id = :uid AND status IN ('pending','accepted','in_progress') "
            "LIMIT 1"
        ),
        {"bid": bid, "uid": user_id},
    ).fetchone()

    if not booking_row:
        raise APIException(message="Booking not found for checklist task", status_code=404)

    caretaker_id = booking_row.caretaker_user_id

    result = db.execute(
        text(
            "INSERT INTO booking_checklist_tasks "
            "(booking_id, family_user_id, caretaker_user_id, title, description) "
            "VALUES (:booking_id, :family_user_id, :caretaker_user_id, :title, :description)"
        ),
        {
            "booking_id": bid,
            "family_user_id": user_id,
            "caretaker_user_id": int(caretaker_id) if caretaker_id is not None else None,
            "title": title_str,
            "description": desc_str if desc_str else None,
        },
    )
    db.commit()

    return {
        "task_id": result.lastrowid,
    }


def mark_done(
    db: Session,
    caretaker_user: Dict[str, Any],
    task_id: Any,
    status: Optional[str] = "completed",
) -> Dict[str, Any]:
    """
    Route: api/v1/checklist/mark_done
    Only caretaker assigned to the in_progress booking can update the checklist task.
    """
    user_id = int(caretaker_user["id"])

    if not task_id:
        raise APIException(
            message="Validation failed",
            errors={"task_id": ["Task id must be an integer"]},
            status_code=400,
        )
    try:
        tid = int(task_id)
        if tid <= 0:
            raise ValueError
    except (ValueError, TypeError):
        raise APIException(
            message="Validation failed",
            errors={"task_id": ["Task id must be an integer"]},
            status_code=400,
        )

    norm_status = visit_live_task_status(status or "completed")
    if not norm_status:
        raise APIException(
            message="Validation failed",
            errors={"status": ["Allowed values are pending, ongoing, completed"]},
            status_code=400,
        )

    task_row = db.execute(
        text(
            "SELECT t.id "
            "FROM booking_checklist_tasks t "
            "INNER JOIN bookings b ON b.id = t.booking_id "
            "WHERE t.id = :tid AND b.caretaker_user_id = :uid AND b.status = 'in_progress' "
            "LIMIT 1"
        ),
        {"tid": tid, "uid": user_id},
    ).fetchone()

    if not task_row:
        raise APIException(message="Checklist task not found", status_code=404)

    now_dt = datetime.now() if norm_status == "completed" else None
    completed_by = user_id if norm_status == "completed" else None

    db.execute(
        text(
            "UPDATE booking_checklist_tasks "
            "SET status = :status, completed_by = :completed_by, completed_at = :completed_at "
            "WHERE id = :tid"
        ),
        {
            "status": norm_status,
            "completed_by": completed_by,
            "completed_at": now_dt,
            "tid": tid,
        },
    )
    db.commit()

    return {
        "task_id": tid,
        "status": norm_status,
        "completed_at": care_request_datetime(now_dt),
    }
