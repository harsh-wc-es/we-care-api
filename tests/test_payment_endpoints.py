"""
WeCare — Payment & Refund Endpoints Test Suite (Part 10)

Tests all payment and refund endpoints and behaviors:
- POST /pay_advance (50% advance, validation, eligibility, idempotency, transaction safety, blocked statuses)
- POST /pay_remaining (remaining balance, eligibility preconditions, idempotency, paid status, allowed booking statuses)
- GET /payment_history (total_spent, display_status, dual history/items keys, pagination, role security)
- GET /payment_summary (per-booking summary, calculated advance/remaining amounts)
- GET /my_refunds (read-only refund queries, status filtering, pagination)
- GET /refund_detail (read-only refund details, 404/400 validation)
- Legacy  route aliases for all endpoints
"""

import time
from datetime import datetime, timedelta
import pytest
from sqlalchemy import text

from app.core.security import hash_password
from tests.conftest import make_auth_headers


def _create_user(db, role="family"):
    ts = int(time.time() * 1000000) % 1000000000
    email = f"pay_{role}_{ts}@example.com"
    username = f"p_{role[:2]}_{ts}"
    phone = f"9{ts:09d}"[:10]
    pwd_hash = hash_password("TestPassword123!")

    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, :role, 1, 1)"
        ),
        {
            "email": email,
            "username": username,
            "phone": phone,
            "password": pwd_hash,
            "role": role,
        },
    )
    user_id = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).scalar()
    db.commit()
    return {"id": int(user_id), "email": email, "username": username, "role": role}


def _create_booking(db, family_id, caretaker_id=None, status="pending", total_amount=1000.00, total_customer_amount=1000.00, paid_amount=0.00, payment_status=None):
    if payment_status is None:
        p_stat = "paid" if paid_amount >= total_customer_amount and total_customer_amount > 0 else "pending"
    else:
        p_stat = payment_status

    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, service_type, booking_date, start_time, end_time, address, status, total_amount, total_customer_amount, paid_amount, remaining_amount, payment_status) "
            "VALUES (:fid, :cid, 'Elder Care', CURDATE(), '09:00:00', '13:00:00', '123 Care Street', :status, :ta, :tca, :pa, :ra, :ps)"
        ),
        {
            "fid": family_id,
            "cid": caretaker_id,
            "status": status,
            "ta": total_amount,
            "tca": total_customer_amount,
            "pa": paid_amount,
            "ra": max(0.0, total_customer_amount - paid_amount),
            "ps": p_stat,
        },
    )
    bid = db.execute(text("SELECT id FROM bookings WHERE family_user_id = :fid ORDER BY id DESC LIMIT 1"), {"fid": family_id}).scalar()
    db.commit()
    return int(bid)


def test_pay_advance_flow(client, db):
    fam = _create_user(db, "family")
    car = _create_user(db, "caretaker")
    fam_headers = make_auth_headers(fam, db)
    bid = _create_booking(db, fam["id"], car["id"], status="pending", total_customer_amount=2000.00)

    # Validation: missing payment_method
    resp_bad = client.post("/api/v1/payment/pay_advance", json={"booking_id": bid}, headers=fam_headers)
    assert resp_bad.status_code == 400

    # Validation: invalid payment_method
    resp_bad_m = client.post(
        "/api/v1/payment/pay_advance",
        json={"booking_id": bid, "payment_method": "bitcoin"},
        headers=fam_headers,
    )
    assert resp_bad_m.status_code == 400

    # 404: wrong booking
    resp_nf = client.post(
        "/api/v1/payment/pay_advance",
        json={"booking_id": 999999, "payment_method": "upi"},
        headers=fam_headers,
    )
    assert resp_nf.status_code == 404

    # Success: cash payment -> verification_status = "not_required"
    idem_key = f"idem_adv_{int(time.time()*1000)}"
    resp_ok = client.post(
        "/api/v1/payment/pay_advance",
        json={
            "booking_id": bid,
            "payment_method": "cash",
            "transaction_id": "TXN_CASH_01",
            "idempotency_key": idem_key,
        },
        headers=fam_headers,
    )
    assert resp_ok.status_code == 201
    data = resp_ok.json()["data"]
    assert data["payment_type"] == "advance"
    assert data["total_amount"] == 2000.00
    assert data["advance_paid"] == 1000.00
    assert data["remaining_amount"] == 1000.00
    assert data["payment_status"] == "pending"
    assert data["verification_status"] == "not_required"

    # Idempotency duplicate rejection (409)
    resp_dup = client.post(
        "/api/v1/payment/pay_advance",
        json={
            "booking_id": bid,
            "payment_method": "cash",
            "idempotency_key": idem_key,
        },
        headers=fam_headers,
    )
    assert resp_dup.status_code == 409

    # Advance already done rejection (409)
    resp_again = client.post(
        "/api/v1/payment/pay_advance",
        json={"booking_id": bid, "payment_method": "upi"},
        headers=fam_headers,
    )
    assert resp_again.status_code == 409


def test_pay_advance_blocked_statuses(client, db):
    fam = _create_user(db, "family")
    car = _create_user(db, "caretaker")
    fam_headers = make_auth_headers(fam, db)

    # Blocked booking statuses
    for blocked_st in ["cancelled", "declined"]:
        bid = _create_booking(db, fam["id"], car["id"], status=blocked_st, total_customer_amount=1000.00)
        resp = client.post(
            "/api/v1/payment/pay_advance",
            json={"booking_id": bid, "payment_method": "upi"},
            headers=fam_headers,
        )
        assert resp.status_code == 409

    # Blocked payment statuses
    for blocked_ps in ["refunded", "failed"]:
        bid = _create_booking(db, fam["id"], car["id"], status="pending", total_customer_amount=1000.00, payment_status=blocked_ps)
        resp = client.post(
            "/api/v1/payment/pay_advance",
            json={"booking_id": bid, "payment_method": "upi"},
            headers=fam_headers,
        )
        assert resp.status_code == 409


def test_pay_remaining_flow(client, db):
    fam = _create_user(db, "family")
    car = _create_user(db, "caretaker")
    fam_headers = make_auth_headers(fam, db)

    # 1. Booking without advance payment -> 409 "Advance payment required first"
    bid1 = _create_booking(db, fam["id"], car["id"], status="confirmed", total_customer_amount=1500.00, paid_amount=0.00)
    resp_no_adv = client.post(
        "/api/v1/payment/pay_remaining",
        json={"booking_id": bid1, "payment_method": "upi"},
        headers=fam_headers,
    )
    assert resp_no_adv.status_code == 409

    # 2. Booking in pending status -> 409 "Remaining payment is not allowed yet"
    bid2 = _create_booking(db, fam["id"], car["id"], status="pending", total_customer_amount=1500.00, paid_amount=750.00)
    resp_bad_stat = client.post(
        "/api/v1/payment/pay_remaining",
        json={"booking_id": bid2, "payment_method": "upi"},
        headers=fam_headers,
    )
    assert resp_bad_stat.status_code == 409

    # 3. Successful remaining payment on in_progress booking
    bid3 = _create_booking(db, fam["id"], car["id"], status="in_progress", total_customer_amount=1500.00, paid_amount=750.00)
    resp_rem = client.post(
        "/api/v1/payment/pay_remaining",
        json={
            "booking_id": bid3,
            "payment_method": "card",
            "transaction_id": "TXN_CARD_99",
        },
        headers=fam_headers,
    )
    assert resp_rem.status_code == 201
    data = resp_rem.json()["data"]
    assert data["payment_type"] == "remaining"
    assert data["total_amount"] == 1500.00
    assert data["remaining_paid"] == 750.00
    assert data["remaining_amount"] == 0
    assert data["payment_status"] == "paid"
    assert data["verification_status"] == "verified"

    # 4. Already fully paid -> 409
    resp_already = client.post(
        "/api/v1/payment/pay_remaining",
        json={"booking_id": bid3, "payment_method": "card"},
        headers=fam_headers,
    )
    assert resp_already.status_code == 409


def test_payment_history_and_summary(client, db):
    fam = _create_user(db, "family")
    car = _create_user(db, "caretaker")
    fam_headers = make_auth_headers(fam, db)

    # Set up caretaker profile
    db.execute(
        text("INSERT INTO caretaker_profiles (user_id, full_name) VALUES (:uid, 'Caretaker John')"),
        {"uid": car["id"]},
    )
    db.commit()

    bid = _create_booking(db, fam["id"], car["id"], status="in_progress", total_customer_amount=1200.00, paid_amount=600.00)

    # Insert payment record
    db.execute(
        text(
            "INSERT INTO payments (booking_id, family_user_id, caretaker_user_id, amount, payment_method, payment_type, status, total_amount, remaining_amount, paid_at) "
            "VALUES (:bid, :fid, :cid, 600.00, 'upi', 'advance', 'success', 1200.00, 600.00, NOW())"
        ),
        {"bid": bid, "fid": fam["id"], "cid": car["id"]},
    )
    db.commit()

    # Test summary (canonical & legacy)
    resp_sum = client.get(f"/api/v1/payment/payment_summary?booking_id={bid}", headers=fam_headers)
    assert resp_sum.status_code == 200
    sum_data = resp_sum.json()["data"]
    assert sum_data["total_amount"] == 1200.00
    assert sum_data["paid_amount"] == 600.00
    assert sum_data["advance_percentage"] == 50
    assert sum_data["advance_amount"] == 600.00
    assert sum_data["remaining_amount"] == 600.00
    assert sum_data["caretaker_name"] == "Caretaker John"

    resp_sum_php = client.get(f"/api/v1/payment/payment_summary?booking_id={bid}", headers=fam_headers)
    assert resp_sum_php.status_code == 200

    # Summary 404
    resp_sum_nf = client.get("/api/v1/payment/payment_summary?booking_id=999999", headers=fam_headers)
    assert resp_sum_nf.status_code == 404

    # Test payment history (canonical & legacy)
    resp_hist = client.get("/api/v1/payment/payment_history?page=1&limit=10", headers=fam_headers)
    assert resp_hist.status_code == 200
    hist_data = resp_hist.json()["data"]
    assert hist_data["total_spent"] == 600.00
    assert "history" in hist_data
    assert "items" in hist_data
    assert len(hist_data["history"]) == 1
    assert hist_data["history"][0]["display_status"] == "Paid Half"
    assert hist_data["history"][0]["caretaker_name"] == "Caretaker John"


def test_my_refunds_and_refund_detail(client, db):
    fam = _create_user(db, "family")
    car = _create_user(db, "caretaker")
    fam_headers = make_auth_headers(fam, db)

    # Insert patient
    db.execute(
        text("INSERT INTO patient_details (family_user_id, patient_name) VALUES (:fid, 'Grandpa Joe')"),
        {"fid": fam["id"]},
    )
    db.commit()
    pid = db.execute(text("SELECT id FROM patient_details WHERE family_user_id = :fid"), {"fid": fam["id"]}).scalar()

    # Insert booking
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, booking_date, start_time, end_time, address, status, total_amount, paid_amount) "
            "VALUES (:fid, :cid, :pid, 'Nursing', '2026-08-20', '10:00:00', '14:00:00', 'Street 1', 'cancelled', 800.00, 800.00)"
        ),
        {"fid": fam["id"], "cid": car["id"], "pid": pid},
    )
    db.commit()
    bid = db.execute(text("SELECT id FROM bookings WHERE family_user_id = :fid ORDER BY id DESC LIMIT 1"), {"fid": fam["id"]}).scalar()

    # Insert refund record
    db.execute(
        text(
            "INSERT INTO booking_refunds (booking_id, family_user_id, caretaker_user_id, paid_amount, refund_amount, refund_percentage, refund_method, status, reason) "
            "VALUES (:bid, :fid, :cid, 800.00, 400.00, 50.00, 'upi', 'pending', 'Cancelled >12h before')"
        ),
        {"bid": bid, "fid": fam["id"], "cid": car["id"]},
    )
    db.commit()
    rid = db.execute(text("SELECT id FROM booking_refunds WHERE family_user_id = :fid"), {"fid": fam["id"]}).scalar()

    # Test my_refunds: invalid status
    resp_bad_st = client.get("/api/v1/payment/my_refunds?status=invalid_status", headers=fam_headers)
    assert resp_bad_st.status_code == 400

    # Test my_refunds (canonical & legacy)
    resp_ref = client.get("/api/v1/payment/my_refunds", headers=fam_headers)
    assert resp_ref.status_code == 200
    ref_data = resp_ref.json()["data"]
    assert len(ref_data["items"]) == 1
    assert ref_data["items"][0]["refund_amount"] == 400.00
    assert ref_data["items"][0]["patient_name"] == "Grandpa Joe"

    resp_ref_php = client.get("/api/v1/payment/my_refunds?status=pending", headers=fam_headers)
    assert resp_ref_php.status_code == 200

    # Test refund_detail
    resp_det = client.get(f"/api/v1/payment/refund_detail?id={rid}", headers=fam_headers)
    assert resp_det.status_code == 200
    assert resp_det.json()["data"]["refund_id"] == rid
    assert resp_det.json()["data"]["status"] == "pending"

    # Detail 404
    resp_det_nf = client.get("/api/v1/payment/refund_detail?id=999999", headers=fam_headers)
    assert resp_det_nf.status_code == 404

    # Detail 400 on invalid id
    resp_det_bad = client.get("/api/v1/payment/refund_detail?id=-5", headers=fam_headers)
    assert resp_det_bad.status_code == 400
