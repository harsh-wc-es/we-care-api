"""
WeCare — Booking Endpoints Integration Tests

Covers all 16 booking endpoints across family, caretaker, and admin roles.
"""

from datetime import datetime, timedelta
import pytest
from sqlalchemy import text

from tests.conftest import make_auth_headers


def _setup_booking_scenario(db, test_user, caretaker_user):
    """Helper to set up caretaker pricing, patient details, and a test booking."""
    family_id = test_user["id"]
    caretaker_id = caretaker_user["id"]

    # 1. Update caretaker profile with pricing and availability
    db.execute(
        text(
            "UPDATE caretaker_profiles "
            "SET pricing_tier_id = 1, "
            "    pricing_tier = 'standard', "
            "    skill_level = 'certified', "
            "    customer_hourly_rate = 30.00, "
            "    caretaker_hourly_rate = 20.00, "
            "    platform_commission_hourly = 10.00, "
            "    is_available = 1, "
            "    manual_availability_enabled = 1, "
            "    verification_status = 'approved', "
            "    availability_locked_by_admin = 0 "
            "WHERE user_id = :cid"
        ),
        {"cid": caretaker_id},
    )

    # 2. Insert patient details
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition, care_type) "
            "VALUES (:fuid, 'Grandma Rose', 80, 'female', 'Alzheimer', 'Elder Care')"
        ),
        {"fuid": family_id},
    )
    db.commit()

    patient_id = db.execute(
        text("SELECT id FROM patient_details WHERE family_user_id = :fuid"),
        {"fuid": family_id},
    ).scalar()

    return family_id, caretaker_id, patient_id


def _cleanup_booking_scenario(db, booking_id=None, patient_id=None):
    """Cleanup test entities."""
    if booking_id:
        db.execute(text("DELETE FROM replacement_tickets WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM booking_refunds WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM payments WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM otp_codes WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM notifications WHERE related_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM visit_tracking WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM booking_checklist_tasks WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM complaints WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM sos_alerts WHERE booking_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM admin_audit_logs WHERE entity_id = :bid"), {"bid": booking_id})
        db.execute(text("DELETE FROM bookings WHERE id = :bid"), {"bid": booking_id})
    if patient_id:
        db.execute(text("DELETE FROM patient_details WHERE id = :pid"), {"pid": patient_id})
    db.commit()


def test_create_booking_flow(client, db, test_user, caretaker_user):
    """Tests POST /api/v1/booking/create_booking and validation."""
    family_id, caretaker_id, patient_id = _setup_booking_scenario(db, test_user, caretaker_user)
    headers = make_auth_headers(test_user, db)

    # 1. Missing fields validation
    res_invalid = client.post("/api/v1/booking/create_booking", json={}, headers=headers)
    assert res_invalid.status_code == 400
    assert res_invalid.json()["success"] is False

    # 2. Valid booking creation
    visit_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    payload = {
        "caretaker_user_id": caretaker_id,
        "patient_id": patient_id,
        "service_type": "Elder Care",
        "booking_date": visit_date,
        "start_time": "09:00:00",
        "end_time": "13:00:00",
        "address": "456 Blossom Lane, Greenfield",
        "notes": "Please assist with morning medication",
    }

    res = client.post("/api/v1/booking/create_booking", json=payload, headers=headers)
    assert res.status_code == 201
    body = res.json()
    assert body["success"] is True
    data = body["data"]
    booking_id = data["booking_id"]
    assert data["total_hours"] == 4.0
    assert data["customer_hourly_rate"] == 30.0
    assert data["total_customer_amount"] == 120.0
    assert data["total_amount"] == 120.0

    # 3. Test  alias
    res_php = client.post("/api/v1/booking/create_booking", json=payload, headers=headers)
    assert res_php.status_code == 201
    booking_id_2 = res_php.json()["data"]["booking_id"]

    _cleanup_booking_scenario(db, booking_id, patient_id)
    _cleanup_booking_scenario(db, booking_id_2)


def test_my_bookings_endpoints(client, db, test_user, caretaker_user):
    """Tests GET /api/v1/booking/my_bookings for family and caretaker roles."""
    family_id, caretaker_id, patient_id = _setup_booking_scenario(db, test_user, caretaker_user)
    family_headers = make_auth_headers(test_user, db)
    caretaker_headers = make_auth_headers(caretaker_user, db)

    # Insert a booking
    visit_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    create_payload = {
        "caretaker_user_id": caretaker_id,
        "patient_id": patient_id,
        "service_type": "Elder Care",
        "booking_date": visit_date,
        "start_time": "10:00:00",
        "end_time": "14:00:00",
        "address": "789 Park Ave, Metro City",
    }
    res_create = client.post("/api/v1/booking/create_booking", json=create_payload, headers=family_headers)
    booking_id = res_create.json()["data"]["booking_id"]

    # 1. Family requests my_bookings
    res_fam = client.get("/api/v1/booking/my_bookings", headers=family_headers)
    assert res_fam.status_code == 200
    fam_body = res_fam.json()
    assert fam_body["success"] is True
    assert len(fam_body["data"]) >= 1
    # Check field stripping (no caretaker rate or platform commission)
    fam_booking = next(b for b in fam_body["data"] if b["id"] == booking_id)
    assert "caretaker_hourly_rate" not in fam_booking
    assert "platform_commission_hourly" not in fam_booking

    # 2. Caretaker requests my_bookings
    res_ct = client.get("/api/v1/booking/my_bookings", headers=caretaker_headers)
    assert res_ct.status_code == 200
    ct_body = res_ct.json()
    assert ct_body["success"] is True
    ct_booking = next(b for b in ct_body["data"] if b["id"] == booking_id)
    # Check field stripping (no customer hourly rate, no total customer amount)
    assert "customer_hourly_rate" not in ct_booking
    assert "total_customer_amount" not in ct_booking

    # 3. Paginated mode
    res_pag = client.get("/api/v1/booking/my_bookings?paginated=true&page=1&limit=10", headers=family_headers)
    assert res_pag.status_code == 200
    assert "pagination" in res_pag.json()["data"]

    _cleanup_booking_scenario(db, booking_id, patient_id)


def test_caretaker_requests_and_details(client, db, test_user, caretaker_user):
    """Tests GET /api/v1/booking/caretaker_requests, detail, and legacy routes."""
    family_id, caretaker_id, patient_id = _setup_booking_scenario(db, test_user, caretaker_user)
    family_headers = make_auth_headers(test_user, db)
    caretaker_headers = make_auth_headers(caretaker_user, db)

    visit_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    create_payload = {
        "caretaker_user_id": caretaker_id,
        "patient_id": patient_id,
        "service_type": "Elder Care",
        "booking_date": visit_date,
        "start_time": "08:00:00",
        "end_time": "12:00:00",
        "address": "100 Maple St, City",
    }
    res_create = client.post("/api/v1/booking/create_booking", json=create_payload, headers=family_headers)
    booking_id = res_create.json()["data"]["booking_id"]

    # 1. GET /api/v1/booking/caretaker_requests
    res_reqs = client.get("/api/v1/booking/caretaker_requests", headers=caretaker_headers)
    assert res_reqs.status_code == 200
    reqs_body = res_reqs.json()
    assert reqs_body["success"] is True
    assert "requests" in reqs_body["data"]
    assert "pagination" in reqs_body["data"]

    # 2. GET /api/v1/booking/caretaker_request_detail
    res_detail = client.get(f"/api/v1/booking/caretaker_request_detail?booking_id={booking_id}", headers=caretaker_headers)
    assert res_detail.status_code == 200
    det_body = res_detail.json()
    assert det_body["success"] is True
    assert det_body["data"]["booking_id"] == booking_id
    assert "patient" in det_body["data"]
    assert "actions" in det_body["data"]
    assert det_body["data"]["actions"]["can_accept"] is True

    # 3. GET /api/v1/caretaker/requests (legacy)
    res_leg = client.get("/api/v1/caretaker/requests", headers=caretaker_headers)
    assert res_leg.status_code == 200
    assert "requests" in res_leg.json()["data"]

    # 4. GET /api/v1/caretaker/booking_detail (legacy)
    res_leg_det = client.get(f"/api/v1/caretaker/booking_detail?booking_id={booking_id}", headers=caretaker_headers)
    assert res_leg_det.status_code == 200
    assert res_leg_det.json()["data"]["booking_id"] == booking_id

    _cleanup_booking_scenario(db, booking_id, patient_id)


def test_caretaker_respond_accept_decline(client, db, test_user, caretaker_user):
    """Tests respond_request, accept_booking, and reject_booking."""
    family_id, caretaker_id, patient_id = _setup_booking_scenario(db, test_user, caretaker_user)
    family_headers = make_auth_headers(test_user, db)
    caretaker_headers = make_auth_headers(caretaker_user, db)

    visit_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

    # Scenario A: respond_request with decline
    res_c1 = client.post("/api/v1/booking/create_booking", json={
        "caretaker_user_id": caretaker_id,
        "patient_id": patient_id,
        "service_type": "Elder Care",
        "booking_date": visit_date,
        "start_time": "09:00:00",
        "end_time": "12:00:00",
        "address": "123 Street A",
    }, headers=family_headers)
    bid_1 = res_c1.json()["data"]["booking_id"]

    res_dec = client.post("/api/v1/booking/respond_request", json={
        "booking_id": bid_1,
        "action": "decline",
        "decline_reason_code": "not_available",
    }, headers=caretaker_headers)
    assert res_dec.status_code == 200
    assert res_dec.json()["data"]["status"] == "declined"

    # Scenario B: accept_booking endpoint
    res_c2 = client.post("/api/v1/booking/create_booking", json={
        "caretaker_user_id": caretaker_id,
        "patient_id": patient_id,
        "service_type": "Elder Care",
        "booking_date": visit_date,
        "start_time": "13:00:00",
        "end_time": "17:00:00",
        "address": "123 Street B",
    }, headers=family_headers)
    bid_2 = res_c2.json()["data"]["booking_id"]

    res_acc = client.post("/api/v1/booking/accept_booking", json={"booking_id": bid_2}, headers=caretaker_headers)
    assert res_acc.status_code == 200
    assert res_acc.json()["data"]["status"] == "accepted"
    assert res_acc.json()["data"]["visit_otp_required"] is True

    # Scenario C: reject_booking endpoint
    res_c3 = client.post("/api/v1/booking/create_booking", json={
        "caretaker_user_id": caretaker_id,
        "patient_id": patient_id,
        "service_type": "Elder Care",
        "booking_date": visit_date,
        "start_time": "17:00:00",
        "end_time": "20:00:00",
        "address": "123 Street C",
    }, headers=family_headers)
    bid_3 = res_c3.json()["data"]["booking_id"]

    res_rej = client.post("/api/v1/booking/reject_booking", json={
        "booking_id": bid_3,
        "decline_reason_code": "location_too_far",
    }, headers=caretaker_headers)
    assert res_rej.status_code == 200
    assert res_rej.json()["data"]["status"] == "declined"

    _cleanup_booking_scenario(db, bid_1, patient_id)
    _cleanup_booking_scenario(db, bid_2)
    _cleanup_booking_scenario(db, bid_3)


def test_family_cancel_booking(client, db, test_user, caretaker_user):
    """Tests POST /api/v1/booking/cancel_booking with payment & refund calculation."""
    family_id, caretaker_id, patient_id = _setup_booking_scenario(db, test_user, caretaker_user)
    family_headers = make_auth_headers(test_user, db)

    visit_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    res_create = client.post("/api/v1/booking/create_booking", json={
        "caretaker_user_id": caretaker_id,
        "patient_id": patient_id,
        "service_type": "Elder Care",
        "booking_date": visit_date,
        "start_time": "09:00:00",
        "end_time": "13:00:00",
        "address": "123 Family Home",
    }, headers=family_headers)
    booking_id = res_create.json()["data"]["booking_id"]

    # Add a mock successful payment
    db.execute(
        text(
            "INSERT INTO payments (booking_id, family_user_id, caretaker_user_id, amount, status, payment_method) "
            "VALUES (:bid, :fuid, :cid, 120.00, 'success', 'card')"
        ),
        {"bid": booking_id, "fuid": family_id, "cid": caretaker_id},
    )
    db.commit()

    # Cancel booking
    res_cancel = client.post("/api/v1/booking/cancel_booking", json={
        "booking_id": booking_id,
        "cancel_reason_code": "change_of_plan",
        "cancel_note": "Travel schedule altered",
    }, headers=family_headers)

    assert res_cancel.status_code == 200
    body = res_cancel.json()
    assert body["success"] is True
    assert body["data"]["status"] == "cancelled"
    refund = body["data"]["refund"]
    assert refund["eligible"] is True
    assert refund["refund_percentage"] == 100.0
    assert refund["refund_amount"] == 120.0
    assert refund["cancellation_fee"] == 0.0

    _cleanup_booking_scenario(db, booking_id, patient_id)


def test_caretaker_cancel_booking(client, db, test_user, caretaker_user, admin_user):
    """Tests POST /api/v1/booking/caretaker_cancel_booking with 100% refund & replacement ticket."""
    family_id, caretaker_id, patient_id = _setup_booking_scenario(db, test_user, caretaker_user)
    family_headers = make_auth_headers(test_user, db)
    caretaker_headers = make_auth_headers(caretaker_user, db)

    visit_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    res_create = client.post("/api/v1/booking/create_booking", json={
        "caretaker_user_id": caretaker_id,
        "patient_id": patient_id,
        "service_type": "Elder Care",
        "booking_date": visit_date,
        "start_time": "10:00:00",
        "end_time": "14:00:00",
        "address": "456 Care Lane",
    }, headers=family_headers)
    booking_id = res_create.json()["data"]["booking_id"]

    # Caretaker accepts first
    client.post("/api/v1/booking/accept_booking", json={"booking_id": booking_id}, headers=caretaker_headers)

    # Caretaker cancels
    res_cancel = client.post("/api/v1/booking/caretaker_cancel_booking", json={
        "booking_id": booking_id,
        "cancel_reason_code": "emergency",
        "cancel_note": "Family emergency",
    }, headers=caretaker_headers)

    assert res_cancel.status_code == 200
    body = res_cancel.json()
    assert body["success"] is True
    assert body["data"]["status"] == "cancelled"
    assert body["data"]["replacement_ticket_id"] is not None
    assert body["data"]["availability_restored"] is True

    # Verify replacement ticket in database
    ticket = db.execute(
        text("SELECT id, reason FROM replacement_tickets WHERE booking_id = :bid"),
        {"bid": booking_id},
    ).mappings().first()
    assert ticket is not None
    assert "Emergency" in ticket["reason"]

    _cleanup_booking_scenario(db, booking_id, patient_id)


def test_complete_booking_endpoint(client, db, test_user, caretaker_user):
    """Tests POST /api/v1/booking/complete_booking."""
    family_id, caretaker_id, patient_id = _setup_booking_scenario(db, test_user, caretaker_user)
    family_headers = make_auth_headers(test_user, db)
    caretaker_headers = make_auth_headers(caretaker_user, db)

    visit_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    res_create = client.post("/api/v1/booking/create_booking", json={
        "caretaker_user_id": caretaker_id,
        "patient_id": patient_id,
        "service_type": "Elder Care",
        "booking_date": visit_date,
        "start_time": "09:00:00",
        "end_time": "13:00:00",
        "address": "789 Work Lane",
    }, headers=family_headers)
    booking_id = res_create.json()["data"]["booking_id"]

    # Accept booking
    client.post("/api/v1/booking/accept_booking", json={"booking_id": booking_id}, headers=caretaker_headers)

    # Complete booking
    res_complete = client.post("/api/v1/booking/complete_booking", json={"booking_id": booking_id}, headers=caretaker_headers)
    assert res_complete.status_code == 200
    body = res_complete.json()
    assert body["success"] is True
    assert body["data"]["payout_status"] == "hold"

    _cleanup_booking_scenario(db, booking_id, patient_id)


def test_visit_otp_endpoint(client, db, test_user, caretaker_user):
    """Tests POST /api/v1/booking/visit_otp and rate limiting."""
    family_id, caretaker_id, patient_id = _setup_booking_scenario(db, test_user, caretaker_user)
    family_headers = make_auth_headers(test_user, db)
    caretaker_headers = make_auth_headers(caretaker_user, db)

    visit_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    res_create = client.post("/api/v1/booking/create_booking", json={
        "caretaker_user_id": caretaker_id,
        "patient_id": patient_id,
        "service_type": "Elder Care",
        "booking_date": visit_date,
        "start_time": "09:00:00",
        "end_time": "13:00:00",
        "address": "789 OTP Lane",
    }, headers=family_headers)
    booking_id = res_create.json()["data"]["booking_id"]

    # Accept booking so it's active
    client.post("/api/v1/booking/accept_booking", json={"booking_id": booking_id}, headers=caretaker_headers)

    # 1. Family requests visit OTP
    res_otp = client.post("/api/v1/booking/visit_otp", json={"booking_id": booking_id}, headers=family_headers)
    assert res_otp.status_code == 200
    body = res_otp.json()
    assert body["success"] is True
    assert len(body["data"]["visit_start_otp"]) == 6
    assert body["data"]["otp_expires_in"] == 900
    assert body["data"]["resend_cooldown"] == 60

    # 2. Second request immediately hits 429 rate limit
    res_otp_cooldown = client.post("/api/v1/booking/visit_otp", json={"booking_id": booking_id}, headers=family_headers)
    assert res_otp_cooldown.status_code == 429

    _cleanup_booking_scenario(db, booking_id, patient_id)


def test_admin_booking_endpoints(client, db, test_user, caretaker_user, admin_user):
    """Tests GET /api/v1/admin/bookings, detail, and admin cancel booking."""
    family_id, caretaker_id, patient_id = _setup_booking_scenario(db, test_user, caretaker_user)
    family_headers = make_auth_headers(test_user, db)
    admin_headers = make_auth_headers(admin_user, db)

    visit_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    res_create = client.post("/api/v1/booking/create_booking", json={
        "caretaker_user_id": caretaker_id,
        "patient_id": patient_id,
        "service_type": "Elder Care",
        "booking_date": visit_date,
        "start_time": "14:00:00",
        "end_time": "18:00:00",
        "address": "555 Admin St",
    }, headers=family_headers)
    booking_id = res_create.json()["data"]["booking_id"]

    # 1. Admin bookings list
    res_list = client.get("/api/v1/admin/bookings", headers=admin_headers)
    assert res_list.status_code == 200
    body_list = res_list.json()
    assert body_list["success"] is True
    assert len(body_list["data"]["items"]) >= 1

    # 2. Admin booking detail
    res_det = client.get(f"/api/v1/admin/booking_detail?booking_id={booking_id}", headers=admin_headers)
    assert res_det.status_code == 200
    body_det = res_det.json()
    assert body_det["success"] is True
    assert body_det["data"]["booking_id"] == booking_id
    assert "payments" in body_det["data"]
    assert "visits" in body_det["data"]
    assert "checklist_tasks" in body_det["data"]
    assert "complaints" in body_det["data"]
    assert "sos_alerts" in body_det["data"]

    # 3. Admin cancel booking
    res_admin_cancel = client.post("/api/v1/admin/cancel_booking", json={
        "booking_id": booking_id,
        "reason": "Administrative override due to client emergency",
    }, headers=admin_headers)
    assert res_admin_cancel.status_code == 200
    body_ac = res_admin_cancel.json()
    assert body_ac["success"] is True
    assert body_ac["data"]["new_status"] == "cancelled"

    _cleanup_booking_scenario(db, booking_id, patient_id)
