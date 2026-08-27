"""
WeCare — Pricing Tier Service

Mirrors helpers/pricing_tiers.
"""

import re
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session


def pricing_tier_slug(name: str) -> str:
    """
    Route: pricing_tier_slug() — helpers/pricing_tiers L3-10
    """
    slug = str(name).lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug if slug else "pricing-tier"


def calculate_commission(customer_rate: float, caretaker_rate: float) -> Dict[str, float]:
    """
    Route: calculate_commission() — helpers/pricing_tiers L12-23
    """
    platform_commission = round(customer_rate - caretaker_rate, 2)
    commission_percentage = (
        round((platform_commission / customer_rate) * 100, 2)
        if customer_rate > 0
        else 0.00
    )
    return {
        "platform_commission_hourly": platform_commission,
        "commission_percentage": commission_percentage,
    }


def validate_pricing_rates(customer_rate: float, caretaker_rate: float) -> Dict[str, List[str]]:
    """
    Route: validate_pricing_rates() — helpers/pricing_tiers L25-47
    """
    errors: Dict[str, List[str]] = {}
    if customer_rate <= 0:
        errors["customer_hourly_rate"] = ["Customer hourly rate must be greater than 0"]
    if caretaker_rate <= 0:
        errors["caretaker_hourly_rate"] = ["Caretaker hourly rate must be greater than 0"]
    if customer_rate > 0 and caretaker_rate > customer_rate:
        errors["caretaker_hourly_rate"] = ["Caretaker hourly rate cannot exceed customer hourly rate"]

    commission = calculate_commission(customer_rate, caretaker_rate)
    if commission["commission_percentage"] < 0 or commission["commission_percentage"] > 100:
        errors["commission_percentage"] = ["Commission percentage must be between 0 and 100"]

    return errors


def get_pricing_tier(db: Session, tier_id: int) -> Optional[Dict[str, Any]]:
    """
    Route: get_pricing_tier() — helpers/pricing_tiers L49-63
    """
    row = db.execute(
        text(
            "SELECT id, name, slug, description, skill_level, customer_hourly_rate, "
            "       caretaker_hourly_rate, platform_commission_hourly, commission_percentage, "
            "       is_active, created_at, updated_at "
            "FROM pricing_tiers "
            "WHERE id = :tid "
            "LIMIT 1"
        ),
        {"tid": int(tier_id)},
    ).fetchone()

    if not row:
        return None

    m = row._mapping
    cr_at = m.get("created_at")
    up_at = m.get("updated_at")

    return {
        "id": int(m["id"]),
        "name": m["name"],
        "slug": m["slug"],
        "description": m.get("description"),
        "skill_level": m.get("skill_level"),
        "customer_hourly_rate": round(float(m["customer_hourly_rate"]), 2),
        "caretaker_hourly_rate": round(float(m["caretaker_hourly_rate"]), 2),
        "platform_commission_hourly": round(float(m.get("platform_commission_hourly") or 0), 2),
        "commission_percentage": round(float(m.get("commission_percentage") or 0), 2),
        "is_active": bool(int(m.get("is_active") or 0) == 1),
        "created_at": cr_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(cr_at, "strftime") else (str(cr_at) if cr_at else None),
        "updated_at": up_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(up_at, "strftime") else (str(up_at) if up_at else None),
    }


def list_active_pricing_tiers(db: Session) -> List[Dict[str, Any]]:
    """
    Route: list_active_pricing_tiers() — helpers/pricing_tiers L65-77
    """
    rows = db.execute(
        text(
            "SELECT id, name, slug, description, skill_level, customer_hourly_rate, "
            "       caretaker_hourly_rate, platform_commission_hourly, commission_percentage, "
            "       is_active, created_at, updated_at "
            "FROM pricing_tiers "
            "WHERE is_active = 1 "
            "ORDER BY customer_hourly_rate ASC, id ASC"
        )
    ).fetchall()

    results = []
    for r in rows:
        m = r._mapping
        cr_at = m.get("created_at")
        up_at = m.get("updated_at")
        results.append({
            "id": int(m["id"]),
            "name": m["name"],
            "slug": m["slug"],
            "description": m.get("description"),
            "skill_level": m.get("skill_level"),
            "customer_hourly_rate": round(float(m["customer_hourly_rate"]), 2),
            "caretaker_hourly_rate": round(float(m["caretaker_hourly_rate"]), 2),
            "platform_commission_hourly": round(float(m.get("platform_commission_hourly") or 0), 2),
            "commission_percentage": round(float(m.get("commission_percentage") or 0), 2),
            "is_active": bool(int(m.get("is_active") or 0) == 1),
            "created_at": cr_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(cr_at, "strftime") else (str(cr_at) if cr_at else None),
            "updated_at": up_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(up_at, "strftime") else (str(up_at) if up_at else None),
        })
    return results


def apply_pricing_tier_to_caretaker(
    db: Session,
    caretaker_user_id: int,
    tier_id: int,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Route: apply_pricing_tier_to_caretaker() — helpers/pricing_tiers L79-157
    """
    if overrides is None:
        overrides = {}

    tier = get_pricing_tier(db, tier_id)
    if not tier:
        return {
            "success": False,
            "message": "Pricing tier not found",
            "errors": {"pricing_tier_id": ["Pricing tier not found"]},
        }

    if not tier["is_active"]:
        return {
            "success": False,
            "message": "Pricing tier is inactive",
            "errors": {"pricing_tier_id": ["Pricing tier must be active"]},
        }

    override_enabled = bool(overrides.get("pricing_override_enabled"))
    customer_rate = (
        float(overrides.get("customer_hourly_rate") or 0)
        if override_enabled
        else float(tier["customer_hourly_rate"])
    )
    caretaker_rate = (
        float(overrides.get("caretaker_hourly_rate") or 0)
        if override_enabled
        else float(tier["caretaker_hourly_rate"])
    )

    errors = validate_pricing_rates(customer_rate, caretaker_rate)
    if errors:
        return {
            "success": False,
            "message": "Invalid caretaker pricing",
            "errors": errors,
        }

    commission = calculate_commission(customer_rate, caretaker_rate)
    pricing = {
        "pricing_tier_id": tier_id,
        "pricing_tier": tier["slug"],
        "pricing_tier_name": tier["name"],
        "skill_level": tier["skill_level"],
        "customer_hourly_rate": round(customer_rate, 2),
        "caretaker_hourly_rate": round(caretaker_rate, 2),
        "platform_commission_hourly": commission["platform_commission_hourly"],
        "commission_percentage": commission["commission_percentage"],
        "pricing_override_enabled": 1 if override_enabled else 0,
    }

    db.execute(
        text(
            "UPDATE caretaker_profiles "
            "SET pricing_tier_id = :tier_id, "
            "    pricing_tier = :slug, "
            "    skill_level = :skill, "
            "    customer_hourly_rate = :cust_rate, "
            "    caretaker_hourly_rate = :ct_rate, "
            "    platform_commission_hourly = :comm_hr, "
            "    commission_percentage = :comm_pct, "
            "    pricing_override_enabled = :override_en "
            "WHERE user_id = :cid"
        ),
        {
            "tier_id": pricing["pricing_tier_id"],
            "slug": pricing["pricing_tier"],
            "skill": pricing["skill_level"],
            "cust_rate": pricing["customer_hourly_rate"],
            "ct_rate": pricing["caretaker_hourly_rate"],
            "comm_hr": pricing["platform_commission_hourly"],
            "comm_pct": pricing["commission_percentage"],
            "override_en": pricing["pricing_override_enabled"],
            "cid": int(caretaker_user_id),
        },
    )

    return {
        "success": True,
        "tier": tier,
        "pricing": pricing,
    }
