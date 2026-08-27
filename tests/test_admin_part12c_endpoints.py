"""
WeCare — Part 12C Admin Refund Processing Test Suite

Tests all 5 Admin Part 12C endpoints and business rules:
1. GET  /api/v1/admin/refunds (+  alias)
2. GET  /api/v1/admin/refund_detail (+  alias)
3. POST /api/v1/admin/approve_refund (+  alias)
4. POST /api/v1/admin/reject_refund (+  alias)
5. POST /api/v1/admin/mark_refund_processed (+  alias)
"""

import time
import pytest
from datetime import date, datetime, timedelta
from sqlalchemy import text

from app.core.security import hash_password
from tests.conftest import make_auth_headers


def _create_user(db, role="family"):
    ts = int(time.time() * 1000000) % 1000000000
    email = f"adm12c_{role}_{ts}@example.com"
    username = f"u12c_{role[:2]}_{ts}"
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


def _create_caretaker_profile(db, user_id, full_name="Caretaker 12C"):
    db.execute(
        text(
            "INSERT INTO caretaker_profiles (user_id, full_name, gender, date_of_birth, experience_years, "
            "                                hourly_rate, bio, verification_status, is_available, "
            "                                manual_availability_enabled, availability_reason, last_active_at) "
            "VALUES (:uid, :name, 'female', '1990-01-01', 5, 300.00, 'Experienced nurse', "
            "        'approved', 1, 1, 'manual_on', NOW() - INTERVAL 1 HOUR)"
        ),
        {"uid": user_id, "name": full_name},
    )
    db.commit()


def _create_family_profile(db, user_id, full_name="Family 12C"):
    db.execute(
        text(
            "INSERT INTO family_profiles (user_id, full_name, gender, date_of_birth, address, city, state, pincode) "
            "VALUES (:uid, :name, 'male', '1985-05-15', '123 Test Street', 'Mumbai', 'Maharashtra', '400001')"
        ),
        {"uid": user_id, "name": full_name},
    )
    db.commit()


def _create_patient(db, family_user_id, name="Patient 12C"):
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition, care_type) "
            "VALUES (:fid, :name, 75, 'male', 'Hypertension', 'elderly_care') "
            "ON DUPLICATE KEY UPDATE patient_name = :name"
        ),
        {"fid": family_user_id, "name": name},
    )
    pid = db.execute(
        text("SELECT id FROM patient_details WHERE family_user_id = :fid"),
        {"fid": family_user_id},
    ).scalar()
    db.commit()
    return int(pid)


def _create_booking(
    db,
    family_user_id,
    caretaker_user_id,
    patient_id,
    status="cancelled",
    refund_status="pending",
    booking_date="2026-08-25",
    customer_amount=1000.00,
    paid_amount=1000.00,
    refund_amount=500.00,
    refund_percentage=50.00,
):
    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, booking_date, "
            "                      start_time, end_time, total_amount, total_customer_amount, caretaker_earning_amount, "
            "                      platform_commission_amount, paid_amount, remaining_amount, status, payment_status, "
            "                      refund_eligible, refund_percentage, refund_amount, refund_status, created_at, updated_at) "
            "VALUES (:fid, :cid, :pid, 'elderly_care', :bdate, '09:00:00', '13:00:00', :cust_amt, :cust_amt, 800.00, "
            "        200.00, :paid_amt, 0.00, :status, 'paid', 1, :r_pct, :r_amt, :r_status, NOW(), NOW())"
        ),
        {
            "fid": family_user_id,
            "cid": caretaker_user_id,
            "pid": patient_id,
            "bdate": booking_date,
            "cust_amt": customer_amount,
            "paid_amt": paid_amount,
            "status": status,
            "r_pct": refund_percentage,
            "r_amt": refund_amount,
            "r_status": refund_status,
        },
    )
    bid = db.execute(
        text("SELECT id FROM bookings WHERE family_user_id = :fid AND caretaker_user_id = :cid ORDER BY id DESC LIMIT 1"),
        {"fid": family_user_id, "cid": caretaker_user_id},
    ).scalar()
    db.commit()
    return int(bid)


def _create_payment(db, booking_id, family_user_id, caretaker_user_id, amount=1000.00):
    db.execute(
        text(
            "INSERT INTO payments (booking_id, family_user_id, caretaker_user_id, amount, payment_method, status, verification_status, created_at) "
            "VALUES (:bid, :fid, :cid, :amt, 'upi', 'success', 'verified', NOW())"
        ),
        {"bid": booking_id, "fid": family_user_id, "cid": caretaker_user_id, "amt": amount},
    )
    pid = db.execute(
        text("SELECT id FROM payments WHERE booking_id = :bid ORDER BY id DESC LIMIT 1"),
        {"bid": booking_id},
    ).scalar()
    db.commit()
    return int(pid)


def _create_booking_refund(
    db,
    booking_id,
    family_user_id,
    caretaker_user_id,
    payment_id=None,
    paid_amount=1000.00,
    refund_amount=500.00,
    refund_percentage=50.00,
    status="pending",
    reason="Family cancelled 12h prior",
    admin_note=None,
    refund_method=None,
    refund_transaction_id=None,
):
    db.execute(
        text(
            "INSERT INTO booking_refunds (booking_id, family_user_id, caretaker_user_id, payment_id, "
            "                             paid_amount, refund_amount, refund_percentage, refund_method, "
            "                             refund_transaction_id, reason, status, admin_note, created_at, updated_at) "
            "VALUES (:bid, :fid, :cid, :pid, :paid_amt, :ref_amt, :ref_pct, :ref_method, :ref_tx, :reason, :status, :note, NOW(), NOW())"
        ),
        {
            "bid": booking_id,
            "fid": family_user_id,
            "cid": caretaker_user_id,
            "pid": payment_id,
            "paid_amt": paid_amount,
            "ref_amt": refund_amount,
            "ref_pct": refund_percentage,
            "ref_method": refund_method,
            "ref_tx": refund_transaction_id,
            "reason": reason,
            "status": status,
            "note": admin_note,
        },
    )
    rid = db.execute(
        text("SELECT id FROM booking_refunds WHERE booking_id = :bid ORDER BY id DESC LIMIT 1"),
        {"bid": booking_id},
    ).scalar()
    db.commit()
    return int(rid)


def _cleanup_test_data(db, user_ids):
    if not user_ids:
        return
    u_list = ",".join(str(int(u)) for u in user_ids)
    db.execute(text(f"DELETE FROM booking_refunds WHERE family_user_id IN ({u_list}) OR caretaker_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM payments WHERE family_user_id IN ({u_list}) OR caretaker_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM bookings WHERE family_user_id IN ({u_list}) OR caretaker_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM patient_details WHERE family_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM family_profiles WHERE user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM caretaker_profiles WHERE user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM tokens WHERE user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM admin_audit_logs WHERE admin_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM users WHERE id IN ({u_list})"))
    db.commit()


# ══════════════════════════════════════════════════════════════════════
# 1. AUTHENTICATION & RBAC TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_part12c_auth_and_rbac(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        ct_headers = make_auth_headers(caretaker, db)
        fam_headers = make_auth_headers(family, db)

        endpoints = [
            ("GET", "/api/v1/admin/refunds", "/api/v1/admin/refunds", None),
            ("GET", "/api/v1/admin/refund_detail?id=999999", "/api/v1/admin/refund_detail?id=999999", None),
            ("POST", "/api/v1/admin/approve_refund", "/api/v1/admin/approve_refund", {"refund_id": 999999}),
            ("POST", "/api/v1/admin/reject_refund", "/api/v1/admin/reject_refund", {"refund_id": 999999}),
            ("POST", "/api/v1/admin/mark_refund_processed", "/api/v1/admin/mark_refund_processed", {
                "refund_id": 999999,
                "refund_method": "upi",
                "refund_transaction_id": "TXN123"
            }),
        ]

        for method, canonical, alias, body in endpoints:
            for url in [canonical, alias]:
                # 1. Unauthenticated -> 401
                if method == "GET":
                    r_no_auth = client.get(url)
                else:
                    r_no_auth = client.post(url, json=body)
                assert r_no_auth.status_code == 401, f"Expected 401 for {url}, got {r_no_auth.status_code}"
                assert r_no_auth.json()["success"] is False

                # 2. Caretaker -> 403
                if method == "GET":
                    r_ct = client.get(url, headers=ct_headers)
                else:
                    r_ct = client.post(url, json=body, headers=ct_headers)
                assert r_ct.status_code == 403, f"Expected 403 for caretaker on {url}, got {r_ct.status_code}"
                assert r_ct.json()["success"] is False

                # 3. Family -> 403
                if method == "GET":
                    r_fam = client.get(url, headers=fam_headers)
                else:
                    r_fam = client.post(url, json=body, headers=fam_headers)
                assert r_fam.status_code == 403, f"Expected 403 for family on {url}, got {r_fam.status_code}"
                assert r_fam.json()["success"] is False

                # 4. Admin -> Allowed (not 401 or 403)
                if method == "GET":
                    r_adm = client.get(url, headers=admin_headers)
                else:
                    r_adm = client.post(url, json=body, headers=admin_headers)
                assert r_adm.status_code not in [401, 403], f"Admin denied access on {url}: {r_adm.status_code}"

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 2. REFUNDS LIST & SUMMARY TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_refunds_list_and_summary(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        _create_caretaker_profile(db, caretaker["id"], full_name="Refund Caretaker")
        _create_family_profile(db, family["id"], full_name="Refund Family")
        pid = _create_patient(db, family["id"], "Refund Patient Name Unique")

        # Create bookings and refunds in multiple states:
        # 1. Pending
        b1 = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="pending")
        p1 = _create_payment(db, b1, family["id"], caretaker["id"])
        r1 = _create_booking_refund(db, b1, family["id"], caretaker["id"], payment_id=p1, status="pending", refund_amount=400.00)

        # 2. Approved
        b2 = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="pending")
        p2 = _create_payment(db, b2, family["id"], caretaker["id"])
        r2 = _create_booking_refund(db, b2, family["id"], caretaker["id"], payment_id=p2, status="approved", refund_amount=500.00)

        # 3. Rejected
        b3 = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="not_applicable")
        p3 = _create_payment(db, b3, family["id"], caretaker["id"])
        r3 = _create_booking_refund(db, b3, family["id"], caretaker["id"], payment_id=p3, status="rejected", refund_amount=300.00)

        # 4. Processed
        b4 = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="processed")
        p4 = _create_payment(db, b4, family["id"], caretaker["id"])
        r4 = _create_booking_refund(db, b4, family["id"], caretaker["id"], payment_id=p4, status="processed", refund_amount=600.00, refund_method="upi", refund_transaction_id="TXN-PROC-1")

        # Test A: Default list
        res = client.get("/api/v1/admin/refunds", headers=admin_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["message"] == "Refunds retrieved"
        assert "items" in body["data"]
        assert "pagination" in body["data"]
        assert "summary" in body["data"]
        assert body["data"]["pagination"]["page"] == 1
        assert body["data"]["pagination"]["limit"] == 50
        assert body["data"]["pagination"]["total"] >= 4

        # Verify all 5 statuses exist in summary
        summary = body["data"]["summary"]
        for st in ["pending", "approved", "rejected", "processed", "failed"]:
            assert st in summary
            assert "count" in summary[st]
            assert "amount" in summary[st]
            assert isinstance(summary[st]["count"], int)
            assert isinstance(summary[st]["amount"], float)

        # Test B: Filter by status=pending
        res_pending = client.get("/api/v1/admin/refunds?status=pending", headers=admin_headers)
        assert res_pending.status_code == 200
        items_p = res_pending.json()["data"]["items"]
        assert any(it["id"] == r1 for it in items_p)
        assert all(it["status"] == "pending" for it in items_p)

        # Test C: Filter status=all
        res_all = client.get("/api/v1/admin/refunds?status=all", headers=admin_headers)
        assert res_all.status_code == 200
        assert len(res_all.json()["data"]["items"]) >= 4

        # Test D: Invalid status -> 400
        res_bad_status = client.get("/api/v1/admin/refunds?status=unknown_xyz", headers=admin_headers)
        assert res_bad_status.status_code == 400
        b_bad_s = res_bad_status.json()
        assert b_bad_s["message"] == "Validation failed"
        assert "status" in b_bad_s["errors"]
        assert "Status must be one of: pending, approved, rejected, processed, failed, all" in b_bad_s["errors"]["status"][0]

        # Test E: Search by patient name
        res_search = client.get("/api/v1/admin/refunds?search=Refund+Patient+Name+Unique", headers=admin_headers)
        assert res_search.status_code == 200
        assert len(res_search.json()["data"]["items"]) >= 4

        # Test F: Search by refund ID
        res_search_id = client.get(f"/api/v1/admin/refunds?search={r1}", headers=admin_headers)
        assert res_search_id.status_code == 200
        assert any(it["id"] == r1 for it in res_search_id.json()["data"]["items"])

        # Test G: Search by family email
        res_search_email = client.get(f"/api/v1/admin/refunds?search={family['email']}", headers=admin_headers)
        assert res_search_email.status_code == 200
        assert len(res_search_email.json()["data"]["items"]) >= 4

        # Test H: Date filter
        today_str = date.today().strftime("%Y-%m-%d")
        res_date = client.get(f"/api/v1/admin/refunds?date_from={today_str}&date_to={today_str}", headers=admin_headers)
        assert res_date.status_code == 200
        assert len(res_date.json()["data"]["items"]) >= 4

        # Test I: Invalid date_from / date_to format -> 400
        res_bad_df = client.get("/api/v1/admin/refunds?date_from=invalid-date-string", headers=admin_headers)
        assert res_bad_df.status_code == 400
        assert res_bad_df.json()["errors"]["date_from"] == ["date_from must be a valid date"]

        res_bad_dt = client.get("/api/v1/admin/refunds?date_to=invalid-date-string", headers=admin_headers)
        assert res_bad_dt.status_code == 400
        assert res_bad_dt.json()["errors"]["date_to"] == ["date_to must be a valid date"]

        # Test J: Pagination limit clamping (max 100, min 1)
        res_clamp = client.get("/api/v1/admin/refunds?page=0&limit=500", headers=admin_headers)
        assert res_clamp.status_code == 200
        assert res_clamp.json()["data"]["pagination"]["page"] == 1
        assert res_clamp.json()["data"]["pagination"]["limit"] == 100

        # Test K:  alias parity
        res_alias = client.get("/api/v1/admin/refunds", headers=admin_headers)
        assert res_alias.status_code == 200
        assert res_alias.json()["message"] == "Refunds retrieved"

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 3. REFUND DETAIL TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_refund_detail(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        _create_caretaker_profile(db, caretaker["id"], full_name="Detail Caretaker")
        _create_family_profile(db, family["id"], full_name="Detail Family")
        pid = _create_patient(db, family["id"], "Detail Patient")

        bid = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="pending")
        p_id = _create_payment(db, bid, family["id"], caretaker["id"])
        r_id = _create_booking_refund(
            db, bid, family["id"], caretaker["id"],
            payment_id=p_id, paid_amount=1200.00, refund_amount=600.00,
            refund_percentage=50.00, status="pending", reason="Test cancellation refund"
        )

        # Test A: Missing ID -> 400
        res_missing = client.get("/api/v1/admin/refund_detail", headers=admin_headers)
        assert res_missing.status_code == 400
        assert res_missing.json()["message"] == "Invalid refund id"
        assert res_missing.json()["errors"]["id"] == ["Refund id must be a positive integer"]

        # Test B: Invalid ID (0 or negative or non-int) -> 400
        res_zero = client.get("/api/v1/admin/refund_detail?id=0", headers=admin_headers)
        assert res_zero.status_code == 400

        res_str = client.get("/api/v1/admin/refund_detail?id=abc", headers=admin_headers)
        assert res_str.status_code == 400

        # Test C: Nonexistent refund -> 404
        res_404 = client.get("/api/v1/admin/refund_detail?id=999999", headers=admin_headers)
        assert res_404.status_code == 404
        assert res_404.json()["message"] == "Refund not found"

        # Test D: Valid refund detail
        res_valid = client.get(f"/api/v1/admin/refund_detail?id={r_id}", headers=admin_headers)
        assert res_valid.status_code == 200
        body = res_valid.json()
        assert body["success"] is True
        assert body["message"] == "Refund detail retrieved"
        data = body["data"]

        assert data["id"] == r_id
        assert data["booking_id"] == bid
        assert data["payment_id"] == p_id
        assert data["paid_amount"] == 1200.00
        assert data["refund_amount"] == 600.00
        assert data["refund_percentage"] == 50.00
        assert data["status"] == "pending"
        assert data["reason"] == "Test cancellation refund"
        assert data["family"]["id"] == family["id"]
        assert data["family"]["email"] == family["email"]
        assert data["caretaker"]["id"] == caretaker["id"]
        assert data["booking"]["status"] == "cancelled"
        assert data["patient_name"] == "Detail Patient"
        assert "created_at" in data

        # Test E:  alias parity
        res_alias = client.get(f"/api/v1/admin/refund_detail?id={r_id}", headers=admin_headers)
        assert res_alias.status_code == 200
        assert res_alias.json()["data"]["id"] == r_id

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 4. APPROVE REFUND TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_approve_refund_lifecycle(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        _create_caretaker_profile(db, caretaker["id"], full_name="Approve Caretaker")
        _create_family_profile(db, family["id"], full_name="Approve Family")
        pid = _create_patient(db, family["id"], "Approve Patient")

        bid = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="pending")
        p_id = _create_payment(db, bid, family["id"], caretaker["id"])
        r_id = _create_booking_refund(db, bid, family["id"], caretaker["id"], payment_id=p_id, status="pending")

        # Test A: Missing refund_id -> 400
        res_missing = client.post("/api/v1/admin/approve_refund", json={}, headers=admin_headers)
        assert res_missing.status_code == 400
        assert res_missing.json()["message"] == "Validation failed"
        assert res_missing.json()["errors"]["refund_id"] == ["Refund id must be a positive integer"]

        # Test B: Note > 1000 chars -> 400
        res_long_note = client.post(
            "/api/v1/admin/approve_refund",
            json={"refund_id": r_id, "admin_note": "A" * 1001},
            headers=admin_headers,
        )
        assert res_long_note.status_code == 400
        assert res_long_note.json()["errors"]["admin_note"] == ["Admin note must not exceed 1000 characters"]

        # Test C: Nonexistent refund -> 404
        res_404 = client.post(
            "/api/v1/admin/approve_refund",
            json={"refund_id": 999999},
            headers=admin_headers,
        )
        assert res_404.status_code == 404
        assert res_404.json()["message"] == "Refund not found"

        # Test D: Successful approve (pending -> approved)
        res_ok = client.post(
            "/api/v1/admin/approve_refund",
            json={"refund_id": r_id, "admin_note": "Refund verified by admin"},
            headers=admin_headers,
        )
        assert res_ok.status_code == 200
        body = res_ok.json()
        assert body["success"] is True
        assert body["message"] == "Refund approved"
        assert body["data"] == {"refund_id": r_id, "status": "approved"}

        # Verify DB state
        db.commit()
        ref_row = db.execute(
            text("SELECT status, admin_note, processed_by_admin_id, approved_at FROM booking_refunds WHERE id = :id"),
            {"id": r_id},
        ).mappings().first()
        assert ref_row["status"] == "approved"
        assert ref_row["admin_note"] == "Refund verified by admin"
        assert ref_row["processed_by_admin_id"] == admin["id"]
        assert ref_row["approved_at"] is not None

        # Verify audit log
        audit_row = db.execute(
            text("SELECT * FROM admin_audit_logs WHERE admin_user_id = :aid AND action = 'approve_refund' AND entity_id = :eid"),
            {"aid": admin["id"], "eid": r_id},
        ).mappings().first()
        assert audit_row is not None

        # Test E: Already approved refund -> 409 Conflict
        res_conflict = client.post(
            "/api/v1/admin/approve_refund",
            json={"refund_id": r_id},
            headers=admin_headers,
        )
        assert res_conflict.status_code == 409
        assert res_conflict.json()["message"] == "Only pending refunds can be approved"
        assert res_conflict.json()["errors"]["status"] == ["Refund status must be pending"]

        # Test F:  alias parity on a second pending refund
        b_alias = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="pending")
        r_alias = _create_booking_refund(db, b_alias, family["id"], caretaker["id"], status="pending")
        res_alias = client.post(
            "/api/v1/admin/approve_refund",
            json={"refund_id": r_alias},
            headers=admin_headers,
        )
        assert res_alias.status_code == 200
        assert res_alias.json()["message"] == "Refund approved"

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 5. REJECT REFUND TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_reject_refund_lifecycle(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        _create_caretaker_profile(db, caretaker["id"], full_name="Reject Caretaker")
        _create_family_profile(db, family["id"], full_name="Reject Family")
        pid = _create_patient(db, family["id"], "Reject Patient")

        bid = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="pending")
        r_id = _create_booking_refund(db, bid, family["id"], caretaker["id"], status="pending")

        # Test A: Missing refund_id -> 400
        res_missing = client.post("/api/v1/admin/reject_refund", json={}, headers=admin_headers)
        assert res_missing.status_code == 400

        # Test B: Nonexistent refund -> 404
        res_404 = client.post("/api/v1/admin/reject_refund", json={"refund_id": 999999}, headers=admin_headers)
        assert res_404.status_code == 404

        # Test C: Successful reject (pending -> rejected)
        res_ok = client.post(
            "/api/v1/admin/reject_refund",
            json={"refund_id": r_id, "admin_note": "Refund terms not met"},
            headers=admin_headers,
        )
        assert res_ok.status_code == 200
        body = res_ok.json()
        assert body["success"] is True
        assert body["message"] == "Refund rejected"
        assert body["data"] == {"refund_id": r_id, "status": "rejected"}

        # Verify DB state
        db.commit()
        ref_row = db.execute(
            text("SELECT status, admin_note, processed_by_admin_id, rejected_at FROM booking_refunds WHERE id = :id"),
            {"id": r_id},
        ).mappings().first()
        assert ref_row["status"] == "rejected"
        assert ref_row["admin_note"] == "Refund terms not met"
        assert ref_row["processed_by_admin_id"] == admin["id"]
        assert ref_row["rejected_at"] is not None

        # Verify bookings.refund_status is NOT modified by reject
        bk_row = db.execute(text("SELECT refund_status FROM bookings WHERE id = :id"), {"id": bid}).mappings().first()
        assert bk_row["refund_status"] == "pending"

        # Verify audit log
        audit_row = db.execute(
            text("SELECT * FROM admin_audit_logs WHERE admin_user_id = :aid AND action = 'reject_refund' AND entity_id = :eid"),
            {"aid": admin["id"], "eid": r_id},
        ).mappings().first()
        assert audit_row is not None

        # Test D: Already rejected refund -> 409 Conflict
        res_conflict = client.post("/api/v1/admin/reject_refund", json={"refund_id": r_id}, headers=admin_headers)
        assert res_conflict.status_code == 409
        assert res_conflict.json()["message"] == "Only pending refunds can be rejected"

        # Test E:  alias parity on second pending refund
        b_alias = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="pending")
        r_alias = _create_booking_refund(db, b_alias, family["id"], caretaker["id"], status="pending")
        res_alias = client.post(
            "/api/v1/admin/reject_refund",
            json={"refund_id": r_alias},
            headers=admin_headers,
        )
        assert res_alias.status_code == 200
        assert res_alias.json()["message"] == "Refund rejected"

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 6. MARK REFUND PROCESSED TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_mark_refund_processed_lifecycle(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        _create_caretaker_profile(db, caretaker["id"], full_name="Process Caretaker")
        _create_family_profile(db, family["id"], full_name="Process Family")
        pid = _create_patient(db, family["id"], "Process Patient")

        # 1. Create approved refund
        bid = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="pending")
        r_approved = _create_booking_refund(db, bid, family["id"], caretaker["id"], status="approved")

        # 2. Create pending refund (should fail mark_processed with 409)
        bid_pend = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="pending")
        r_pending = _create_booking_refund(db, bid_pend, family["id"], caretaker["id"], status="pending")

        # Test A: Missing refund_id -> 400
        res_no_id = client.post(
            "/api/v1/admin/mark_refund_processed",
            json={"refund_method": "upi", "refund_transaction_id": "TXN123"},
            headers=admin_headers,
        )
        assert res_no_id.status_code == 400

        # Test B: Empty refund_method -> 400 with 'payment_method' key (legacy quirk)
        res_empty_method = client.post(
            "/api/v1/admin/mark_refund_processed",
            json={"refund_id": r_approved, "refund_method": "", "refund_transaction_id": "TXN123"},
            headers=admin_headers,
        )
        assert res_empty_method.status_code == 400
        assert "payment_method" in res_empty_method.json()["errors"]
        assert res_empty_method.json()["errors"]["payment_method"] == ["Payment method is required"]

        # Test C: Invalid non-empty refund_method (e.g. crypto) -> 400 with 'refund_method' key
        res_bad_method = client.post(
            "/api/v1/admin/mark_refund_processed",
            json={"refund_id": r_approved, "refund_method": "crypto", "refund_transaction_id": "TXN123"},
            headers=admin_headers,
        )
        assert res_bad_method.status_code == 400
        assert "refund_method" in res_bad_method.json()["errors"]
        assert "Refund method must be one of: card, upi, netbanking, wallet, cash, insurance, bank_transfer, other" in res_bad_method.json()["errors"]["refund_method"][0]

        # Test D: Missing refund_transaction_id -> 400
        res_no_tx = client.post(
            "/api/v1/admin/mark_refund_processed",
            json={"refund_id": r_approved, "refund_method": "bank_transfer", "refund_transaction_id": ""},
            headers=admin_headers,
        )
        assert res_no_tx.status_code == 400
        assert res_no_tx.json()["errors"]["refund_transaction_id"] == ["Refund transaction id is required"]

        # Test E: Transaction ID > 255 -> 400
        res_long_tx = client.post(
            "/api/v1/admin/mark_refund_processed",
            json={"refund_id": r_approved, "refund_method": "bank_transfer", "refund_transaction_id": "T" * 256},
            headers=admin_headers,
        )
        assert res_long_tx.status_code == 400
        assert "Refund transaction id must not exceed 255 characters" in res_long_tx.json()["errors"]["refund_transaction_id"][0]

        # Test F: Nonexistent refund -> 404
        res_404 = client.post(
            "/api/v1/admin/mark_refund_processed",
            json={"refund_id": 999999, "refund_method": "bank_transfer", "refund_transaction_id": "TXN-999"},
            headers=admin_headers,
        )
        assert res_404.status_code == 404

        # Test G: Pending refund -> 409 Conflict
        res_conflict = client.post(
            "/api/v1/admin/mark_refund_processed",
            json={"refund_id": r_pending, "refund_method": "bank_transfer", "refund_transaction_id": "TXN-123"},
            headers=admin_headers,
        )
        assert res_conflict.status_code == 409
        assert res_conflict.json()["message"] == "Only approved refunds can be marked processed"
        assert res_conflict.json()["errors"]["status"] == ["Refund status must be approved"]

        # Test H: Successful mark_refund_processed on approved refund (with bank_transfer)
        res_ok = client.post(
            "/api/v1/admin/mark_refund_processed",
            json={
                "refund_id": r_approved,
                "refund_method": "bank_transfer",
                "refund_transaction_id": "NEFT-20260826-001",
                "admin_note": "Transferred via NEFT",
            },
            headers=admin_headers,
        )
        assert res_ok.status_code == 200
        body = res_ok.json()
        assert body["success"] is True
        assert body["message"] == "Refund marked processed"
        assert body["data"]["refund_id"] == r_approved
        assert body["data"]["status"] == "processed"
        assert body["data"]["refund_method"] == "bank_transfer"
        assert body["data"]["refund_transaction_id"] == "NEFT-20260826-001"

        # Verify DB state of booking_refunds
        db.commit()
        ref_row = db.execute(
            text("SELECT status, refund_method, refund_transaction_id, admin_note, processed_by_admin_id, processed_at FROM booking_refunds WHERE id = :id"),
            {"id": r_approved},
        ).mappings().first()
        assert ref_row["status"] == "processed"
        assert ref_row["refund_method"] == "bank_transfer"
        assert ref_row["refund_transaction_id"] == "NEFT-20260826-001"
        assert ref_row["admin_note"] == "Transferred via NEFT"
        assert ref_row["processed_by_admin_id"] == admin["id"]
        assert ref_row["processed_at"] is not None

        # Verify bookings.refund_status is updated to 'processed'
        bk_row = db.execute(text("SELECT refund_status FROM bookings WHERE id = :id"), {"id": bid}).mappings().first()
        assert bk_row["refund_status"] == "processed"

        # Verify audit log
        audit_row = db.execute(
            text("SELECT * FROM admin_audit_logs WHERE admin_user_id = :aid AND action = 'mark_refund_processed' AND entity_id = :eid"),
            {"aid": admin["id"], "eid": r_approved},
        ).mappings().first()
        assert audit_row is not None

        # Test I: Already processed refund -> 409 Conflict
        res_reprocess = client.post(
            "/api/v1/admin/mark_refund_processed",
            json={"refund_id": r_approved, "refund_method": "bank_transfer", "refund_transaction_id": "NEFT-002"},
            headers=admin_headers,
        )
        assert res_reprocess.status_code == 409

        # Test J:  alias parity on a second approved refund
        b_alias = _create_booking(db, family["id"], caretaker["id"], pid, refund_status="pending")
        r_alias = _create_booking_refund(db, b_alias, family["id"], caretaker["id"], status="approved")
        res_alias = client.post(
            "/api/v1/admin/mark_refund_processed",
            json={"refund_id": r_alias, "refund_method": "upi", "refund_transaction_id": "UPI-12345"},
            headers=admin_headers,
        )
        assert res_alias.status_code == 200
        assert res_alias.json()["message"] == "Refund marked processed"

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 7. CANONICAL VS ALIAS PARITY TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_part12c_canonical_vs_alias_parity(client, db):
    admin = _create_user(db, "admin")
    user_ids = [admin["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)

        pairs = [
            ("GET", "/api/v1/admin/refunds", "/api/v1/admin/refunds", None),
            ("GET", "/api/v1/admin/refund_detail?id=999999", "/api/v1/admin/refund_detail?id=999999", None),
            ("POST", "/api/v1/admin/approve_refund", "/api/v1/admin/approve_refund", {"refund_id": 999999}),
            ("POST", "/api/v1/admin/reject_refund", "/api/v1/admin/reject_refund", {"refund_id": 999999}),
            ("POST", "/api/v1/admin/mark_refund_processed", "/api/v1/admin/mark_refund_processed", {
                "refund_id": 999999,
                "refund_method": "upi",
                "refund_transaction_id": "TXN123"
            }),
        ]

        for method, canonical, alias, body in pairs:
            if method == "GET":
                r_can = client.get(canonical, headers=admin_headers)
                r_ali = client.get(alias, headers=admin_headers)
            else:
                r_can = client.post(canonical, json=body, headers=admin_headers)
                r_ali = client.post(alias, json=body, headers=admin_headers)

            assert r_can.status_code == r_ali.status_code
            b_can = r_can.json()
            b_ali = r_ali.json()
            assert b_can["success"] == b_ali["success"]
            assert b_can["message"] == b_ali["message"]
            assert b_can["errors"] == b_ali["errors"]
            assert type(b_can["data"]) == type(b_ali["data"])

    finally:
        _cleanup_test_data(db, user_ids)
