"""
WeCare — Part 12B Admin Endpoints Test Suite

Tests all 6 Admin Part 12B endpoints and business rules:
1. GET  /api/v1/admin/earnings (+  alias)
2. GET  /api/v1/admin/earnings_export (+  alias)
3. POST /api/v1/admin/create_payout (+  alias)
4. POST /api/v1/admin/update_payout (+  alias)
5. POST /api/v1/admin/refresh_payout_eligibility (+  alias)
6. GET  /api/v1/admin/reports_summary (+  alias)
"""

import time
import pytest
from datetime import date, datetime, timedelta
from sqlalchemy import text

from app.core.security import hash_password
from tests.conftest import make_auth_headers


def _create_user(db, role="caretaker"):
    ts = int(time.time() * 1000000) % 1000000000
    email = f"adm12b_{role}_{ts}@example.com"
    username = f"u12b_{role[:2]}_{ts}"
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


def _create_caretaker_profile(db, user_id, full_name="Caretaker 12B"):
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


def _create_family_profile(db, user_id, full_name="Family 12B"):
    db.execute(
        text(
            "INSERT INTO family_profiles (user_id, full_name, gender, date_of_birth, address, city, state, pincode) "
            "VALUES (:uid, :name, 'male', '1985-05-15', '123 Test Street', 'Mumbai', 'Maharashtra', '400001')"
        ),
        {"uid": user_id, "name": full_name},
    )
    db.commit()


def _create_patient(db, family_user_id, name="Patient 12B"):
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition, care_type) "
            "VALUES (:fid, :name, 70, 'male', 'Arthritis', 'elderly_care') "
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
    status="completed",
    payout_status="ready_for_payout",
    booking_date=None,
    start_time="09:00:00",
    end_time="13:00:00",
    earning_amount=600.00,
    customer_amount=800.00,
    commission_amount=200.00,
    completed_at=None,
    payout_id=None,
    payout_paid_at=None,
    payment_status="paid",
    hold_hours=0,
):
    bdate = booking_date or date.today().strftime("%Y-%m-%d")
    comp_at = completed_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hold_until = (datetime.now() + timedelta(hours=hold_hours)).strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        text(
            "INSERT INTO bookings (family_user_id, caretaker_user_id, patient_id, service_type, booking_date, "
            "                      start_time, end_time, total_amount, total_customer_amount, caretaker_earning_amount, "
            "                      platform_commission_amount, paid_amount, remaining_amount, status, payment_status, "
            "                      payout_status, payout_hold_until, completed_at, payout_id, payout_paid_at, created_at, updated_at) "
            "VALUES (:fid, :cid, :pid, 'elderly_care', :bdate, :stime, :etime, :cust_amt, :cust_amt, :earning, "
            "        :comm_amt, :cust_amt, 0.00, :status, :pay_status, :pstatus, :hold_until, :completed_at, :payout_id, :paid_at, NOW(), NOW())"
        ),
        {
            "fid": family_user_id,
            "cid": caretaker_user_id,
            "pid": patient_id,
            "bdate": bdate,
            "stime": start_time,
            "etime": end_time,
            "cust_amt": customer_amount,
            "earning": earning_amount,
            "comm_amt": commission_amount,
            "status": status,
            "pay_status": payment_status,
            "pstatus": payout_status,
            "hold_until": hold_until,
            "completed_at": comp_at if status == "completed" else None,
            "payout_id": payout_id,
            "paid_at": payout_paid_at,
        },
    )
    bid = db.execute(
        text("SELECT id FROM bookings WHERE family_user_id = :fid AND caretaker_user_id = :cid ORDER BY id DESC LIMIT 1"),
        {"fid": family_user_id, "cid": caretaker_user_id},
    ).scalar()
    db.commit()
    return int(bid)


def _cleanup_test_data(db, user_ids):
    if not user_ids:
        return
    u_list = ",".join(str(int(u)) for u in user_ids)
    db.execute(text(f"DELETE FROM caretaker_payout_items WHERE caretaker_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM caretaker_payouts WHERE caretaker_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM payments WHERE family_user_id IN ({u_list}) OR caretaker_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM complaints WHERE family_user_id IN ({u_list}) OR caretaker_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM sos_alerts WHERE user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM booking_checklist_tasks WHERE family_user_id IN ({u_list}) OR caretaker_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM bookings WHERE family_user_id IN ({u_list}) OR caretaker_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM patient_details WHERE family_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM family_profiles WHERE user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM caretaker_profiles WHERE user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM tokens WHERE user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM notifications WHERE user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM admin_audit_logs WHERE admin_user_id IN ({u_list})"))
    db.execute(text(f"DELETE FROM users WHERE id IN ({u_list})"))
    db.commit()


# ══════════════════════════════════════════════════════════════════════
# 1. AUTHENTICATION & RBAC TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_part12b_auth_and_rbac(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        ct_headers = make_auth_headers(caretaker, db)
        fam_headers = make_auth_headers(family, db)

        endpoints = [
            ("GET", "/api/v1/admin/earnings", "/api/v1/admin/earnings", None),
            ("GET", "/api/v1/admin/earnings_export", "/api/v1/admin/earnings_export", None),
            ("POST", "/api/v1/admin/create_payout", "/api/v1/admin/create_payout", {"caretaker_user_id": caretaker["id"], "force": 1}),
            ("POST", "/api/v1/admin/update_payout", "/api/v1/admin/update_payout", {"id": 999999, "status": "pending"}),
            ("POST", "/api/v1/admin/refresh_payout_eligibility", "/api/v1/admin/refresh_payout_eligibility", {}),
            ("GET", "/api/v1/admin/reports_summary", "/api/v1/admin/reports_summary", None),
        ]

        for method, canonical, alias, body in endpoints:
            for url in [canonical, alias]:
                # 1. No auth -> 401
                if method == "GET":
                    r_no_auth = client.get(url)
                else:
                    r_no_auth = client.post(url, json=body)
                assert r_no_auth.status_code == 401, f"Expected 401 for {url}, got {r_no_auth.status_code}"
                assert r_no_auth.json()["success"] is False

                # 2. Caretaker auth -> 403
                if method == "GET":
                    r_ct = client.get(url, headers=ct_headers)
                else:
                    r_ct = client.post(url, json=body, headers=ct_headers)
                assert r_ct.status_code == 403, f"Expected 403 for caretaker on {url}, got {r_ct.status_code}"
                assert r_ct.json()["success"] is False

                # 3. Family auth -> 403
                if method == "GET":
                    r_fam = client.get(url, headers=fam_headers)
                else:
                    r_fam = client.post(url, json=body, headers=fam_headers)
                assert r_fam.status_code == 403, f"Expected 403 for family on {url}, got {r_fam.status_code}"
                assert r_fam.json()["success"] is False

                # 4. Admin auth -> 200 or 201 (or 400/404 based on business data, but NEVER 401/403)
                if method == "GET":
                    r_adm = client.get(url, headers=admin_headers)
                else:
                    r_adm = client.post(url, json=body, headers=admin_headers)
                assert r_adm.status_code not in [401, 403], f"Admin was denied access on {url}: {r_adm.status_code}"

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 2. EARNINGS SUMMARY & TABBED QUEUES TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_earnings_summary_and_tabs(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        _create_caretaker_profile(db, caretaker["id"], full_name="Jane Caretaker")
        _create_family_profile(db, family["id"], full_name="John Family")
        pid = _create_patient(db, family["id"], "Alice Patient")

        # Create bookings in different states:
        # 1. Ready for payout (large amount to ensure rank #1 in pending_settlement DESC)
        _create_booking(db, family["id"], caretaker["id"], pid, status="completed", payout_status="ready_for_payout", earning_amount=500000.00, customer_amount=600000.00, hold_hours=-2)
        # 2. Hold
        _create_booking(db, family["id"], caretaker["id"], pid, status="completed", payout_status="hold", earning_amount=30000.00, customer_amount=40000.00, hold_hours=24)
        # 3. Disputed (with open complaint so payout_refresh_eligibility keeps it disputed)
        b_disp = _create_booking(db, family["id"], caretaker["id"], pid, status="completed", payout_status="disputed", earning_amount=20000.00, customer_amount=25000.00)
        db.execute(
            text(
                "INSERT INTO complaints (booking_id, family_user_id, caretaker_user_id, subject, description, status, created_at) "
                "VALUES (:bid, :fid, :cid, 'Dispute Test', 'Dispute description', 'open', NOW())"
            ),
            {"bid": b_disp, "fid": family["id"], "cid": caretaker["id"]},
        )
        db.commit()
        # 4. Paid history
        _create_booking(db, family["id"], caretaker["id"], pid, status="completed", payout_status="paid", earning_amount=10000.00, customer_amount=12000.00, payout_paid_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # Test A: Default summary view
        res = client.get("/api/v1/admin/earnings", headers=admin_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["message"] == "Earnings settlement summary retrieved"
        assert "items" in body["data"]
        assert body["data"]["page"] == 1
        assert body["data"]["limit"] == 50

        # Find test caretaker in summary
        ct_item = next((it for it in body["data"]["items"] if it["caretaker_user_id"] == caretaker["id"]), None)
        assert ct_item is not None
        assert ct_item["ready_to_pay"] >= 500000.00
        assert ct_item["under_review_hold"] >= 30000.00
        assert ct_item["disputed"] >= 20000.00
        assert ct_item["pending_settlement"] >= 500000.00
        assert ct_item["pending_settlement"] >= 500.00

        # Test B: Pagination clamps (page lower bound, limit max 100)
        res_page = client.get("/api/v1/admin/earnings?page=0&limit=500", headers=admin_headers)
        assert res_page.status_code == 200
        assert res_page.json()["data"]["page"] == 1
        assert res_page.json()["data"]["limit"] == 100

        # Test C: Tab ready_to_pay
        res_tab_ready = client.get("/api/v1/admin/earnings?tab=ready_to_pay", headers=admin_headers)
        assert res_tab_ready.status_code == 200
        body_ready = res_tab_ready.json()
        assert body_ready["success"] is True
        assert body_ready["message"] == "Payout tab retrieved"
        assert body_ready["data"]["tab"] == "ready_to_pay"
        assert any(b["caretaker_user_id"] == caretaker["id"] for b in body_ready["data"]["bookings"])

        # Test D: Tab hold
        res_tab_hold = client.get("/api/v1/admin/earnings?tab=hold", headers=admin_headers)
        assert res_tab_hold.status_code == 200
        assert res_tab_hold.json()["data"]["tab"] == "hold"

        # Test E: Tab disputed
        res_tab_disp = client.get("/api/v1/admin/earnings?tab=disputed", headers=admin_headers)
        assert res_tab_disp.status_code == 200
        assert res_tab_disp.json()["data"]["tab"] == "disputed"

        # Test F: Tab paid_history
        res_tab_paid = client.get("/api/v1/admin/earnings?tab=paid_history", headers=admin_headers)
        assert res_tab_paid.status_code == 200
        assert res_tab_paid.json()["data"]["tab"] == "paid_history"

        # Test G: Tab failed (insert failed payout)
        db.execute(
            text(
                "INSERT INTO caretaker_payouts (caretaker_user_id, amount, status, admin_note, week_start, week_end, created_at, updated_at) "
                "VALUES (:cid, 450.00, 'failed', 'Bank account rejected', '2026-08-17', '2026-08-23', NOW(), NOW())"
            ),
            {"cid": caretaker["id"]},
        )
        db.commit()

        res_tab_failed = client.get("/api/v1/admin/earnings?tab=failed", headers=admin_headers)
        assert res_tab_failed.status_code == 200
        body_failed = res_tab_failed.json()
        assert body_failed["data"]["tab"] == "failed"
        failed_item = next((b for b in body_failed["data"]["bookings"] if b["caretaker_user_id"] == caretaker["id"]), None)
        assert failed_item is not None
        assert failed_item["failure_reason"] == "Bank account rejected"

        # Test H: Invalid tab returns 400 with exact error dict
        res_invalid = client.get("/api/v1/admin/earnings?tab=invalid_tab_name", headers=admin_headers)
        assert res_invalid.status_code == 400
        err_body = res_invalid.json()
        assert err_body["success"] is False
        assert err_body["message"] == "Invalid payout tab"
        assert "tab" in err_body["errors"]
        assert "Allowed values: ready_to_pay, hold, disputed, failed, paid_history" in err_body["errors"]["tab"][0]

        # Test I:  alias returns identical structure
        res_alias = client.get("/api/v1/admin/earnings", headers=admin_headers)
        assert res_alias.status_code == 200
        assert res_alias.json()["message"] == "Earnings settlement summary retrieved"

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 3. EARNINGS EXPORT TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_earnings_export(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        _create_caretaker_profile(db, caretaker["id"], full_name="Export Caretaker")
        _create_family_profile(db, family["id"], full_name="Export Family")
        pid = _create_patient(db, family["id"], "Export Patient")

        comp_date = "2026-08-20 10:00:00"
        _create_booking(
            db, family["id"], caretaker["id"], pid,
            status="completed", payout_status="ready_for_payout",
            booking_date="2026-08-20", completed_at=comp_date,
            customer_amount=1000.00, earning_amount=750.00, commission_amount=250.00
        )

        # Test A: Export without filters
        res = client.get("/api/v1/admin/earnings_export", headers=admin_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["message"] == "Earnings export retrieved"
        assert "totals" in body["data"]
        assert "items" in body["data"]
        assert body["data"]["totals"]["record_count"] >= 1

        # Test B: Export with caretaker_user_id and status
        res_filter = client.get(
            f"/api/v1/admin/earnings_export?caretaker_user_id={caretaker['id']}&status=ready_for_payout",
            headers=admin_headers,
        )
        assert res_filter.status_code == 200
        b_filter = res_filter.json()
        assert b_filter["data"]["totals"]["record_count"] >= 1
        assert all(it["caretaker_user_id"] == caretaker["id"] for it in b_filter["data"]["items"])
        assert all(it["payout_status"] == "ready_for_payout" for it in b_filter["data"]["items"])

        # Test C: Date range filter
        res_date = client.get(
            f"/api/v1/admin/earnings_export?start_date=2026-08-19&end_date=2026-08-21&caretaker_user_id={caretaker['id']}",
            headers=admin_headers,
        )
        assert res_date.status_code == 200
        assert res_date.json()["data"]["totals"]["record_count"] >= 1

        # Test D: Invalid status filter -> 400
        res_bad_status = client.get("/api/v1/admin/earnings_export?status=unknown_status", headers=admin_headers)
        assert res_bad_status.status_code == 400
        assert res_bad_status.json()["message"] == "Invalid payout status filter"
        assert "status" in res_bad_status.json()["errors"]

        # Test E: Invalid start_date format -> 400
        res_bad_start = client.get("/api/v1/admin/earnings_export?start_date=20-08-2026", headers=admin_headers)
        assert res_bad_start.status_code == 400
        assert res_bad_start.json()["message"] == "Invalid start_date format"
        assert "start_date" in res_bad_start.json()["errors"]

        # Test F: Invalid end_date format -> 400
        res_bad_end = client.get("/api/v1/admin/earnings_export?end_date=2026/08/21", headers=admin_headers)
        assert res_bad_end.status_code == 400
        assert res_bad_end.json()["message"] == "Invalid end_date format"
        assert "end_date" in res_bad_end.json()["errors"]

        # Test G:  alias parity
        res_alias = client.get(
            f"/api/v1/admin/earnings_export?caretaker_user_id={caretaker['id']}",
            headers=admin_headers,
        )
        assert res_alias.status_code == 200
        assert res_alias.json()["message"] == "Earnings export retrieved"

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 4. CREATE PAYOUT BATCH TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_create_payout_workflow(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        _create_caretaker_profile(db, caretaker["id"], full_name="Payout Target Caretaker")
        _create_family_profile(db, family["id"], full_name="Payout Target Family")
        pid = _create_patient(db, family["id"], "Payout Target Patient")

        # Test A: Missing caretaker_user_id -> 400
        res_missing = client.post("/api/v1/admin/create_payout", json={}, headers=admin_headers)
        assert res_missing.status_code == 400
        assert res_missing.json()["message"] == "Caretaker user id is required"

        # Test B: Nonexistent caretaker -> 404
        res_404 = client.post(
            "/api/v1/admin/create_payout",
            json={"caretaker_user_id": 999999, "force": 1},
            headers=admin_headers,
        )
        assert res_404.status_code == 404
        assert res_404.json()["message"] == "Caretaker not found"

        # Test C: Non-Monday/Tuesday restriction (when force is 0)
        # Note: If today is Wed-Sun, passing force=0 will trigger 400
        today_is_mon_or_tue = datetime.now().isoweekday() in [1, 2]
        if not today_is_mon_or_tue:
            res_weekday = client.post(
                "/api/v1/admin/create_payout",
                json={"caretaker_user_id": caretaker["id"], "force": 0},
                headers=admin_headers,
            )
            assert res_weekday.status_code == 400
            assert "Weekly payout batches can be generated only on Monday or Tuesday" in res_weekday.json()["message"]

        # Test D: Empty eligible set -> 400
        res_empty = client.post(
            "/api/v1/admin/create_payout",
            json={"caretaker_user_id": caretaker["id"], "force": 1},
            headers=admin_headers,
        )
        assert res_empty.status_code == 400
        assert res_empty.json()["message"] == "No eligible bookings found for weekly payout"

        # Test E: Successful Payout Batch Creation with force=1
        # Create 2 eligible completed bookings
        past_week_end = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        b1 = _create_booking(
            db, family["id"], caretaker["id"], pid,
            status="completed", payout_status="ready_for_payout",
            customer_amount=800.00, earning_amount=600.00, commission_amount=200.00,
            completed_at=(datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            hold_hours=-10
        )
        b2 = _create_booking(
            db, family["id"], caretaker["id"], pid,
            status="completed", payout_status="ready_for_payout",
            customer_amount=1200.00, earning_amount=900.00, commission_amount=300.00,
            completed_at=(datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            hold_hours=-10
        )

        res_create = client.post(
            "/api/v1/admin/create_payout",
            json={
                "caretaker_user_id": caretaker["id"],
                "week_end": past_week_end,
                "force": 1,
                "admin_note": "Weekly payout batch test",
            },
            headers=admin_headers,
        )
        assert res_create.status_code == 201
        body_create = res_create.json()
        assert body_create["success"] is True
        assert body_create["message"] == "Payout created"
        payout_id = body_create["data"]["payout_id"]
        assert body_create["data"]["amount"] == 1500.00
        assert body_create["data"]["gross_customer_amount"] == 2000.00
        assert body_create["data"]["total_platform_commission"] == 500.00
        assert set(body_create["data"]["booking_ids"]) == {b1, b2}

        # Verify bookings are now linked to payout_id
        bk_rows = db.execute(
            text("SELECT id, payout_id FROM bookings WHERE id IN (:b1, :b2)"),
            {"b1": b1, "b2": b2},
        ).fetchall()
        for r in bk_rows:
            assert r.payout_id == payout_id

        # Verify caretaker_payout_items are inserted
        item_count = db.execute(
            text("SELECT COUNT(*) FROM caretaker_payout_items WHERE payout_id = :pid"),
            {"pid": payout_id},
        ).scalar()
        assert item_count == 2

        # Test F: Duplicate payout batch in same week window -> 409 Conflict
        # Create another eligible booking so eligible bookings check passes and duplicate check triggers 409
        _create_booking(
            db, family["id"], caretaker["id"], pid,
            status="completed", payout_status="ready_for_payout",
            customer_amount=800.00, earning_amount=600.00, commission_amount=200.00,
            completed_at=(datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            hold_hours=-10
        )
        res_dup = client.post(
            "/api/v1/admin/create_payout",
            json={
                "caretaker_user_id": caretaker["id"],
                "week_end": past_week_end,
                "force": 1,
            },
            headers=admin_headers,
        )
        assert res_dup.status_code == 409
        assert "A payout batch already exists for this caretaker in the selected week" in res_dup.json()["message"]

        # Test G: Verify audit log entry was created
        db.commit()
        audit_row = db.execute(
            text("SELECT * FROM admin_audit_logs WHERE admin_user_id = :aid AND action = 'create_payout' AND entity_id = :pid"),
            {"aid": admin["id"], "pid": payout_id},
        ).fetchone()
        assert audit_row is not None

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 5. UPDATE PAYOUT TESTS & NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════

def test_admin_update_payout_and_notification(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        _create_caretaker_profile(db, caretaker["id"], full_name="Update Payout Caretaker")
        _create_family_profile(db, family["id"], full_name="Update Payout Family")
        pid = _create_patient(db, family["id"], "Update Payout Patient")

        # Create booking and payout record
        bid = _create_booking(
            db, family["id"], caretaker["id"], pid,
            status="completed", payout_status="ready_for_payout",
            earning_amount=800.00
        )
        db.execute(
            text(
                "INSERT INTO caretaker_payouts (caretaker_user_id, amount, status, week_start, week_end, created_at, updated_at) "
                "VALUES (:cid, 800.00, 'pending', '2026-08-17', '2026-08-23', NOW(), NOW())"
            ),
            {"cid": caretaker["id"]},
        )
        payout_id = db.execute(
            text("SELECT id FROM caretaker_payouts WHERE caretaker_user_id = :cid ORDER BY id DESC LIMIT 1"),
            {"cid": caretaker["id"]},
        ).scalar()
        payout_id = int(payout_id)

        # Link booking item to payout
        db.execute(
            text(
                "INSERT INTO caretaker_payout_items (payout_id, booking_id, caretaker_user_id, amount) "
                "VALUES (:pid, :bid, :cid, 800.00)"
            ),
            {"pid": payout_id, "bid": bid, "cid": caretaker["id"]},
        )
        db.execute(text("UPDATE bookings SET payout_id = :pid WHERE id = :bid"), {"pid": payout_id, "bid": bid})
        db.commit()

        # Test A: Missing ID or status -> 400
        res_missing = client.post("/api/v1/admin/update_payout", json={}, headers=admin_headers)
        assert res_missing.status_code == 400

        # Test B: Invalid status -> 400
        res_bad_status = client.post(
            "/api/v1/admin/update_payout",
            json={"id": payout_id, "status": "invalid_status_xyz"},
            headers=admin_headers,
        )
        assert res_bad_status.status_code == 400

        # Test C: Nonexistent payout -> 404
        res_404 = client.post(
            "/api/v1/admin/update_payout",
            json={"id": 999999, "status": "processing"},
            headers=admin_headers,
        )
        assert res_404.status_code == 404

        # Test D: Update status to 'processing'
        res_proc = client.post(
            "/api/v1/admin/update_payout",
            json={"id": payout_id, "status": "processing", "admin_note": "Bank transfer initiated"},
            headers=admin_headers,
        )
        assert res_proc.status_code == 200
        assert res_proc.json()["message"] == "Payout updated"

        db.commit()
        p_row = db.execute(text("SELECT status, admin_note FROM caretaker_payouts WHERE id = :id"), {"id": payout_id}).mappings().first()
        assert p_row["status"] == "processing"
        assert p_row["admin_note"] == "Bank transfer initiated"

        # Test E: Update status to 'paid' (triggers settled_by, settled_at, booking payout_status='paid', notification)
        res_paid = client.post(
            "/api/v1/admin/update_payout",
            json={
                "id": payout_id,
                "status": "paid",
                "payment_method": "bank_transfer",
                "payment_reference": "TXN-987654321",
                "admin_note": "Settlement finalized",
            },
            headers=admin_headers,
        )
        assert res_paid.status_code == 200

        db.commit()
        p_settled = db.execute(
            text("SELECT status, settled_by, settled_at, payment_reference FROM caretaker_payouts WHERE id = :id"),
            {"id": payout_id},
        ).mappings().first()
        assert p_settled["status"] == "paid"
        assert p_settled["settled_by"] == admin["id"]
        assert p_settled["settled_at"] is not None
        assert p_settled["payment_reference"] == "TXN-987654321"

        # Check booking was transitioned to 'paid' with payout_paid_at set
        b_settled = db.execute(
            text("SELECT payout_status, payout_paid_at FROM bookings WHERE id = :id"),
            {"id": bid},
        ).mappings().first()
        assert b_settled["payout_status"] == "paid"
        assert b_settled["payout_paid_at"] is not None

        # Check notification was created for caretaker
        notif_row = db.execute(
            text("SELECT * FROM notifications WHERE user_id = :uid AND type = 'payout_processed' AND related_id = :pid"),
            {"uid": caretaker["id"], "pid": payout_id},
        ).mappings().first()
        assert notif_row is not None
        assert notif_row["title"] == "Payout processed"

        # Test F: Re-updating an already 'paid' payout does NOT send duplicate notification
        client.post(
            "/api/v1/admin/update_payout",
            json={"id": payout_id, "status": "paid", "admin_note": "Re-saving note"},
            headers=admin_headers,
        )
        db.commit()
        notif_count = db.execute(
            text("SELECT COUNT(*) FROM notifications WHERE user_id = :uid AND type = 'payout_processed' AND related_id = :pid"),
            {"uid": caretaker["id"], "pid": payout_id},
        ).scalar()
        assert notif_count == 1

        # Test G:  alias parity
        res_alias = client.post(
            "/api/v1/admin/update_payout",
            json={"id": payout_id, "status": "paid"},
            headers=admin_headers,
        )
        assert res_alias.status_code == 200
        assert res_alias.json()["message"] == "Payout updated"

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 6. REFRESH PAYOUT ELIGIBILITY TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_refresh_payout_eligibility(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        _create_caretaker_profile(db, caretaker["id"], full_name="Refresh Caretaker")
        _create_family_profile(db, family["id"], full_name="Refresh Family")
        pid = _create_patient(db, family["id"], "Refresh Patient")

        bid = _create_booking(
            db, family["id"], caretaker["id"], pid,
            status="completed", payout_status="hold",
            hold_hours=-5
        )

        # Test A: Global refresh
        res_global = client.post("/api/v1/admin/refresh_payout_eligibility", json={}, headers=admin_headers)
        assert res_global.status_code == 200
        body_g = res_global.json()
        assert body_g["success"] is True
        assert body_g["message"] == "Payout eligibility refreshed"
        assert "ready_for_payout" in body_g["data"]
        assert "hold" in body_g["data"]
        assert "disputed" in body_g["data"]

        # Test B: Targeted refresh with booking_id
        res_single = client.post(
            "/api/v1/admin/refresh_payout_eligibility",
            json={"booking_id": bid},
            headers=admin_headers,
        )
        assert res_single.status_code == 200
        assert res_single.json()["data"]["ready_for_payout"] >= 1

        # Test C:  alias parity
        res_alias = client.post(
            "/api/v1/admin/refresh_payout_eligibility",
            json={"booking_id": bid},
            headers=admin_headers,
        )
        assert res_alias.status_code == 200
        assert res_alias.json()["message"] == "Payout eligibility refreshed"

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 7. REPORTS SUMMARY TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_reports_summary(client, db):
    admin = _create_user(db, "admin")
    caretaker = _create_user(db, "caretaker")
    family = _create_user(db, "family")
    user_ids = [admin["id"], caretaker["id"], family["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)
        _create_caretaker_profile(db, caretaker["id"], full_name="Report Caretaker")
        _create_family_profile(db, family["id"], full_name="Report Family")
        pid = _create_patient(db, family["id"], "Report Patient")

        # Seed payment, booking, sos, complaint
        bid = _create_booking(
            db, family["id"], caretaker["id"], pid,
            status="completed", customer_amount=1000.00, earning_amount=800.00, commission_amount=200.00
        )
        db.execute(
            text(
                "INSERT INTO payments (booking_id, family_user_id, caretaker_user_id, amount, status, payment_method, verification_status, created_at) "
                "VALUES (:bid, :fid, :cid, 1000.00, 'success', 'online', 'verified', NOW())"
            ),
            {"bid": bid, "fid": family["id"], "cid": caretaker["id"]},
        )
        db.execute(
            text(
                "INSERT INTO sos_alerts (user_id, booking_id, message, status, created_at) "
                "VALUES (:uid, :bid, 'Test SOS Alert', 'open', NOW())"
            ),
            {"uid": family["id"], "bid": bid},
        )
        db.execute(
            text(
                "INSERT INTO complaints (booking_id, family_user_id, caretaker_user_id, subject, description, status, created_at) "
                "VALUES (:bid, :fid, :cid, 'Report Complaint', 'Testing complaint', 'open', NOW())"
            ),
            {"bid": bid, "fid": family["id"], "cid": caretaker["id"]},
        )
        db.commit()

        # Test A: Canonical route
        res = client.get("/api/v1/admin/reports_summary", headers=admin_headers)
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["message"] == "Reports summary retrieved"
        data = body["data"]

        # Check all 7 groups exist
        assert "revenue" in data
        assert "commission" in data
        assert "bookings" in data
        assert "users" in data
        assert "payouts" in data
        assert "sos_alerts" in data
        assert "complaints" in data

        # Check float rounding for revenue/commission/payouts
        assert isinstance(data["revenue"]["total_revenue"], float)
        assert isinstance(data["commission"]["total_platform_commission"], float)
        assert isinstance(data["payouts"]["total_paid"], float)
        assert isinstance(data["payouts"]["paid_count"], float)  # legacy float group

        # Check integer types for counts
        assert isinstance(data["bookings"]["total"], int)
        assert isinstance(data["users"]["total"], int)
        assert isinstance(data["sos_alerts"]["total"], int)
        assert isinstance(data["complaints"]["total"], int)

        # Check seeded values are reflected
        assert data["revenue"]["total_revenue"] >= 1000.00
        assert data["commission"]["total_platform_commission"] >= 200.00
        assert data["sos_alerts"]["open_alerts"] >= 1
        assert data["complaints"]["pending"] >= 1

        # Test B:  alias parity
        res_alias = client.get("/api/v1/admin/reports_summary", headers=admin_headers)
        assert res_alias.status_code == 200
        assert res_alias.json()["message"] == "Reports summary retrieved"

    finally:
        _cleanup_test_data(db, user_ids)


# ══════════════════════════════════════════════════════════════════════
# 8. CANONICAL VS ALIAS PARITY TESTS
# ══════════════════════════════════════════════════════════════════════

def test_admin_part12b_canonical_vs_alias_parity(client, db):
    admin = _create_user(db, "admin")
    user_ids = [admin["id"]]

    try:
        admin_headers = make_auth_headers(admin, db)

        pairs = [
            ("GET", "/api/v1/admin/earnings", "/api/v1/admin/earnings", None),
            ("GET", "/api/v1/admin/earnings_export", "/api/v1/admin/earnings_export", None),
            ("POST", "/api/v1/admin/refresh_payout_eligibility", "/api/v1/admin/refresh_payout_eligibility", {}),
            ("GET", "/api/v1/admin/reports_summary", "/api/v1/admin/reports_summary", None),
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
