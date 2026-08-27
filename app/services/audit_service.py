"""
WeCare — Audit Service (STEP 9)

Mirrors helpers/audit audit_log() function.
Inserts into admin_audit_logs table.
"""

import json
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def audit_log(
    db: Session,
    admin_user_id: int,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    old_values: Any = None,
    new_values: Any = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """
    Route: audit_log() — audit L5-25
    """
    db.execute(
        text(
            "INSERT INTO admin_audit_logs "
            "(admin_user_id, action, entity_type, entity_id, old_values, new_values, ip_address, user_agent) "
            "VALUES (:admin_user_id, :action, :entity_type, :entity_id, :old_values, :new_values, :ip_address, :user_agent)"
        ),
        {
            "admin_user_id": admin_user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "old_values": json.dumps(old_values, default=str) if old_values else None,
            "new_values": json.dumps(new_values, default=str) if new_values else None,
            "ip_address": ip_address,
            "user_agent": user_agent,
        },
    )
    db.commit()
