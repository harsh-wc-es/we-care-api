"""
WeCare — Review & Caretaker Feedback Endpoints HTTP Integration Tests (Part 8)

Comprehensive test suite covering all 5 Review & Feedback endpoints via FastAPI TestClient:
1. POST /api/v1/review/add_review[]
2. GET  /api/v1/review/caretaker_reviews[]
3. POST /api/v1/caretaker/submit_feedback[]
4. GET  /api/v1/admin/caretaker_feedback[]
5. POST /api/v1/admin/update_feedback_status[]

Tests role scoping, IDOR protection, rating calculations in caretaker_profiles,
validation boundaries, anonymous feedback masking, and admin audit logging.
"""

from datetime import datetime, timedelta, timezone
import time
import pytest
from sqlalchemy import text

from app.core.security import hash_password
from tests.conftest import make_auth_headers


def _create_aux_user(db, role="family"):
    """Creates a real auxiliary user for IDOR testing."""
    ts = int(time.time() * 1000000) % 1000000000
    email = f"aux_rev_{role}_{ts}@example.com"
    username = f"aux_rev_{role[:2]}_{ts}"
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
    user_id = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())
    db.commit()

    if role == "caretaker":
        db.execute(
            text(
                "INSERT INTO caretaker_profiles (user_id, full_name, verification_status, is_available) "
                "VALUES (:uid, :name, 'approved', 1)"
            ),
            {"uid": user_id, "name": f"Aux Caretaker {user_id}"},
        )
        db.commit()
    elif role == "family":
        db.execute(
            text(
                "INSERT INTO family_profiles (user_id, full_name, emergency_contact_phone) "
                "VALUES (:uid, :name, '9998887776')"
            ),
            {"uid": user_id, "name": f"Aux Family {user_id}"},
        )
        db.commit()

    return {"id": user_id, "email": email, "role": role}


@pytest.fixture
def review_setup_data(db):
    """Sets up primary family, caretaker, admin, patient, and completed bookings."""
    ts = int(time.time() * 1000000) % 1000000000
    pwd_hash = hash_password("TestPassword123!")

    # 1. Family User
    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, 'family', 1, 1)"
        ),
        {
            "email": f"fam_rev_{ts}@example.com",
            "username": f"fam_rev_{ts}",
            "phone": f"9{ts:09d}"[:10],
            "password": pwd_hash,
        },
    )
    family_id = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())

    db.execute(
        text(
            "INSERT INTO family_profiles (user_id, full_name, emergency_contact_phone) "
            "VALUES (:uid, :name, '9998887776')"
        ),
        {"uid": family_id, "name": f"Family Rev {family_id}"},
    )

    # 2. Caretaker User
    ts_c = (ts + 1) % 1000000000
    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, 'caretaker', 1, 1)"
        ),
        {
            "email": f"car_rev_{ts_c}@example.com",
            "username": f"car_rev_{ts_c}",
            "phone": f"9{ts_c:09d}"[:10],
            "password": pwd_hash,
        },
    )
    caretaker_id = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())

    db.execute(
        text(
            "INSERT INTO caretaker_profiles (user_id, full_name, verification_status, is_available, rating, total_reviews) "
            "VALUES (:uid, :name, 'approved', 1, 0.00, 0)"
        ),
        {"uid": caretaker_id, "name": f"Caretaker Rev {caretaker_id}"},
    )

    # 3. Admin User
    ts_a = (ts + 2) % 1000000000
    db.execute(
        text(
            "INSERT INTO users (email, username, phone_number, password, role, is_verified, is_active) "
            "VALUES (:email, :username, :phone, :password, 'admin', 1, 1)"
        ),
        {
            "email": f"adm_rev_{ts_a}@example.com",
            "username": f"adm_rev_{ts_a}",
            "phone": f"9{ts_a:09d}"[:10],
            "password": pwd_hash,
        },
    )
    admin_id = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())

    # 4. Patient
    db.execute(
        text(
            "INSERT INTO patient_details (family_user_id, patient_name, age, gender, medical_condition) "
            "VALUES (:fid, :name, 75, 'female', 'Post-surgery recovery')"
        ),
        {"fid": family_id, "name": "Senior Patient Rev"},
    )
    patient_id = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())

    # 5. Completed Booking 1
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db.execute(
        text(
            "INSERT INTO bookings ("
            "  family_user_id, caretaker_user_id, patient_id, service_type, "
            "  booking_date, start_time, end_time, total_hours, address, "
            "  status, payment_status, total_customer_amount, caretaker_earning_amount"
            ") VALUES ("
            "  :fid, :cid, :pid, 'Elderly Care', "
            "  :bdate, '09:00:00', '17:00:00', 8.0, '123 Caregiver Ave', "
            "  'completed', 'paid', 1600.00, 1280.00"
            ")"
        ),
        {"fid": family_id, "cid": caretaker_id, "pid": patient_id, "bdate": today_str},
    )
    completed_booking_id1 = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())

    # 6. Completed Booking 2
    db.execute(
        text(
            "INSERT INTO bookings ("
            "  family_user_id, caretaker_user_id, patient_id, service_type, "
            "  booking_date, start_time, end_time, total_hours, address, "
            "  status, payment_status, total_customer_amount, caretaker_earning_amount"
            ") VALUES ("
            "  :fid, :cid, :pid, 'Elderly Care', "
            "  :bdate, '09:00:00', '17:00:00', 8.0, '123 Caregiver Ave', "
            "  'completed', 'paid', 1600.00, 1280.00"
            ")"
        ),
        {"fid": family_id, "cid": caretaker_id, "pid": patient_id, "bdate": today_str},
    )
    completed_booking_id2 = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())

    # 7. In-Progress Booking (Non-completed)
    db.execute(
        text(
            "INSERT INTO bookings ("
            "  family_user_id, caretaker_user_id, patient_id, service_type, "
            "  booking_date, start_time, end_time, total_hours, address, "
            "  status, payment_status, total_customer_amount, caretaker_earning_amount"
            ") VALUES ("
            "  :fid, :cid, :pid, 'Elderly Care', "
            "  :bdate, '09:00:00', '17:00:00', 8.0, '123 Caregiver Ave', "
            "  'in_progress', 'paid', 1600.00, 1280.00"
            ")"
        ),
        {"fid": family_id, "cid": caretaker_id, "pid": patient_id, "bdate": today_str},
    )
    in_progress_booking_id = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())
    db.commit()

    return {
        "family": {"id": family_id, "email": f"fam_rev_{ts}@example.com", "role": "family"},
        "caretaker": {"id": caretaker_id, "email": f"car_rev_{ts_c}@example.com", "role": "caretaker"},
        "admin": {"id": admin_id, "email": f"adm_rev_{ts_a}@example.com", "role": "admin"},
        "patient_id": patient_id,
        "completed_booking_id1": completed_booking_id1,
        "completed_booking_id2": completed_booking_id2,
        "in_progress_booking_id": in_progress_booking_id,
    }


def test_add_review_completed_booking_success_and_rating_recalculation_http(client, db, review_setup_data):
    """
    Tests submitting reviews for completed bookings and verifies automatic
    recalculation of total_reviews and average rating on caretaker_profiles.
    """
    data = review_setup_data
    fam_headers = make_auth_headers(data["family"], db)

    # 1. Submit first review (rating = 5) on completed_booking_id1 via  alias
    resp1 = client.post(
        "/api/v1/review/add_review",
        json={
            "booking_id": data["completed_booking_id1"],
            "rating": 5,
            "comment": "Outstanding, very attentive caregiver!",
        },
        headers=fam_headers,
    )
    assert resp1.status_code == 201
    body1 = resp1.json()
    assert body1["success"] is True
    assert body1["message"] == "Review submitted successfully"
    assert "review_id" in body1["data"]
    assert body1["data"]["review_id"] > 0

    # Verify caretaker_profiles stats
    db.commit()
    cp1 = db.execute(
        text("SELECT rating, total_reviews FROM caretaker_profiles WHERE user_id = :cid"),
        {"cid": data["caretaker"]["id"]},
    ).fetchone()
    assert cp1.total_reviews == 1
    assert float(cp1.rating) == 5.00

    # 2. Prevent duplicate review for the same booking
    resp_dup = client.post(
        "/api/v1/review/add_review",
        json={
            "booking_id": data["completed_booking_id1"],
            "rating": 4,
            "comment": "Duplicate attempt",
        },
        headers=fam_headers,
    )
    assert resp_dup.status_code == 400
    assert resp_dup.json()["message"] == "Review already submitted for this booking"

    # 3. Submit second review (rating = 3) on completed_booking_id2 via canonical route
    resp2 = client.post(
        "/api/v1/review/add_review",
        json={
            "booking_id": data["completed_booking_id2"],
            "rating": 3,
            "comment": "Good overall, but arrived slightly late.",
        },
        headers=fam_headers,
    )
    assert resp2.status_code == 201
    assert resp2.json()["success"] is True

    # Verify updated stats: (5 + 3) / 2 = 4.00, total = 2
    db.commit()
    cp2 = db.execute(
        text("SELECT rating, total_reviews FROM caretaker_profiles WHERE user_id = :cid"),
        {"cid": data["caretaker"]["id"]},
    ).fetchone()
    assert cp2.total_reviews == 2
    assert float(cp2.rating) == 4.00


def test_add_review_validation_and_ownership_and_idor_http(client, db, review_setup_data):
    """Tests validation errors, status constraints, and IDOR protection on add_review."""
    data = review_setup_data
    fam_headers = make_auth_headers(data["family"], db)
    car_headers = make_auth_headers(data["caretaker"], db)

    # 1. Non-family role forbidden
    resp_role = client.post(
        "/api/v1/review/add_review",
        json={"booking_id": data["completed_booking_id1"], "rating": 5},
        headers=car_headers,
    )
    assert resp_role.status_code == 403

    # 2. Missing fields
    resp_missing = client.post(
        "/api/v1/review/add_review",
        json={"rating": 5},
        headers=fam_headers,
    )
    assert resp_missing.status_code == 400
    assert resp_missing.json()["message"] == "Booking id and rating are required"

    # 3. Rating out of range (0 or 6)
    resp_range_low = client.post(
        "/api/v1/review/add_review",
        json={"booking_id": data["completed_booking_id1"], "rating": 0},
        headers=fam_headers,
    )
    assert resp_range_low.status_code == 400
    assert resp_range_low.json()["message"] == "Rating must be between 1 and 5"

    resp_range_high = client.post(
        "/api/v1/review/add_review",
        json={"booking_id": data["completed_booking_id1"], "rating": 6},
        headers=fam_headers,
    )
    assert resp_range_high.status_code == 400
    assert resp_range_high.json()["message"] == "Rating must be between 1 and 5"

    # 4. In-progress booking rejection (must be completed)
    resp_inprog = client.post(
        "/api/v1/review/add_review",
        json={"booking_id": data["in_progress_booking_id"], "rating": 5},
        headers=fam_headers,
    )
    assert resp_inprog.status_code == 404
    assert resp_inprog.json()["message"] == "Completed booking not found"

    # 5. IDOR: Other family user tries to review completed booking
    aux_fam = _create_aux_user(db, "family")
    aux_fam_headers = make_auth_headers(aux_fam, db)

    resp_idor = client.post(
        "/api/v1/review/add_review",
        json={"booking_id": data["completed_booking_id1"], "rating": 5},
        headers=aux_fam_headers,
    )
    assert resp_idor.status_code == 404
    assert resp_idor.json()["message"] == "Completed booking not found"


def test_get_caretaker_reviews_pagination_and_role_scoping_http(client, db, review_setup_data):
    """Tests GET /api/v1/review/caretaker_reviews[] endpoint."""
    data = review_setup_data
    fam_headers = make_auth_headers(data["family"], db)
    car_headers = make_auth_headers(data["caretaker"], db)

    # Insert 3 reviews for caretaker
    for i in range(3):
        db.execute(
            text(
                "INSERT INTO reviews (booking_id, family_user_id, caretaker_user_id, rating, comment) "
                "VALUES (:bid, :fid, :cid, :rating, :comment)"
            ),
            {
                "bid": data["completed_booking_id1"],
                "fid": data["family"]["id"],
                "cid": data["caretaker"]["id"],
                "rating": 4 + (i % 2),
                "comment": f"Review comment #{i+1}",
            },
        )
    db.commit()

    # 1. Caretaker gets own reviews automatically without providing caretaker_user_id query param
    resp_car = client.get("/api/v1/review/caretaker_reviews?page=1&limit=2", headers=car_headers)
    assert resp_car.status_code == 200
    body_car = resp_car.json()
    assert body_car["success"] is True
    assert len(body_car["data"]["items"]) == 2
    assert len(body_car["data"]["reviews"]) == 2
    assert body_car["data"]["pagination"]["total"] >= 3

    # 2. Family user retrieves reviews providing caretaker_user_id
    resp_fam = client.get(
        f"/api/v1/review/caretaker_reviews?caretaker_user_id={data['caretaker']['id']}&limit=10",
        headers=fam_headers,
    )
    assert resp_fam.status_code == 200
    assert len(resp_fam.json()["data"]["items"]) >= 3

    # 3. Family user missing caretaker_user_id returns 400
    resp_fam_missing = client.get("/api/v1/review/caretaker_reviews", headers=fam_headers)
    assert resp_fam_missing.status_code == 400
    assert resp_fam_missing.json()["message"] == "Caretaker user id is required"


def test_caretaker_submit_feedback_http(client, db, review_setup_data):
    """Tests POST /api/v1/caretaker/submit_feedback[]."""
    data = review_setup_data
    car_headers = make_auth_headers(data["caretaker"], db)
    fam_headers = make_auth_headers(data["family"], db)

    # 1. Non-caretaker forbidden
    resp_fam = client.post(
        "/api/v1/caretaker/submit_feedback",
        json={"rating": 5, "feedback": "Family trying feedback"},
        headers=fam_headers,
    )
    assert resp_fam.status_code == 403

    # 2. Unapproved caretaker rejected
    aux_car = _create_aux_user(db, "caretaker")
    db.execute(
        text("UPDATE caretaker_profiles SET verification_status = 'pending' WHERE user_id = :uid"),
        {"uid": aux_car["id"]},
    )
    db.commit()
    aux_car_headers = make_auth_headers(aux_car, db)

    resp_unapproved = client.post(
        "/api/v1/caretaker/submit_feedback",
        json={"rating": 5, "feedback": "Pending caretaker feedback"},
        headers=aux_car_headers,
    )
    assert resp_unapproved.status_code == 403
    assert "Only approved caretakers can submit feedback" in resp_unapproved.json()["message"]

    # 3. Approved caretaker submits anonymous feedback via  alias
    resp_ok = client.post(
        "/api/v1/caretaker/submit_feedback",
        json={
            "rating": 5,
            "feedback": "Great platform experience!",
            "suggestion": "Add dark mode to caregiver app.",
            "is_anonymous": True,
        },
        headers=car_headers,
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["message"] == "Feedback submitted successfully"

    # Verify database insert
    db.commit()
    fb_row = db.execute(
        text("SELECT * FROM caretaker_feedback WHERE caretaker_user_id = :cid ORDER BY id DESC LIMIT 1"),
        {"cid": data["caretaker"]["id"]},
    ).fetchone()
    assert fb_row is not None
    assert fb_row.rating == 5
    assert fb_row.is_anonymous == 1
    assert fb_row.feedback == "Great platform experience!"
    assert fb_row.suggestion == "Add dark mode to caregiver app."

    # 4. Validation: empty feedback and suggestion
    resp_empty = client.post(
        "/api/v1/caretaker/submit_feedback",
        json={"rating": 4, "feedback": "", "suggestion": ""},
        headers=car_headers,
    )
    assert resp_empty.status_code == 400
    assert "Feedback or suggestion is required" in str(resp_empty.json()["errors"])


def test_admin_caretaker_feedback_list_and_filters_http(client, db, review_setup_data):
    """Tests GET /api/v1/admin/caretaker_feedback[] list, filters, and statistics."""
    data = review_setup_data
    adm_headers = make_auth_headers(data["admin"], db)
    car_headers = make_auth_headers(data["caretaker"], db)

    # 1. Non-admin forbidden
    resp_non_admin = client.get("/api/v1/admin/caretaker_feedback", headers=car_headers)
    assert resp_non_admin.status_code == 403

    # Insert test feedbacks: 1 named, 1 anonymous
    db.execute(
        text(
            "INSERT INTO caretaker_feedback (caretaker_user_id, rating, feedback, suggestion, is_anonymous, status) "
            "VALUES (:cid, 5, 'Public feedback text', 'Public suggestion', 0, 'pending')"
        ),
        {"cid": data["caretaker"]["id"]},
    )
    db.execute(
        text(
            "INSERT INTO caretaker_feedback (caretaker_user_id, rating, feedback, suggestion, is_anonymous, status) "
            "VALUES (:cid, 2, 'Secret complaint', 'Secret suggestion', 1, 'pending')"
        ),
        {"cid": data["caretaker"]["id"]},
    )
    db.commit()

    # 2. Admin retrieves list via  alias
    resp_list = client.get("/api/v1/admin/caretaker_feedback?per_page=10", headers=adm_headers)
    assert resp_list.status_code == 200
    body = resp_list.json()
    assert body["success"] is True
    assert "items" in body["data"]
    assert "statistics" in body["data"]
    assert "pagination" in body["data"]

    stats = body["data"]["statistics"]
    assert stats["total_feedback"] >= 2
    assert "rating_counts" in stats

    # Verify anonymous masking
    items = body["data"]["items"]
    anon_item = next((i for i in items if i["is_anonymous"] is True), None)
    named_item = next((i for i in items if i["is_anonymous"] is False), None)

    if anon_item:
        assert "caretaker" not in anon_item
    if named_item:
        assert "caretaker" in named_item
        assert named_item["caretaker"]["id"] == data["caretaker"]["id"]

    # 3. Filter by rating=5
    resp_filt = client.get("/api/v1/admin/caretaker_feedback?rating=5", headers=adm_headers)
    assert resp_filt.status_code == 200
    for itm in resp_filt.json()["data"]["items"]:
        assert itm["rating"] == 5

    # 4. Invalid rating filter -> 400
    resp_bad = client.get("/api/v1/admin/caretaker_feedback?rating=99", headers=adm_headers)
    assert resp_bad.status_code == 400


def test_admin_update_feedback_status_and_audit_http(client, db, review_setup_data):
    """Tests POST /api/v1/admin/update_feedback_status[] and audit trail."""
    data = review_setup_data
    adm_headers = make_auth_headers(data["admin"], db)
    car_headers = make_auth_headers(data["caretaker"], db)

    # Insert pending feedback
    db.execute(
        text(
            "INSERT INTO caretaker_feedback (caretaker_user_id, rating, feedback, suggestion, is_anonymous, status) "
            "VALUES (:cid, 4, 'Moderate feedback', 'Suggestions', 0, 'pending')"
        ),
        {"cid": data["caretaker"]["id"]},
    )
    fid = int(db.execute(text("SELECT LAST_INSERT_ID() AS id")).scalar())
    db.commit()

    # 1. Non-admin forbidden
    resp_car = client.post(
        "/api/v1/admin/update_feedback_status",
        json={"feedback_id": fid, "status": "reviewed"},
        headers=car_headers,
    )
    assert resp_car.status_code == 403

    # 2. Admin updates feedback status to 'reviewed' with admin_note via  alias
    resp_up = client.post(
        "/api/v1/admin/update_feedback_status",
        json={
            "feedback_id": fid,
            "status": "reviewed",
            "admin_note": "Reviewed by senior admin and forwarded to mobile dev team.",
        },
        headers=adm_headers,
    )
    assert resp_up.status_code == 200
    body_up = resp_up.json()
    assert body_up["success"] is True
    assert body_up["message"] == "Feedback status updated"
    assert body_up["data"]["status"] == "reviewed"

    # Verify db status and reviewed_at timestamp
    db.commit()
    fb_row = db.execute(
        text("SELECT status, admin_note, reviewed_at FROM caretaker_feedback WHERE id = :fid"),
        {"fid": fid},
    ).fetchone()
    assert str(fb_row.status.value if hasattr(fb_row.status, "value") else fb_row.status) == "reviewed"
    assert fb_row.admin_note == "Reviewed by senior admin and forwarded to mobile dev team."
    assert fb_row.reviewed_at is not None

    # Verify admin audit log
    audit_row = db.execute(
        text("SELECT * FROM admin_audit_logs WHERE action = 'update_caretaker_feedback_status' AND entity_id = :fid"),
        {"fid": fid},
    ).fetchone()
    assert audit_row is not None
    assert audit_row.admin_user_id == data["admin"]["id"]

    # 3. Invalid status returns 400
    resp_invalid = client.post(
        "/api/v1/admin/update_feedback_status",
        json={"feedback_id": fid, "status": "bad_status"},
        headers=adm_headers,
    )
    assert resp_invalid.status_code == 400
    assert "Status must be pending, reviewed, or archived" in str(resp_invalid.json()["errors"])
