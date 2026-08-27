"""
WeCare — Payment & Refund API Router (Part 10)
Provides canonical and legacy  routes for payments and read-only refund queries.
"""

from typing import Any, Dict, Optional, Union
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_family
from app.schemas.payment import PayAdvanceRequest, PayRemainingRequest
from app.services import payment_service

router = APIRouter(tags=["Payments"])


# ── Pay Advance ─────────────────────────────────────────────────────────────

async def _handle_pay_advance(
    request: Request,
    payload: Optional[PayAdvanceRequest] = None,
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    booking_id = body.get("booking_id") if "booking_id" in body else (payload.booking_id if payload else None)
    payment_method = body.get("payment_method") if "payment_method" in body else (payload.payment_method if payload else None)
    transaction_id = body.get("transaction_id") if "transaction_id" in body else (payload.transaction_id if payload else None)
    idempotency_key = payment_service.payment_idempotency_key(body, dict(request.headers))

    data = payment_service.pay_advance(
        db=db,
        family_user=current_user,
        booking_id=booking_id,
        payment_method=payment_method,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
    )
    return success_response(data=data, message="Advance payment successful", status_code=201)


@router.post("/pay_advance")
async def pay_advance_canonical(
    request: Request,
    payload: Optional[PayAdvanceRequest] = None,
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_pay_advance(request, payload, current_user, db)
async def _handle_pay_remaining(
    request: Request,
    payload: Optional[PayRemainingRequest] = None,
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass

    booking_id = body.get("booking_id") if "booking_id" in body else (payload.booking_id if payload else None)
    payment_method = body.get("payment_method") if "payment_method" in body else (payload.payment_method if payload else None)
    transaction_id = body.get("transaction_id") if "transaction_id" in body else (payload.transaction_id if payload else None)
    idempotency_key = payment_service.payment_idempotency_key(body, dict(request.headers))

    data = payment_service.pay_remaining(
        db=db,
        family_user=current_user,
        booking_id=booking_id,
        payment_method=payment_method,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
    )
    return success_response(data=data, message="Remaining payment successful", status_code=201)


@router.post("/pay_remaining")
async def pay_remaining_canonical(
    request: Request,
    payload: Optional[PayRemainingRequest] = None,
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return await _handle_pay_remaining(request, payload, current_user, db)
def _handle_payment_history(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = payment_service.get_payment_history(
        db=db,
        family_user=current_user,
        page=page,
        limit=limit,
    )
    return success_response(data=data, message="Payment history retrieved")


@router.get("/payment_history")
def payment_history_canonical(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return _handle_payment_history(page, limit, current_user, db)
def _handle_payment_summary(
    booking_id: Optional[Union[int, str]] = Query(None),
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = payment_service.get_payment_summary(
        db=db,
        family_user=current_user,
        booking_id=booking_id,
    )
    return success_response(data=data, message="Payment summary retrieved")


@router.get("/payment_summary")
def payment_summary_canonical(
    booking_id: Optional[Union[int, str]] = Query(None),
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return _handle_payment_summary(booking_id, current_user, db)
def _handle_my_refunds(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = payment_service.get_my_refunds(
        db=db,
        family_user=current_user,
        status=status,
        page=page,
        limit=limit,
    )
    return success_response(data=data, message="My refunds retrieved")


@router.get("/my_refunds")
def my_refunds_canonical(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return _handle_my_refunds(status, page, limit, current_user, db)
def _handle_refund_detail(
    id: Optional[Union[int, str]] = Query(None),
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = payment_service.get_refund_detail(
        db=db,
        family_user=current_user,
        refund_id=id,
    )
    return success_response(data=data, message="Refund detail retrieved")


@router.get("/refund_detail")
def refund_detail_canonical(
    id: Optional[Union[int, str]] = Query(None),
    current_user: Any = Depends(require_family),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return _handle_refund_detail(id, current_user, db)
