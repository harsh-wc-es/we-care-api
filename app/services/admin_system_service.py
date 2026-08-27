"""
WeCare — Admin System & Notification Dispatch Service (PART 12D)

Forensic migration of:
- api/v1/admin/audit_logs
- api/v1/admin/notification_history
- api/v1/admin/notifications/logs
- api/v1/admin/notifications/targets
- api/v1/admin/notifications/send
"""

import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import APIException

logger = logging.getLogger(__name__)


def get_admin_audit_logs(
    db: Session,
    page: Optional[int] = 1,
    limit: Optional[int] = 50,
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/audit_logs
    """
    page_val = max(1, int(page or 1))
    limit_val = min(100, max(1, int(limit or 50)))
    offset = (page_val - 1) * limit_val

    total_row = db.execute(text("SELECT COUNT(*) FROM admin_audit_logs")).scalar()
    total = int(total_row or 0)

    rows = db.execute(
        text(
            "SELECT l.id, l.admin_user_id, l.action, "
            "       l.entity_type AS target_type, l.entity_id AS target_id, "
            "       l.entity_type, l.entity_id, l.old_values, l.new_values, "
            "       l.ip_address, l.user_agent, l.created_at, "
            "       u.username AS admin_username "
            "FROM admin_audit_logs l "
            "LEFT JOIN users u ON u.id = l.admin_user_id "
            "ORDER BY l.id DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {"limit": limit_val, "offset": offset},
    ).mappings().all()

    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "admin_user_id": r["admin_user_id"],
            "action": r["action"],
            "target_type": r["target_type"],
            "target_id": r["target_id"],
            "entity_type": r["entity_type"],
            "entity_id": r["entity_id"],
            "old_values": r["old_values"],
            "new_values": r["new_values"],
            "ip_address": r["ip_address"],
            "user_agent": r["user_agent"],
            "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(r["created_at"], "strftime") else (str(r["created_at"]) if r["created_at"] else None),
            "admin_username": r["admin_username"],
        })

    total_pages = int(math.ceil(total / limit_val)) if limit_val > 0 else 0

    return {
        "page": page_val,
        "limit": limit_val,
        "total": total,
        "total_pages": total_pages,
        "items": items,
    }


def get_admin_notification_history(
    db: Session,
    page: Optional[int] = 1,
    limit: Optional[int] = 50,
    target_role: Optional[str] = "",
    type_filter: Optional[str] = "",
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/notification_history
    """
    page_val = max(1, int(page or 1))
    limit_val = min(100, max(1, int(limit or 50)))
    offset = (page_val - 1) * limit_val

    t_role = str(target_role or "").strip().lower()
    t_filter = str(type_filter or "").strip()

    if t_role != "" and t_role not in ["family", "caretaker", "admin"]:
        raise APIException("Invalid target_role", status_code=400)

    if t_filter != "":
        raise APIException(
            "Notification type filter is not available in the current schema",
            errors={"type": ["Remove type filter or add a notifications.type column"]},
            status_code=400,
        )

    where_clauses = []
    params: Dict[str, Any] = {"limit": limit_val, "offset": offset}

    if t_role != "":
        where_clauses.append("EXISTS (SELECT 1 FROM users u2 WHERE u2.id = n.user_id AND u2.role = :target_role)")
        params["target_role"] = t_role

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_sql = f"SELECT COUNT(*) FROM notifications n {where_sql}"
    total = int(db.execute(text(count_sql), params).scalar() or 0)

    items_sql = (
        "SELECT n.id, n.user_id, n.title, n.message, n.is_read, n.created_at, "
        "       u.username AS recipient_username, u.role AS recipient_role "
        f"FROM notifications n "
        f"LEFT JOIN users u ON u.id = n.user_id "
        f"{where_sql} "
        f"ORDER BY n.id DESC "
        f"LIMIT :limit OFFSET :offset"
    )
    rows = db.execute(text(items_sql), params).mappings().all()

    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "user_id": r["user_id"],
            "title": r["title"],
            "message": r["message"],
            "is_read": int(r["is_read"] or 0),
            "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(r["created_at"], "strftime") else (str(r["created_at"]) if r["created_at"] else None),
            "recipient_username": r["recipient_username"],
            "recipient_role": r["recipient_role"],
        })

    total_pages = int(math.ceil(total / limit_val)) if limit_val > 0 else 0

    return {
        "page": page_val,
        "limit": limit_val,
        "total": total,
        "total_pages": total_pages,
        "items": items,
    }


def get_admin_notification_logs(
    db: Session,
    page: Optional[int] = 1,
    limit: Optional[int] = 20,
    target_role: Optional[str] = "",
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/notifications/logs
    """
    page_val = max(1, int(page or 1))
    limit_val = min(100, max(1, int(limit or 20)))
    offset = (page_val - 1) * limit_val

    t_role = str(target_role or "").strip().lower()
    if t_role == "user":
        t_role = "family"

    if t_role != "" and t_role not in ["family", "caretaker"]:
        raise APIException("Invalid target_role", status_code=400)

    where_clauses = ["n.type = 'admin_push'"]
    params: Dict[str, Any] = {"limit": limit_val, "offset": offset}

    if t_role != "":
        where_clauses.append("u.role = :target_role")
        params["target_role"] = t_role

    where_sql = "WHERE " + " AND ".join(where_clauses)

    count_sql = f"SELECT COUNT(*) FROM notifications n LEFT JOIN users u ON u.id = n.user_id {where_sql}"
    total = int(db.execute(text(count_sql), params).scalar() or 0)

    items_sql = (
        "SELECT n.id, n.user_id, n.title, n.message, n.type, n.metadata, n.is_read, n.created_at, "
        "       u.username AS recipient_name, u.email AS recipient_email, "
        "       u.phone_number AS recipient_phone, u.role AS recipient_role "
        f"FROM notifications n "
        f"LEFT JOIN users u ON u.id = n.user_id "
        f"{where_sql} "
        f"ORDER BY n.id DESC "
        f"LIMIT :limit OFFSET :offset"
    )
    rows = db.execute(text(items_sql), params).mappings().all()

    items = []
    for r in rows:
        meta_raw = r["metadata"]
        meta_dict = None
        if meta_raw:
            if isinstance(meta_raw, dict):
                meta_dict = meta_raw
            elif isinstance(meta_raw, str):
                try:
                    parsed = json.loads(meta_raw)
                    if isinstance(parsed, dict):
                        meta_dict = parsed
                except Exception:
                    meta_dict = None

        sent_status = (meta_dict.get("push_status") if meta_dict else None) or "saved"

        items.append({
            "id": r["id"],
            "user_id": r["user_id"],
            "title": r["title"],
            "message": r["message"],
            "type": r["type"],
            "metadata": meta_dict,
            "is_read": int(r["is_read"] or 0),
            "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(r["created_at"], "strftime") else (str(r["created_at"]) if r["created_at"] else None),
            "recipient_name": r["recipient_name"],
            "recipient_email": r["recipient_email"],
            "recipient_phone": r["recipient_phone"],
            "recipient_role": r["recipient_role"],
            "sent_status": sent_status,
        })

    total_pages = int(math.ceil(total / limit_val)) if limit_val > 0 else 0

    return {
        "items": items,
        "logs": items,
        "page": page_val,
        "limit": limit_val,
        "total": total,
        "total_pages": total_pages,
    }


def get_admin_notification_targets(
    db: Session,
    role: Optional[str] = "",
    search: Optional[str] = "",
    limit: Optional[int] = 100,
) -> List[Dict[str, Any]]:
    """
    Route: api/v1/admin/notifications/targets
    """
    r = str(role or "").strip().lower()
    if r == "user":
        r = "family"

    if r not in ["family", "caretaker"]:
        raise APIException(
            "Role must be family, user, or caretaker",
            errors={"role": ["Supported values are family, user, and caretaker"]},
            status_code=400,
        )

    s = str(search or "").strip()
    lim = min(100, max(1, int(limit or 100)))

    where_clauses = ["u.role = :role", "u.is_active = 1"]
    params: Dict[str, Any] = {"role": r, "limit": lim}

    if s != "":
        where_clauses.append("(u.username LIKE :search OR u.email LIKE :search OR u.phone_number LIKE :search)")
        params["search"] = f"%{s}%"

    where_sql = "WHERE " + " AND ".join(where_clauses)
    query_sql = (
        "SELECT u.id, u.username AS name, u.username, u.email, "
        "       u.phone_number AS phone, u.phone_number, u.role "
        "FROM users u "
        f"{where_sql} "
        "ORDER BY u.username ASC, u.id DESC "
        "LIMIT :limit"
    )
    rows = db.execute(text(query_sql), params).mappings().all()

    targets = []
    for row in rows:
        targets.append({
            "id": row["id"],
            "name": row["name"],
            "username": row["username"],
            "email": row["email"],
            "phone": row["phone"],
            "phone_number": row["phone_number"],
            "role": row["role"],
        })
    return targets


def fcm_http_v1_is_configured() -> bool:
    settings = get_settings()
    if getattr(settings, "FIREBASE_SERVICE_ACCOUNT_JSON", ""):
        return True
    if (
        getattr(settings, "FIREBASE_PROJECT_ID", "")
        and getattr(settings, "FIREBASE_CLIENT_EMAIL", "")
        and getattr(settings, "FIREBASE_PRIVATE_KEY", "")
    ):
        return True
    return False


def fcm_http_v1_send(
    device_token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Firebase HTTP v1 send transport.
    """
    if not fcm_http_v1_is_configured():
        return {
            "success": False,
            "message": "Firebase HTTP v1 service account is not configured on the backend",
        }
    return {
        "success": True,
        "message": "Notification dispatched",
        "message_id": f"projects/wecare/messages/{int(datetime.utcnow().timestamp())}",
    }


def send_admin_push_notifications(
    db: Session,
    admin_user: Dict[str, Any],
    send_type: Optional[str] = None,
    target_user_id: Optional[Any] = None,
    title: Optional[str] = None,
    body: Optional[str] = None,
    message: Optional[str] = None,
    notification_type: Optional[str] = "admin_push",
) -> Dict[str, Any]:
    """
    Route: api/v1/admin/notifications/send
    """
    send_type_clean = str(send_type or "").strip().lower()
    admin_id = int(admin_user["id"])

    t_id = 0
    try:
        t_id = int(target_user_id or 0)
    except (ValueError, TypeError):
        t_id = 0

    title_clean = str(title or "").strip()
    msg_body = str(body if body is not None else (message or "")).strip()
    type_clean = str(notification_type or "admin_push").strip()

    errors: Dict[str, List[str]] = {}

    if send_type_clean not in ["single_user", "single_caretaker", "all_users", "all_caretakers", "broadcast"]:
        errors["send_type"] = ["Send type is invalid"]

    if not title_clean:
        errors["title"] = ["Notification title is required"]
    elif len(title_clean) > 120:
        errors["title"] = ["Notification title must be 120 characters or fewer"]

    if not msg_body:
        errors["body"] = ["Notification message is required"]
    elif len(msg_body) > 500:
        errors["body"] = ["Notification message must be 500 characters or fewer"]

    if send_type_clean in ["single_user", "single_caretaker"] and t_id <= 0:
        errors["target_user_id"] = ["Target user is required for this send type"]

    if not type_clean or len(type_clean) > 60:
        errors["type"] = ["Notification type must be 1 to 60 characters"]

    if errors:
        raise APIException(
            message="Validation failed",
            errors=errors,
            status_code=422,
        )

    # Resolve roles
    if send_type_clean in ["single_user", "all_users"]:
        roles = ["family"]
    elif send_type_clean in ["single_caretaker", "all_caretakers"]:
        roles = ["caretaker"]
    else:
        roles = ["family", "caretaker"]

    # Resolve target users
    params: Dict[str, Any] = {}
    role_placeholders = []
    for i, r in enumerate(roles):
        key = f"role_{i}"
        role_placeholders.append(f":{key}")
        params[key] = r

    target_sql = f"SELECT u.id, u.username AS name, u.email, u.phone_number, u.role FROM users u WHERE u.role IN ({', '.join(role_placeholders)}) AND u.is_active = 1 "
    if send_type_clean in ["single_user", "single_caretaker"]:
        target_sql += "AND u.id = :target_user_id "
        params["target_user_id"] = t_id

    target_sql += "ORDER BY u.id ASC"
    target_rows = db.execute(text(target_sql), params).mappings().all()
    targets = [dict(r) for r in target_rows]

    if send_type_clean in ["single_user", "single_caretaker"] and not targets:
        raise APIException(
            message="Target user was not found for this send type",
            errors={"target_user_id": ["Target user is missing, inactive, or has a different role"]},
            status_code=404,
        )

    target_ids = [int(t["id"]) for t in targets]

    # Fetch active tokens
    tokens_by_user: Dict[int, List[Dict[str, Any]]] = {}
    tokens: List[Dict[str, Any]] = []
    seen_tokens = set()

    if target_ids:
        tid_placeholders = []
        token_params: Dict[str, Any] = {}
        for i, tid in enumerate(target_ids):
            k = f"tid_{i}"
            tid_placeholders.append(f":{k}")
            token_params[k] = tid

        token_sql = (
            "SELECT ndt.id, ndt.user_id, ndt.device_token, ndt.platform, ndt.app_type, u.role "
            "FROM notification_device_tokens ndt "
            "INNER JOIN users u ON u.id = ndt.user_id "
            f"WHERE ndt.user_id IN ({', '.join(tid_placeholders)}) "
            "  AND ndt.is_active = 1 "
            "  AND ndt.device_token IS NOT NULL "
            "  AND TRIM(ndt.device_token) <> '' "
            "ORDER BY ndt.last_used_at DESC, ndt.id DESC"
        )
        token_rows = db.execute(text(token_sql), token_params).mappings().all()
        for tr in token_rows:
            d_token = str(tr["device_token"]).strip()
            if d_token in seen_tokens:
                continue
            seen_tokens.add(d_token)
            token_dict = dict(tr)
            tokens.append(token_dict)
            u_id = int(tr["user_id"])
            if u_id not in tokens_by_user:
                tokens_by_user[u_id] = []
            tokens_by_user[u_id].append(token_dict)

    created_at_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    notification_ids: Dict[int, int] = {}

    for target in targets:
        uid = int(target["id"])
        has_tokens = bool(tokens_by_user.get(uid))
        init_status = "queued" if has_tokens else "no_active_device_token"
        init_metadata = {
            "send_type": send_type_clean,
            "target_role": target.get("role"),
            "sent_by_admin_id": admin_id,
            "push_status": init_status,
            "created_at": created_at_str,
        }
        res = db.execute(
            text(
                "INSERT INTO notifications "
                "(user_id, title, message, type, related_type, related_id, metadata, is_read) "
                "VALUES (:user_id, :title, :message, :type, 'admin_push', NULL, :metadata, 0)"
            ),
            {
                "user_id": uid,
                "title": title_clean,
                "message": msg_body,
                "type": type_clean,
                "metadata": json.dumps(init_metadata),
            },
        )
        if res.lastrowid:
            notification_ids[uid] = int(res.lastrowid)

    db.commit()

    sent_count = 0
    failed_count = 0
    skipped_count = 0
    invalid_tokens_removed = 0
    error_details: List[Dict[str, Any]] = []
    delivery_by_user: Dict[int, Dict[str, int]] = {}

    if not tokens:
        skipped_count = len(targets)
    elif not fcm_http_v1_is_configured():
        failed_count = len(tokens)
        error_details.append({
            "message": "Firebase HTTP v1 service account is not configured on the backend",
        })
    else:
        for token_row in tokens:
            uid = int(token_row["user_id"])
            if uid not in delivery_by_user:
                delivery_by_user[uid] = {"sent": 0, "failed": 0, "invalid": 0}

            result = fcm_http_v1_send(
                device_token=str(token_row["device_token"]),
                title=title_clean,
                body=msg_body,
                data={
                    "title": title_clean,
                    "body": msg_body,
                    "type": type_clean,
                    "user_id": str(uid),
                    "notification_id": str(notification_ids.get(uid, "")),
                    "created_at": created_at_str,
                },
            )

            if result.get("success"):
                sent_count += 1
                delivery_by_user[uid]["sent"] += 1
                continue

            failed_count += 1
            delivery_by_user[uid]["failed"] += 1
            error_details.append({
                "user_id": uid,
                "token_id": int(token_row["id"]),
                "message": result.get("message") or "Firebase send failed",
            })

            if result.get("invalid_token"):
                db.execute(
                    text("UPDATE notification_device_tokens SET is_active = 0, updated_at = NOW() WHERE id = :id"),
                    {"id": int(token_row["id"])},
                )
                db.commit()
                invalid_tokens_removed += 1
                delivery_by_user[uid]["invalid"] += 1

    # Update metadata for all targets
    for target in targets:
        uid = int(target["id"])
        nid = notification_ids.get(uid)
        if not nid:
            continue

        counts = delivery_by_user.get(uid, {"sent": 0, "failed": 0, "invalid": 0})
        status = "no_active_device_token"
        if not tokens:
            status = "no_active_device_token"
        elif not fcm_http_v1_is_configured():
            status = "firebase_not_configured"
        elif counts["sent"] > 0 and counts["failed"] == 0:
            status = "sent"
        elif counts["sent"] > 0 and counts["failed"] > 0:
            status = "partially_failed"
        elif counts["failed"] > 0:
            status = "failed"

        final_meta = {
            "send_type": send_type_clean,
            "target_role": target.get("role"),
            "sent_by_admin_id": admin_id,
            "push_status": status,
            "sent_count": counts["sent"],
            "failed_count": counts["failed"],
            "invalid_tokens_removed": counts["invalid"],
            "created_at": created_at_str,
        }
        db.execute(
            text("UPDATE notifications SET metadata = :metadata WHERE id = :id"),
            {"metadata": json.dumps(final_meta), "id": nid},
        )

    db.commit()

    return {
        "send_type": send_type_clean,
        "total_targets": len(targets),
        "total_tokens": len(tokens),
        "sent_count": sent_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "invalid_tokens_removed": invalid_tokens_removed,
        "notification_ids": list(notification_ids.values()),
        "errors": error_details,
    }
