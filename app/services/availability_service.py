"""
WeCare — Caretaker Availability Service

Mirrors helpers/availability.
Single source of truth for all caretaker availability state changes.
"""

from typing import Any, Dict, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit_service import audit_log


def caretaker_has_active_visit(db: Session, caretaker_user_id: int) -> bool:
    """
    Route: caretaker_has_active_visit() — helpers/availability L16-31
    """
    row = db.execute(
        text(
            "SELECT vt.id "
            "FROM visit_tracking vt "
            "INNER JOIN bookings b ON b.id = vt.booking_id "
            "WHERE vt.caretaker_user_id = :cid "
            "  AND vt.check_out_time IS NULL "
            "  AND vt.check_in_time IS NOT NULL "
            "  AND b.status = 'in_progress' "
            "LIMIT 1"
        ),
        {"cid": int(caretaker_user_id)},
    ).fetchone()

    return row is not None


def caretaker_can_be_available(db: Session, caretaker_user_id: int) -> Tuple[bool, Optional[str]]:
    """
    Route: caretaker_can_be_available() — helpers/availability L38-72
    """
    row = db.execute(
        text(
            "SELECT u.id, u.is_active, cp.verification_status, "
            "       cp.availability_locked_by_admin "
            "FROM users u "
            "INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
            "WHERE u.id = :cid AND u.role = 'caretaker' "
            "LIMIT 1"
        ),
        {"cid": int(caretaker_user_id)},
    ).fetchone()

    if not row:
        return False, "Caretaker profile not found"

    m = row._mapping
    if int(m["is_active"] or 0) != 1:
        return False, "User account is inactive"

    if m["verification_status"] != "approved":
        return False, f"Caretaker verification status is {m['verification_status']}"

    if int(m["availability_locked_by_admin"] or 0) == 1:
        return False, "Caretaker availability is locked by admin"

    if caretaker_has_active_visit(db, caretaker_user_id):
        return False, "Caretaker has an active visit in progress"

    return True, None


def is_caretaker_available(db: Session, caretaker_user_id: int) -> bool:
    """
    Route: is_caretaker_available() — helpers/availability L366-382
    """
    row = db.execute(
        text(
            "SELECT cp.is_available "
            "FROM caretaker_profiles cp "
            "INNER JOIN users u ON u.id = cp.user_id "
            "WHERE cp.user_id = :cid "
            "  AND u.role = 'caretaker' "
            "  AND u.is_active = 1 "
            "  AND cp.verification_status = 'approved' "
            "LIMIT 1"
        ),
        {"cid": int(caretaker_user_id)},
    ).fetchone()

    return row is not None and int(row._mapping["is_available"] or 0) == 1


def caretaker_can_accept_booking(db: Session, caretaker_user_id: int) -> bool:
    """
    Route: caretaker_can_accept_booking() — helpers/availability L342-361
    """
    if not is_caretaker_available(db, caretaker_user_id):
        return False

    row = db.execute(
        text("SELECT availability_locked_by_admin FROM caretaker_profiles WHERE user_id = :cid"),
        {"cid": int(caretaker_user_id)},
    ).fetchone()

    if row and int(row._mapping["availability_locked_by_admin"] or 0) == 1:
        return False

    return not caretaker_has_active_visit(db, caretaker_user_id)


def touch_caretaker_presence(db: Session, caretaker_user_id: int) -> None:
    """
    Route: touch_caretaker_presence() — helpers/availability L428-436
    """
    db.execute(
        text("UPDATE caretaker_profiles SET last_active_at = NOW() WHERE user_id = :cid"),
        {"cid": int(caretaker_user_id)},
    )
    db.commit()


def caretaker_availability_payload(db: Session, caretaker_user_id: int) -> Optional[Dict[str, Any]]:
    """
    Route: caretaker_availability_payload() — helpers/availability L387-423
    """
    row = db.execute(
        text(
            "SELECT cp.is_available, cp.manual_availability_enabled, "
            "       cp.availability_reason, cp.availability_locked_by_admin, "
            "       cp.availability_locked_note, cp.availability_locked_at, "
            "       cp.availability_changed_at, cp.availability_changed_by, "
            "       cp.availability_auto_restored_at, cp.availability_version, "
            "       cp.last_active_at, cp.verification_status "
            "FROM caretaker_profiles cp "
            "WHERE cp.user_id = :cid"
        ),
        {"cid": int(caretaker_user_id)},
    ).fetchone()

    if not row:
        return None

    m = row._mapping
    has_active_visit = caretaker_has_active_visit(db, caretaker_user_id)

    locked_at = m.get("availability_locked_at")
    changed_at = m.get("availability_changed_at")
    restored_at = m.get("availability_auto_restored_at")
    last_active = m.get("last_active_at")

    return {
        "is_available": int(m.get("is_available") or 0) == 1,
        "manual_availability_enabled": int(m.get("manual_availability_enabled") or 0) == 1,
        "availability_reason": m.get("availability_reason"),
        "availability_locked_by_admin": int(m.get("availability_locked_by_admin") or 0) == 1,
        "availability_locked_note": m.get("availability_locked_note"),
        "availability_locked_at": locked_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(locked_at, "strftime") else (str(locked_at) if locked_at else None),
        "availability_changed_at": changed_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(changed_at, "strftime") else (str(changed_at) if changed_at else None),
        "availability_changed_by": m.get("availability_changed_by"),
        "availability_auto_restored_at": restored_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(restored_at, "strftime") else (str(restored_at) if restored_at else None),
        "availability_version": int(m.get("availability_version") or 1),
        "last_active_at": last_active.strftime("%Y-%m-%d %H:%M:%S") if hasattr(last_active, "strftime") else (str(last_active) if last_active else None),
        "can_accept_booking": caretaker_can_accept_booking(db, caretaker_user_id),
        "has_active_visit": has_active_visit,
    }


def set_caretaker_availability(
    db: Session,
    caretaker_user_id: int,
    available: bool,
    reason: str = "manual_off",
    changed_by: str = "caretaker",
    actor_user_id: Optional[int] = None,
    booking_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Route: set_caretaker_availability() — helpers/availability L86-216
    Single source of truth for setting caretaker availability.
    """
    row = db.execute(
        text(
            "SELECT u.id, u.is_active, "
            "       cp.is_available, cp.manual_availability_enabled, "
            "       cp.availability_reason, cp.availability_version, "
            "       cp.verification_status, cp.availability_locked_by_admin "
            "FROM users u "
            "INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
            "WHERE u.id = :cid AND u.role = 'caretaker' "
            "LIMIT 1"
        ),
        {"cid": int(caretaker_user_id)},
    ).fetchone()

    if not row:
        return {
            "success": False,
            "message": "Caretaker not found",
            "errors": {"caretaker": ["Caretaker profile was not found"]},
        }

    m = row._mapping
    old_available = int(m.get("is_available") or 0) == 1
    old_reason = m.get("availability_reason") or "manual_off"
    old_version = int(m.get("availability_version") or 1)

    if available and changed_by == "caretaker":
        if int(m.get("is_active") or 0) != 1 or m.get("verification_status") != "approved":
            return {
                "success": False,
                "message": "Caretaker is not eligible for availability",
                "errors": {"is_available": ["Only active approved caretakers can become available"]},
            }

        if int(m.get("availability_locked_by_admin") or 0) == 1:
            return {
                "success": False,
                "message": "Caretaker availability is locked by admin",
                "errors": {"is_available": ["An administrator has locked your availability. Please contact support."]},
            }

        if caretaker_has_active_visit(db, caretaker_user_id):
            return {
                "success": False,
                "message": "Cannot enable availability during an active visit",
                "errors": {"is_available": ["Complete your current visit before changing availability"]},
            }

    manual_enabled = int(m.get("manual_availability_enabled") or 0)
    if changed_by == "caretaker":
        manual_enabled = 1 if available else 0

    db.execute(
        text(
            "UPDATE caretaker_profiles "
            "SET is_available = :is_available, "
            "    manual_availability_enabled = :manual_enabled, "
            "    availability_reason = :reason, "
            "    availability_changed_at = NOW(), "
            "    availability_changed_by = :changed_by, "
            "    availability_updated_at = NOW(), "
            "    availability_version = availability_version + 1, "
            "    last_active_at = NOW() "
            "WHERE user_id = :cid"
        ),
        {
            "is_available": 1 if available else 0,
            "manual_enabled": manual_enabled,
            "reason": reason,
            "changed_by": changed_by,
            "cid": int(caretaker_user_id),
        },
    )
    db.commit()

    updated = db.execute(
        text(
            "SELECT is_available, manual_availability_enabled, availability_reason, "
            "       availability_updated_at, availability_changed_at, "
            "       availability_changed_by, availability_version, last_active_at "
            "FROM caretaker_profiles "
            "WHERE user_id = :cid"
        ),
        {"cid": int(caretaker_user_id)},
    ).fetchone()

    u_map = updated._mapping if updated else {}
    new_version = int(u_map.get("availability_version") or (old_version + 1))

    # Audit log
    actor = actor_user_id if actor_user_id is not None else caretaker_user_id
    action = f"availability_{changed_by}_{'on' if available else 'off'}"
    audit_log(
        db=db,
        admin_user_id=actor,
        action=action,
        entity_type="caretaker_profile",
        entity_id=caretaker_user_id,
        old_values={
            "is_available": old_available,
            "availability_reason": old_reason,
            "availability_version": old_version,
            "booking_id": booking_id,
        },
        new_values={
            "is_available": available,
            "availability_reason": reason,
            "availability_version": new_version,
            "booking_id": booking_id,
        },
    )

    up_at = u_map.get("availability_updated_at")
    ch_at = u_map.get("availability_changed_at")
    la_at = u_map.get("last_active_at")

    return {
        "success": True,
        "message": "Availability updated",
        "old_value": old_available,
        "data": {
            "is_available": int(u_map.get("is_available") or 0) == 1,
            "manual_availability_enabled": int(u_map.get("manual_availability_enabled") or 0) == 1,
            "availability_reason": u_map.get("availability_reason") or reason,
            "availability_updated_at": up_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(up_at, "strftime") else (str(up_at) if up_at else None),
            "availability_changed_at": ch_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ch_at, "strftime") else (str(ch_at) if ch_at else None),
            "availability_changed_by": u_map.get("availability_changed_by") or changed_by,
            "availability_version": new_version,
            "last_active_at": la_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(la_at, "strftime") else (str(la_at) if la_at else None),
        },
    }


def admin_set_caretaker_availability(
    db: Session,
    caretaker_user_id: int,
    available: bool,
    lock_availability: bool,
    note: Optional[str],
    reason: str,
    admin_user_id: int,
) -> Dict[str, Any]:
    """
    Route: admin_set_caretaker_availability() — helpers/availability L441-538
    """
    row = db.execute(
        text(
            "SELECT u.id, u.is_active, "
            "       cp.is_available, cp.manual_availability_enabled, "
            "       cp.availability_reason, cp.availability_locked_by_admin, "
            "       cp.availability_version, cp.verification_status "
            "FROM users u "
            "INNER JOIN caretaker_profiles cp ON cp.user_id = u.id "
            "WHERE u.id = :cid AND u.role = 'caretaker' "
            "LIMIT 1"
        ),
        {"cid": int(caretaker_user_id)},
    ).fetchone()

    if not row:
        return {
            "success": False,
            "message": "Caretaker not found",
            "errors": {"caretaker_user_id": ["Caretaker profile was not found"]},
        }

    m = row._mapping
    old_available = int(m.get("is_available") or 0) == 1
    old_reason = m.get("availability_reason") or "manual_off"
    old_locked = int(m.get("availability_locked_by_admin") or 0) == 1

    reason_enum = "admin_forced_on" if available else "admin_forced_off"

    db.execute(
        text(
            "UPDATE caretaker_profiles "
            "SET is_available = :is_available, "
            "    availability_reason = :reason_enum, "
            "    availability_locked_by_admin = :lock_val, "
            "    availability_locked_note = :note, "
            "    availability_locked_at = IF(:lock_val = 1, NOW(), availability_locked_at), "
            "    availability_locked_by_user_id = IF(:lock_val = 1, :admin_id, availability_locked_by_user_id), "
            "    availability_changed_at = NOW(), "
            "    availability_changed_by = 'admin', "
            "    availability_updated_at = NOW(), "
            "    availability_version = availability_version + 1, "
            "    last_active_at = NOW() "
            "WHERE user_id = :cid"
        ),
        {
            "is_available": 1 if available else 0,
            "reason_enum": reason_enum,
            "lock_val": 1 if lock_availability else 0,
            "note": note,
            "admin_id": int(admin_user_id),
            "cid": int(caretaker_user_id),
        },
    )

    if not lock_availability:
        db.execute(
            text(
                "UPDATE caretaker_profiles "
                "SET availability_locked_at = NULL, "
                "    availability_locked_by_user_id = NULL, "
                "    availability_locked_note = NULL "
                "WHERE user_id = :cid "
                "  AND availability_locked_by_admin = 0"
            ),
            {"cid": int(caretaker_user_id)},
        )

    db.commit()

    audit_log(
        db=db,
        admin_user_id=admin_user_id,
        action="admin_availability_override",
        entity_type="caretaker_profile",
        entity_id=caretaker_user_id,
        old_values={
            "is_available": old_available,
            "availability_reason": old_reason,
            "availability_locked_by_admin": old_locked,
            "admin_reason": reason,
        },
        new_values={
            "is_available": available,
            "availability_reason": reason_enum,
            "availability_locked_by_admin": lock_availability,
            "note": note,
            "admin_reason": reason,
        },
    )

    payload = caretaker_availability_payload(db, caretaker_user_id)

    return {
        "success": True,
        "message": "Caretaker availability updated by admin",
        "data": payload,
    }


def force_caretaker_unavailable_for_visit(
    db: Session, caretaker_user_id: int, booking_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Route: force_caretaker_unavailable_for_visit() — helpers/availability L222-262
    Force caretaker unavailable when a visit check-in occurs.
    Preserves manual_availability_enabled so it can be restored later.
    """
    row = db.execute(
        text(
            "SELECT manual_availability_enabled, is_available, availability_reason, "
            "       availability_version "
            "FROM caretaker_profiles "
            "WHERE user_id = :cid"
        ),
        {"cid": int(caretaker_user_id)},
    ).fetchone()

    old_available = (int(row._mapping["is_available"] or 0) == 1) if row else False
    old_reason = (row._mapping["availability_reason"] if row else None) or "manual_off"
    old_version = int(row._mapping["availability_version"] or 1) if row else 1

    db.execute(
        text(
            "UPDATE caretaker_profiles "
            "SET is_available = 0, "
            "    availability_reason = 'on_visit', "
            "    availability_changed_at = NOW(), "
            "    availability_changed_by = 'system', "
            "    availability_updated_at = NOW(), "
            "    availability_version = availability_version + 1, "
            "    last_active_at = NOW() "
            "WHERE user_id = :cid"
        ),
        {"cid": int(caretaker_user_id)},
    )

    audit_log(
        db=db,
        admin_user_id=caretaker_user_id,
        action="availability_visit_disable",
        entity_type="caretaker_profile",
        entity_id=caretaker_user_id,
        old_values={
            "is_available": old_available,
            "availability_reason": old_reason,
            "booking_id": booking_id,
        },
        new_values={
            "is_available": False,
            "availability_reason": "on_visit",
            "booking_id": booking_id,
        },
    )

    return {"success": True, "message": "Caretaker forced unavailable for visit"}


def restore_caretaker_availability_after_visit(
    db: Session, caretaker_user_id: int, booking_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Route: restore_caretaker_availability_after_visit() — helpers/availability L268-337
    Restore caretaker availability after visit completion.
    Only restores if manual_availability_enabled = 1 AND no admin lock.
    """
    row = db.execute(
        text(
            "SELECT manual_availability_enabled, is_available, availability_reason, "
            "       availability_locked_by_admin, availability_version, "
            "       verification_status "
            "FROM caretaker_profiles "
            "WHERE user_id = :cid"
        ),
        {"cid": int(caretaker_user_id)},
    ).fetchone()

    if not row:
        return {"success": False, "message": "Caretaker profile not found"}

    m = row._mapping
    can_restore = (
        int(m.get("manual_availability_enabled") or 0) == 1
        and int(m.get("availability_locked_by_admin") or 0) == 0
        and m.get("verification_status") == "approved"
        and not caretaker_has_active_visit(db, caretaker_user_id)
    )

    if can_restore:
        db.execute(
            text(
                "UPDATE caretaker_profiles "
                "SET is_available = 1, "
                "    availability_reason = 'manual_on', "
                "    availability_changed_at = NOW(), "
                "    availability_changed_by = 'system', "
                "    availability_auto_restored_at = NOW(), "
                "    availability_updated_at = NOW(), "
                "    availability_version = availability_version + 1, "
                "    last_active_at = NOW() "
                "WHERE user_id = :cid"
            ),
            {"cid": int(caretaker_user_id)},
        )

        audit_log(
            db=db,
            admin_user_id=caretaker_user_id,
            action="availability_auto_restore",
            entity_type="caretaker_profile",
            entity_id=caretaker_user_id,
            old_values={
                "is_available": False,
                "availability_reason": m.get("availability_reason"),
                "booking_id": booking_id,
            },
            new_values={
                "is_available": True,
                "availability_reason": "manual_on",
                "booking_id": booking_id,
            },
        )

        return {"success": True, "message": "Availability auto-restored", "restored": True}

    if m.get("availability_reason") == "on_visit":
        new_reason = "manual_off"
        if int(m.get("availability_locked_by_admin") or 0) == 1:
            new_reason = "admin_forced_off"

        db.execute(
            text(
                "UPDATE caretaker_profiles "
                "SET availability_reason = :new_reason, "
                "    availability_changed_at = NOW(), "
                "    availability_changed_by = 'system', "
                "    availability_version = availability_version + 1, "
                "    last_active_at = NOW() "
                "WHERE user_id = :cid"
            ),
            {"new_reason": new_reason, "cid": int(caretaker_user_id)},
        )

    return {
        "success": True,
        "message": "Visit ended; availability not restored (manual preference off or admin lock)",
        "restored": False,
    }

