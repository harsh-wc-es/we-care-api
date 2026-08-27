# CARETAKER_APP_API_GUIDE.md

## 1. Overview

This guide is written only for the Flutter caretaker mobile app integration. It documents the real caretaker-facing APIs found in the WeCare FastAPI backend and separates missing or recommended APIs into their own section.

Live API base URL:

```text
https://we-care.eu.cc/wecare/api/v1
```

Recommended integration order:

1. API client setup
2. Authentication
3. Secure token storage
4. Profile/status check
5. Caretaker profile setup/update
6. Document upload/status
7. Verification state handling
8. Dashboard
9. Availability
10. Booking list/detail
11. Accept/decline booking
12. Visit lifecycle actions
13. Checklist/tasks
14. Replacement, SOS, feedback, and reviews
15. Earnings
16. Payout summary
17. Notifications
18. Logout and 401 handling

Do not use admin-only APIs in the caretaker app. Do not call family-only APIs from the caretaker app.

## 2. Global API Rules

### Base URL

All endpoint paths in this document are relative to:

```text
https://we-care.eu.cc/wecare/api/v1
```

Example:

```text
POST https://we-care.eu.cc/wecare/api/v1/auth/login
```

### JSON Headers

```http
Content-Type: application/json
Accept: application/json
```

### Authorization Header

Protected endpoints require:

```http
Authorization: Bearer <access_token>
```

The access token is returned by login, registration OTP verification, and refresh-token APIs as `data.access`.

### Multipart Upload Headers

For multipart upload APIs, let Flutter/Dio/http generate the multipart content type and boundary automatically. Do not manually hardcode the boundary.

```http
Authorization: Bearer <access_token>
Accept: application/json
```

### Standard Success Response

```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": {},
  "errors": null
}
```

### Standard Error Response

```json
{
  "success": false,
  "message": "Validation failed",
  "data": null,
  "errors": {
    "field_name": ["Error message"]
  }
}
```

### Flutter Error Handling Rules

| Situation | Flutter Action |
|---|---|
| `success: true` | Read `data` and update screen state. |
| `success: false` | Show `message` and field errors when available. |
| HTTP 401 | Clear token and navigate to login. |
| HTTP 403 | Show role/access denied message. |
| HTTP 404 | Show empty/not found state. |
| HTTP 409 | Refresh the current booking/status and show conflict message. |
| HTTP 422/400 | Show validation errors on the form. |
| Network timeout | Show retry option. |

Backend message extraction priority:

1. `message`
2. `error`
3. first value in `errors.<field>[0]`
4. `data.message`
5. generic fallback message

## 3. Caretaker App State Machine

The backend does not provide one single onboarding-state endpoint. The caretaker app should combine auth profile, caretaker profile, verification status, and document slots.

```text
Launch app
  |
  v
Check secure access token
  |
  +-- No token --> Login/Register
  |
  +-- Token exists --> GET /auth/profile.fastapi
                         |
                         +-- 401 --> Clear token --> Login
                         |
                         v
                    GET /caretaker/profile.fastapi
                         |
                         +-- Profile fields incomplete --> Profile Setup
                         |
                         v
                    GET /caretaker/verification_status.fastapi
                         |
                         +-- Missing/rejected documents --> Document Upload
                         |
                         +-- verification_status = pending --> Verification Waiting
                         |
                         +-- verification_status = approved --> Dashboard
                         |
                         +-- verification_status = rejected --> Rejection Reason + Re-submit
```

Important fields:

| State Check | Endpoint | Fields |
|---|---|---|
| Logged-in user | `GET /auth/profile.fastapi` | `id`, `username`, `email`, `role`, `is_verified`, `is_available` |
| Profile details | `GET /caretaker/profile.fastapi` | `full_name`, `experience_years`, `qualification`, `city`, `verification_status`, `documents_by_type` |
| Document state | `GET /caretaker/verification_status.fastapi` | `verification_status`, `rejection_reason`, `documents`, `document_map`, `documents_by_type` |
| Dashboard capability | `GET /caretaker/dashboard.fastapi` | `capabilities.can_toggle_availability`, `caretaker.can_accept_booking` |

## 4. Authentication APIs

### 4.1 Register Caretaker

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/auth/register_caretaker.fastapi` |
| Auth Required | No |
| Used Screen | Register |
| Purpose | Create a pending caretaker registration and send email OTP. |

Request body:

```json
{
  "full_name": "Caretaker Name",
  "username": "caretaker_user",
  "email": "caretaker@example.com",
  "phone_number": "9999999999",
  "password": "StrongPassword123!",
  "password_confirm": "StrongPassword123!"
}
```

Validation from backend:

| Field | Rule |
|---|---|
| `email` | required, valid email, unique |
| `username` | required, valid username, unique |
| `phone_number` | required, exactly 10 digits, unique |
| `password` | required, must pass password strength helper |
| `password_confirm` | required, must match password |
| `full_name` | optional at backend level, recommended in app |

Success response:

```json
{
  "success": true,
  "message": "Registration OTP sent. Please verify your email.",
  "data": {
    "pending_user_id": 12,
    "email": "caretaker@example.com",
    "username": "caretaker_user",
    "role": "caretaker",
    "phone_number": "9999999999",
    "email_otp_required": true,
    "email_otp_sent": true,
    "otp_expires_in": 600
  },
  "errors": null
}
```

Navigation after success: show registration OTP verification screen.

### 4.2 Verify Registration OTP

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/auth/verify-register-otp.fastapi` |
| Auth Required | No |
| Used Screen | Register OTP |
| Purpose | Verify email OTP and create actual caretaker user/profile. |

Request body:

```json
{
  "email": "caretaker@example.com",
  "otp": "123456"
}
```

Success response:

```json
{
  "success": true,
  "message": "Email verified successfully",
  "data": {
    "access": "<access_token>",
    "refresh": "<refresh_token>",
    "user": {
      "id": 15,
      "email": "caretaker@example.com",
      "username": "caretaker_user",
      "role": "caretaker",
      "is_verified": true,
      "phone_number": "9999999999"
    }
  },
  "errors": null
}
```

Flutter integration notes:

- Save `data.access` and `data.refresh` in secure storage.
- Navigate to caretaker profile setup or document upload flow.

### 4.3 Resend Registration Email OTP

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/auth/resend_email_otp.fastapi` |
| Auth Required | No |
| Used Screen | Register OTP |

Request body:

```json
{
  "email": "caretaker@example.com"
}
```

Success response includes `otp_expires_in` and `resend_cooldown`.

### 4.4 Login

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/auth/login.fastapi` |
| Auth Required | No |
| Used Screen | Login |

Request body:

```json
{
  "login": "caretaker@example.com",
  "password": "StrongPassword123!"
}
```

Accepted login identifiers:

- `login`
- `email`
- `phone_number`
- `username`

Success response:

```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "access": "<access_token>",
    "refresh": "<refresh_token>",
    "user": {
      "id": 15,
      "email": "caretaker@example.com",
      "username": "caretaker_user",
      "role": "caretaker",
      "is_verified": true,
      "phone_number": "9999999999"
    }
  },
  "errors": null
}
```

Navigation after success:

1. Save tokens.
2. Confirm `data.user.role == "caretaker"`.
3. Call profile/status APIs.
4. Route to onboarding, verification, or dashboard state.

### 4.5 Login With OTP Mode

`/auth/login.fastapi` supports optional login OTP mode.

Request body:

```json
{
  "login": "caretaker@example.com",
  "password": "StrongPassword123!",
  "require_otp": "1"
}
```

If enabled, backend returns `otp_required: true`. Then call:

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/auth/verify_login_otp.fastapi` |
| Auth Required | No |

Request:

```json
{
  "email": "caretaker@example.com",
  "otp": "123456"
}
```

Success response shape is the same as normal login.

### 4.6 Get Auth Profile

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/auth/profile.fastapi` |
| Auth Required | Yes |
| Role Required | Any authenticated user |
| Used Screen | Splash, Profile Settings |

For caretakers, this endpoint also adds:

- `is_available`
- `availability_updated_at`

### 4.7 Update Auth Profile

| Item | Value |
|---|---|
| Method | `POST` or `PATCH` |
| URL | `/auth/profile.fastapi` |
| Auth Required | Yes |
| Role Required | Any authenticated user |
| Body | JSON or multipart |

JSON fields:

```json
{
  "username": "new_username",
  "phone_number": "9999999999"
}
```

Multipart field:

| Field | Rule |
|---|---|
| `profile_picture` | JPG, PNG, or WebP, max 2 MB |

### 4.8 Change Password

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/auth/change_password.fastapi` |
| Auth Required | Yes |

Request body:

```json
{
  "current_password": "OldPassword123!",
  "new_password": "NewPassword123!",
  "confirm_password": "NewPassword123!"
}
```

On success, backend says to log in again. Flutter should clear tokens and navigate to login.

### 4.9 Forgot Password Flow

Step 1: request OTP.

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/auth/forgot-password/request-otp.fastapi` |
| Auth Required | No |

```json
{
  "login": "caretaker@example.com"
}
```

Step 2: verify OTP.

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/auth/forgot-password/verify-otp.fastapi` |
| Auth Required | No |

```json
{
  "login": "caretaker@example.com",
  "otp": "123456"
}
```

The reset token is returned as `data.password_reset_token`.

Step 3: reset password.

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/auth/forgot-password/reset.fastapi` |
| Auth Required | No |

```json
{
  "password_reset_token": "<password_reset_token>",
  "new_password": "NewPassword123!",
  "confirm_password": "NewPassword123!"
}
```

Do not use OTP digits as a reset token.

### 4.10 Refresh Access Token

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/auth/refresh_token.fastapi` |
| Auth Required | No |

Request body:

```json
{
  "refresh": "<refresh_token>"
}
```

Compatibility request field:

```json
{
  "refresh_token": "<refresh_token>"
}
```

Success response includes a new `data.access`.

### 4.11 Logout

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/auth/logout.fastapi` |
| Auth Required | Yes |

Request body:

```json
{
  "refresh": "<refresh_token>"
}
```

After success, clear secure storage and navigate to login.

## 5. Caretaker Profile APIs

### 5.1 Get Caretaker Profile

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/caretaker/profile.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |
| Used Screen | Profile, onboarding state, dashboard state |

Response includes user/profile details, pricing tier display fields, verification status, and document slots. Sensitive commission/platform fields are intentionally hidden.

Example response shape:

```json
{
  "success": true,
  "message": "Caretaker profile retrieved",
  "data": {
    "user_id": 15,
    "email": "caretaker@example.com",
    "username": "caretaker_user",
    "phone_number": "9999999999",
    "full_name": "Caretaker Name",
    "gender": "female",
    "date_of_birth": "1995-01-01",
    "experience_years": 3,
    "qualification": "Nursing Assistant",
    "bio": "Experienced home-care caretaker.",
    "address": "Address text",
    "city": "Ahmedabad",
    "state": "Gujarat",
    "pincode": "380001",
    "verification_status": "pending",
    "documents": [],
    "document_map": {},
    "documents_by_type": {}
  },
  "errors": null
}
```

### 5.2 Update Caretaker Profile

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/caretaker/profile.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |
| Used Screen | Profile Setup/Edit |

Request body:

```json
{
  "full_name": "Caretaker Name",
  "gender": "female",
  "date_of_birth": "1995-01-01",
  "experience_years": 3,
  "qualification": "Nursing Assistant",
  "bio": "Experienced home-care caretaker.",
  "address": "Address text",
  "city": "Ahmedabad",
  "state": "Gujarat",
  "pincode": "380001"
}
```

Backend action:

- Updates or creates `caretaker_profiles`.
- Sets `verification_status` to `pending`.
- Sets availability unavailable while under review.

Flutter form-field mapping:

| Flutter Field | API Field | Required | Type | Notes |
|---|---|---:|---|---|
| Full name | `full_name` | Recommended | string | Backend accepts null, app should require it. |
| Gender | `gender` | Optional | string | Use app dropdown if available. |
| Date of birth | `date_of_birth` | Optional | date string | Format `YYYY-MM-DD`. |
| Experience years | `experience_years` | Optional | number | Send integer or numeric string. |
| Qualification | `qualification` | Optional | string | Professional qualification. |
| Bio | `bio` | Optional | string | Short profile summary. |
| Address | `address` | Optional | string | Full address. |
| City | `city` | Optional | string | City. |
| State | `state` | Optional | string | State. |
| Pincode | `pincode` | Optional | string | Postal code. |

## 6. Caretaker Document Verification APIs

This section is critical for caretaker onboarding.

### Canonical Document Types

The backend supports these canonical document types:

| API Document Type | App Label | Required in Bulk Upload |
|---|---|---:|
| `id_proof_front` | ID Proof Front | Yes |
| `id_proof_back` | ID Proof Back | Yes |
| `training_certificate` | Training Certificate | Yes |
| `experience_proof` | Experience Proof | No |
| `police_verification` | Police Verification | Yes |

Supported aliases are accepted by helper logic, but Flutter should send canonical names.
`experience_proof` is optional: it can be uploaded, viewed, approved, or rejected, but it does not block caretaker verification when the four required documents are approved.

### Document Status Mapping

| Backend Status | Flutter Label | UI Action |
|---|---|---|
| not uploaded / null | Not Uploaded | Show upload button |
| `uploaded` | Pending Review | Disable upload unless replace is allowed |
| `pending` | Pending Review | Disable upload unless replace is allowed |
| `approved` | Approved | Show view button |
| `rejected` | Rejected | Show rejection reason and re-upload button |

### 6.1 Get Verification Status

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/caretaker/verification_status.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |

Example response shape:

```json
{
  "success": true,
  "message": "Verification status retrieved",
  "data": {
    "verification_status": "pending",
    "rejection_reason": null,
    "documents": [],
    "document_map": {},
    "documents_by_type": {
      "id_proof_front": {
        "document_id": 1,
        "document_type": "id_proof_front",
        "label": "ID Proof Front",
        "uploaded": true,
        "status": "pending",
        "view_url": "https://we-care.eu.cc/wecare/api/v1/caretaker/document_view?id=1",
        "can_reupload": true
      }
    }
  },
  "errors": null
}
```

### 6.2 Upload Single Document

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/caretaker/upload_document.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |
| Body Type | multipart/form-data |

Multipart fields:

| Field | Required | Notes |
|---|---:|---|
| `document_type` | Yes | Canonical document type. |
| `document` | Yes | File upload field. |

File rules:

| Rule | Value |
|---|---|
| Max size | 5 MB |
| Allowed MIME | `application/pdf`, `image/jpeg`, `image/png` |
| Re-upload | Existing record is updated back to `pending`. |

Example multipart fields:

```text
document_type = police_verification
document = police-verification.pdf
```

Success response:

```json
{
  "success": true,
  "message": "Document uploaded successfully",
  "data": {
    "document_id": 10,
    "document_type": "police_verification",
    "file_path": "uploads/documents/file.pdf",
    "view_url": "https://we-care.eu.cc/wecare/api/v1/caretaker/document_view?id=10"
  },
  "errors": null
}
```

### 6.3 Upload Multiple Documents

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/caretaker/upload_documents.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |
| Body Type | multipart/form-data |

Multipart file fields:

| Field | Required |
|---|---:|
| `id_proof_front` | Yes |
| `id_proof_back` | Yes |
| `training_certificate` | Yes |
| `experience_proof` | No |
| `police_verification` | Yes |

Success response shape:

```json
{
  "success": true,
  "message": "Documents uploaded successfully",
  "data": {
    "uploaded_count": 4,
    "documents": {
      "id_proof_front": {
        "document_id": 1,
        "document_type": "id_proof_front",
        "file_path": "uploads/documents/file.jpg",
        "view_url": "https://we-care.eu.cc/wecare/api/v1/caretaker/document_view?id=1",
        "status": "uploaded"
      }
    }
  },
  "errors": null
}
```

### 6.4 View Document File

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/caretaker/document_view.fastapi?id={document_id}` |
| Auth Required | Yes |
| Role Required | caretaker or admin |
| Response Type | File/blob |

Flutter integration notes:

- Fetch this URL with `Authorization: Bearer <access_token>`.
- Do not open it as a raw browser URL without auth.
- Render image/PDF bytes in-app.
- Supported inline file types include PDF, JPEG, PNG, and WebP.

## 7. Dashboard APIs

### 7.1 Caretaker Dashboard

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/caretaker/dashboard.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |
| Used Screen | Dashboard |

Dashboard supports:

- caretaker availability status
- can-accept-booking flag
- active visit summary
- upcoming visits
- new booking requests
- basic counters

Example response shape:

```json
{
  "success": true,
  "message": "Caretaker dashboard retrieved",
  "data": {
    "caretaker": {
      "id": 15,
      "name": "Caretaker Name",
      "availability_status": "available",
      "is_available": true,
      "manual_availability_enabled": true,
      "availability_locked_by_admin": false,
      "availability_reason": null,
      "can_accept_booking": true,
      "has_active_visit": false,
      "verification_status": "approved"
    },
    "summary": {
      "todays_visits": 0,
      "new_requests": 0
    },
    "active_visit": null,
    "upcoming_visits": [],
    "new_requests": [],
    "capabilities": {
      "can_toggle_availability": true,
      "sos_available": true
    }
  },
  "errors": null
}
```

Compatibility dashboard endpoint:

```text
GET /dashboard/caretaker_dashboard.fastapi
```

This compatibility endpoint is also caretaker-protected and returns a flatter dashboard shape with fields such as `verification_status`, `is_available`, `rating`, `total_reviews`, `pending_requests`, `accepted_bookings`, `completed_bookings`, `total_earnings`, `pending_earnings`, `paid_earnings`, `hold_earnings`, `active_visit`, and `upcoming_visits`.

Use `/caretaker/dashboard.fastapi` for new Flutter integration unless the app has already integrated the compatibility response shape.

### 7.2 Pricing Tiers / Plans

Use this endpoint when the caretaker app needs to show active service pricing/plan information.

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/caretaker/pricing_tiers.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |
| Used Screen | Pricing tiers, profile pricing info, onboarding reference |

Optional query parameters are supported only when matching columns exist in the live `pricing_tiers` table:

- `service_type`
- `city`
- `duration_days`
- `status=active`
- `is_active=true`

Current schema support is exposed in the `filters_supported` object. The endpoint always returns active tiers only for caretaker app safety.

Example response shape:

```json
{
  "success": true,
  "message": "Pricing tiers fetched successfully.",
  "data": {
    "tiers": [
      {
        "id": 1,
        "name": "Basic Care",
        "title": "Basic Care",
        "slug": "basic-care",
        "service_type": null,
        "skill_level": "basic",
        "duration_days": null,
        "duration_label": null,
        "price": 1500,
        "currency": "INR",
        "customer_hourly_rate": 1500,
        "caretaker_hourly_rate": 1200,
        "commission_percent": 20,
        "description": "Basic caretaker support plan",
        "features": [],
        "is_active": true,
        "status": "active",
        "sort_order": null
      }
    ],
    "items": [
      {
        "id": 1,
        "name": "Basic Care"
      }
    ],
    "count": 1,
    "filters_supported": {
      "service_type": false,
      "city": false,
      "duration_days": false,
      "status": false,
      "is_active": true
    }
  },
  "errors": null
}
```

Flutter notes:

- Use `tiers` as the canonical list.
- `items` is an alias for clients that use generic list parsing.
- Use `price` as the display price and `currency` for formatting.
- If `duration_label` is null, hide duration text instead of showing `null`.

## 8. Availability APIs

### 8.1 Get Availability Status

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/caretaker/availability_status.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |

Important fields:

| Field | Meaning |
|---|---|
| `is_available` | Current availability boolean. |
| `manual_availability_enabled` | Whether caretaker manually chose availability. |
| `availability_locked_by_admin` | Admin lock prevents changes. |
| `availability_reason` | Reason such as pending review or active visit. |
| `can_accept_booking` | App can show accepting-ready state. |
| `has_active_visit` | Do not allow available toggle during active visit. |

### 8.2 Update Availability

Preferred endpoint:

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/caretaker/availability.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |

Request body:

```json
{
  "is_available": true
}
```

Important:

- `is_available` must be a real JSON boolean, not string `"true"` or `"1"`.
- Backend may reject availability changes during active visits or admin lock.

Compatibility endpoint:

```text
POST /caretaker/update_availability.fastapi
```

Use `/caretaker/availability.fastapi` for new Flutter integration.

## 9. Booking APIs for Caretaker

### 9.1 New Assigned Requests

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/booking/caretaker_requests.fastapi?page=1&limit=20` |
| Auth Required | Yes |
| Role Required | caretaker |
| Used Screen | New Requests |

Response shape:

```json
{
  "success": true,
  "message": "Caretaker booking requests retrieved",
  "data": {
    "requests": [],
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 0,
      "total_pages": 0
    }
  },
  "errors": null
}
```

### 9.2 Request Detail

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/booking/caretaker_request_detail.fastapi?booking_id={booking_id}` |
| Auth Required | Yes |
| Role Required | caretaker |
| Used Screen | Request Detail |

Response includes:

- `booking`
- `patient`
- `visit`
- `care_tasks`
- `special_instructions`
- `family`
- `actions`
- `enums`

### 9.3 My Bookings

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/booking/my_bookings.fastapi?status=all&page=1&limit=20&paginated=true` |
| Auth Required | Yes |
| Role Required | authenticated user; caretaker data is scoped to authenticated caretaker |
| Used Screen | Assigned, Upcoming, History |

Supported `status` values:

```text
pending, accepted, in_progress, completed, declined, cancelled, all
```

Paginated response shape:

```json
{
  "success": true,
  "message": "Bookings retrieved successfully",
  "data": {
    "items": [],
    "bookings": [],
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 0,
      "total_pages": 0
    }
  },
  "errors": null
}
```

### 9.4 Caretaker Booking Detail

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/caretaker/booking_detail.fastapi?id={booking_id}` |
| Auth Required | Yes |
| Role Required | caretaker |

Use this endpoint for compact caretaker booking detail. Notice the query parameter is `id`, not `booking_id`.

### 9.5 Visit History

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/caretaker/visit_history.fastapi?status=completed,cancelled&page=1&limit=20` |
| Auth Required | Yes |
| Role Required | caretaker |

Supported filters:

- `status=all`
- `status=completed`
- `status=cancelled`
- `status=declined`
- comma-separated combinations
- `start_date`
- `end_date`
- `patient_name`

### Booking Card Field Mapping

| UI Field | API Field | Fallback Field | Notes |
|---|---|---|---|
| Booking ID | `booking_id` | `id` | Show as `#id`. |
| Patient | `patient_name` | `patient.full_name` | Depends on endpoint. |
| Family | `family_name` | `family.name` | May be absent in list. |
| Address | `address` | `booking.address` | Wrap long text. |
| Service type | `service_type` | `care_type` | Display label in app. |
| Date | `booking_date` | `date` | Format in Flutter. |
| Start time | `start_time` | `visit.start_time` | Format in Flutter. |
| End time | `end_time` | `visit.end_time` | May be null. |
| Status | `status` | `booking_status` | Use status badges. |
| Payment status | `payment_status` | none | May be hidden in some views. |
| Earning | `caretaker_earning_amount` | `caretaker_earning` | Use only if returned. |
| Instructions | `special_instructions` | `notes` | May be null. |

## 10. Booking Action APIs

### 10.1 Respond to Booking Request

Preferred endpoint for accept/decline:

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/booking/respond_request.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |
| Used Screen | Request Detail |

Accept request:

```json
{
  "booking_id": 55,
  "action": "accept"
}
```

Decline request:

```json
{
  "booking_id": 55,
  "action": "decline",
  "decline_reason_code": "not_available",
  "decline_note": ""
}
```

Decline reason codes:

```text
not_available
location_too_far
not_comfortable_with_care
personal_reasons
other
```

If reason is `other`, `decline_note` is required.

Success response includes:

- `booking_id`
- `status`
- `visit_otp_required`
- `next_steps`
- `enums`

### 10.2 Compatibility Accept Endpoint

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/booking/accept_booking.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |

Request:

```json
{
  "booking_id": 55
}
```

Use `/booking/respond_request.fastapi` for new app integration.

### 10.3 Compatibility Decline Endpoint

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/booking/reject_booking.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |

Request:

```json
{
  "booking_id": 55,
  "decline_reason_code": "not_available",
  "decline_note": ""
}
```

Use `/booking/respond_request.fastapi` for new app integration.

### 10.4 Cancel Accepted Booking by Caretaker

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/booking/caretaker_cancel_booking.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |

Request:

```json
{
  "booking_id": 55,
  "cancel_reason_code": "sick",
  "cancel_note": "Unable to attend due to illness."
}
```

Allowed reason codes:

```text
sick
emergency
schedule_conflict
travel_issue
personal_reasons
other
```

Rules:

- Pending requests must be declined, not cancelled.
- Only accepted future bookings can be cancelled.
- Backend may create refund/replacement ticket data when applicable.

## 11. Visit Lifecycle APIs

The actual backend flow is:

```text
accepted
  |
  v
verify_start_otp
  |
  v
check_in
  |
  v
in_progress
  |
  v
check_out
  |
  v
completed
```

### Visit Button Mapping

| Booking Status | Flutter Button | API Action | Next Status |
|---|---|---|---|
| `accepted` | Verify OTP | `POST /visit/verify_start_otp.fastapi` | `accepted` with `can_check_in=true` |
| `accepted` after OTP | Check In | `POST /visit/check_in.fastapi` | `in_progress` |
| `in_progress` | Complete Visit | `POST /visit/check_out.fastapi` | `completed` |
| `completed` | No action | none | `completed` |

### 11.1 Verify Visit Start OTP

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/visit/verify_start_otp.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |

Request:

```json
{
  "booking_id": 55,
  "otp": "123456"
}
```

Success response includes `otp_verified: true` and `can_check_in: true`.

### 11.2 Check In

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/visit/check_in.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |

Request:

```json
{
  "booking_id": 55,
  "latitude": 23.0225,
  "longitude": 72.5714,
  "notes": "Arrived at patient location."
}
```

Location is optional in backend code but recommended for the app if permission is granted.

### 11.3 Active Visit

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/visit/active_visit.fastapi?booking_id={booking_id}` |
| Auth Required | Yes |
| Role Required | caretaker |

Returns active in-progress visit payload, including tasks and live notes when available.

### 11.4 Add Visit Note

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/visit/add_note.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |

Request:

```json
{
  "booking_id": 55,
  "note": "Patient completed morning medication."
}
```

`note` is required and limited to 1000 characters.

### 11.5 Complete Visit / Check Out

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/visit/check_out.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |

Request:

```json
{
  "booking_id": 55,
  "latitude": 23.0225,
  "longitude": 72.5714,
  "notes": "Visit completed."
}
```

Success response includes:

- `status: completed`
- `check_out_time`
- `duration_minutes`
- `care_points_earned`
- `payout_status`
- `availability_restored`

### 11.6 Completed Summary

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/visit/completed_summary.fastapi?booking_id={booking_id}` |
| Auth Required | Yes |
| Role Required | caretaker |

Use after checkout to show completion confirmation.

### 11.7 Full Visit Report

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/visit/full_report.fastapi?booking_id={booking_id}` |
| Auth Required | Yes |
| Role Required | caretaker |

Use for completed visit detail/report screen.

### 11.8 View Visit Detail

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/visit/view_visit.fastapi?booking_id={booking_id}` |
| Auth Required | Yes |
| Role Required | caretaker, family, or admin with scoped access |

For caretaker app, backend only allows the assigned caretaker.

## 12. Checklist / Task APIs

### 12.1 List Booking Tasks

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/checklist/booking_tasks.fastapi?booking_id={booking_id}` |
| Auth Required | Yes |
| Role Required | caretaker for assigned accepted/in_progress/completed bookings |

Response:

```json
{
  "success": true,
  "message": "Checklist tasks retrieved",
  "data": {
    "tasks": [
      {
        "id": 1,
        "booking_id": 55,
        "title": "Medication reminder",
        "description": "Give prescribed medicine",
        "status": "pending",
        "completed_at": null
      }
    ]
  },
  "errors": null
}
```

### 12.2 Mark Task Done / Update Status

Simple endpoint:

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/checklist/mark_done.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |

Request:

```json
{
  "task_id": 1,
  "status": "completed"
}
```

Allowed statuses:

```text
pending, ongoing, completed
```

Active visit endpoint:

```text
POST /visit/update_task_status.fastapi
```

Request:

```json
{
  "booking_id": 55,
  "task_id": 1,
  "status": "ongoing"
}
```

Use `/visit/update_task_status.fastapi` during active visits because it also validates active visit context.

Note: task creation is family-only through `/checklist/create_task.fastapi`; caretaker app reads and completes tasks but does not create them.

## 13. Complaints and Feedback APIs

No caretaker complaint create/list/detail API was found. Existing complaint creation/listing endpoints are family-only.

For caretaker-to-platform feedback, use:

### 13.1 Submit Caretaker Feedback

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/caretaker/submit_feedback.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |
| Extra Rule | Caretaker profile must be approved |

Request body:

```json
{
  "rating": 5,
  "feedback": "The app is working well.",
  "is_anonymous": false
}
```

Compatibility field:

```json
{
  "rating": 5,
  "suggestion": "The app is working well.",
  "is_anonymous": false
}
```

Use this for app feedback/support notes, not for booking disputes. If the Flutter product requires booking complaints from caretakers, see Missing or Recommended APIs.

### 13.2 View Reviews Given to Current Caretaker

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/review/caretaker_reviews.fastapi?page=1&limit=20` |
| Auth Required | Yes |
| Role Required | authenticated user; caretaker is scoped to own reviews |
| Used Screen | Profile, Ratings & Reviews |

For a caretaker token, backend ignores any supplied `caretaker_user_id` and uses the authenticated caretaker user id. Do not send another caretaker's id from the Flutter caretaker app.

Response shape:

```json
{
  "success": true,
  "message": "Reviews retrieved successfully",
  "data": {
    "items": [
      {
        "id": 1,
        "booking_id": 55,
        "family_user_id": 31,
        "caretaker_user_id": 15,
        "rating": 4,
        "comment": "Good service and punctual.",
        "created_at": "2026-05-26 10:30:00",
        "family_username": "family_user"
      }
    ],
    "reviews": [],
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 1,
      "total_pages": 1
    }
  },
  "errors": null
}
```

Flutter display fields:

| UI Field | API Field | Notes |
|---|---|---|
| Rating | `rating` | 1 to 5 stars. |
| Review text | `comment` | Show "No comment provided" if null. |
| Booking | `booking_id` | Show as `#id`. |
| Family/user | `family_username` | Do not expose extra data not returned. |
| Date | `created_at` | Format in Flutter. |

## 14. Replacement Ticket APIs

### 14.1 Create Replacement Ticket

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/replacement/create_ticket.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |
| Used Screen | Booking Detail, cannot attend flow |

Request:

```json
{
  "booking_id": 55,
  "complaint_id": null,
  "reason": "Unable to attend due to emergency."
}
```

Rules:

- `booking_id` is required.
- `reason` is required.
- `complaint_id` is optional.
- Booking must belong to the authenticated caretaker.
- If `complaint_id` is provided, it must belong to the same booking.

Success response:

```json
{
  "success": true,
  "message": "Replacement ticket created",
  "data": {
    "replacement_ticket_id": 7,
    "booking_id": 55,
    "requested_by_user_id": 15,
    "original_caretaker_user_id": 15
  },
  "errors": null
}
```

No caretaker replacement-ticket list/detail endpoint was found. See Missing or Recommended APIs.

## 15. SOS / Emergency APIs

### 15.1 Create SOS Alert

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/sos/create_sos.fastapi` |
| Auth Required | Yes |
| Role Required | authenticated user; caretaker is supported |
| Used Screen | Emergency/SOS |

Request:

```json
{
  "booking_id": 55,
  "message": "Emergency assistance required.",
  "latitude": 23.0225,
  "longitude": 72.5714
}
```

Rules:

- `message` is required.
- `booking_id` is optional, but if caretaker sends it, the booking must belong to the caretaker and be `accepted` or `in_progress`.
- `latitude` and `longitude` are optional in backend code.
- Backend rate limits SOS creation.

Success response:

```json
{
  "success": true,
  "message": "SOS alert created",
  "data": {
    "sos_id": 3,
    "booking_id": 55,
    "status": "open"
  },
  "errors": null
}
```

### 15.2 My SOS Alerts

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/sos/my_sos.fastapi?page=1&limit=20` |
| Auth Required | Yes |
| Role Required | authenticated user |

Response includes own SOS alerts as `items` and `sos_alerts`, plus pagination.

Caretaker resolve/cancel endpoint was not found. Admin-only SOS status endpoints exist but must not be used by the caretaker app.

## 16. Earnings APIs

### 16.1 Earnings Dashboard

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/caretaker/earnings_dashboard.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |
| Used Screen | Earnings Overview |

Response fields include:

- `currency`
- `total_earnings`
- `this_week_earnings`
- `this_month_earnings`
- `ready_for_payout`
- `hold_earnings`
- `paid_earnings`
- `disputed_earnings`
- `next_payout_date`
- `payout_note`
- `recent_earnings`

### 16.2 Earnings History

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/caretaker/earnings_history.fastapi?status=all&page=1&limit=20` |
| Auth Required | Yes |
| Role Required | caretaker |

Supported status filters:

```text
hold
ready_for_payout
paid
disputed
all
```

Optional filters:

- `start_date`
- `end_date`
- `page`
- `limit`

Earnings row mapping:

| UI Field | API Field | Notes |
|---|---|---|
| Booking | `booking_id` | Show as `#id`. |
| Patient/Family | `patient_name` | Family may not be present in this endpoint. |
| Visit date | `booking_date` / `visit_label` | Use whichever is returned. |
| Gross amount | Needs verification | Backend hides some customer totals from caretaker views. |
| Caretaker earning | `earning_amount` | Main amount to display. |
| Platform fee | Not returned | Do not show unless backend adds it. |
| Payout status | `payout_status` | Status badge. |
| Hold reason | Needs verification | Not always returned. |
| Completed at | `completed_at` | Format in app. |
| Paid at | `payout_paid_at` | May be null. |

## 17. Payout APIs

### 17.1 Payout Summary

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/caretaker/payout_summary.fastapi` |
| Auth Required | Yes |
| Role Required | caretaker |
| Used Screen | Payout Summary |

Response fields:

- `currency`
- `ready_for_payout`
- `hold_earnings`
- `paid_earnings`
- `disputed_earnings`
- `next_payout_date`
- `payout_note`
- `manual_withdrawal_supported`

No caretaker payout list/detail endpoint was found. Admin payout APIs exist but are not caretaker app APIs.

Payout status values used by earnings/payout logic include:

```text
hold
ready_for_payout
paid
disputed
not_applicable
```

Some admin payout flows may also use:

```text
pending
processing
failed
on_hold
```

For the caretaker app, use only statuses returned by the caretaker endpoints.

## 18. Notifications APIs

### 18.1 Register Device Token

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/notification/register_device.fastapi` |
| Auth Required | Yes |
| Role Required | authenticated user |

Request:

```json
{
  "device_token": "firebase-device-token",
  "platform": "android",
  "app_type": "caretaker"
}
```

Allowed `platform` values:

```text
android, ios, web
```

For caretaker Flutter app, send `app_type: "caretaker"`.

### 18.2 My Notifications

| Item | Value |
|---|---|
| Method | `GET` |
| URL | `/notification/my_notifications.fastapi?page=1&limit=20` |
| Auth Required | Yes |

Optional query params:

- `unread_only`
- `type`

Response includes:

- `items`
- `unread_count`
- `pagination`

### 18.3 Mark Notification Read

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/notification/mark_read.fastapi` |
| Auth Required | Yes |

Request:

```json
{
  "notification_id": 10
}
```

### 18.4 Mark All Notifications Read

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/notification/mark_all_read.fastapi` |
| Auth Required | Yes |

No request body required.

### 18.5 Remove Device Token

| Item | Value |
|---|---|
| Method | `POST` |
| URL | `/notification/remove_device.fastapi` |
| Auth Required | Yes |

Request:

```json
{
  "device_token": "firebase-device-token"
}
```

## 19. File Viewing Rules

Caretaker document files are protected by auth. The app should not attempt to open document URLs in an external browser without headers.

Flutter file viewing rules:

1. Call document `view_url` or `/caretaker/document_view.fastapi?id={document_id}` with `Authorization: Bearer <access_token>`.
2. Request bytes/blob.
3. Inspect response `Content-Type`.
4. Render:
   - `application/pdf` in an in-app PDF viewer.
   - `image/jpeg`, `image/png`, `image/webp` in an image preview widget.
5. For unsupported file type, show a download/open-with fallback only if product allows it.
6. On 401, redirect to login.
7. On 404, show "File not found".

## 20. Error Handling Guide for Flutter

| HTTP Code | Meaning | Flutter Action |
|---:|---|---|
| 200 | Success | Update screen with returned data. |
| 201 | Created | Show success and refresh list/detail. |
| 400 | Bad request/validation | Show field errors. |
| 401 | Unauthorized/token invalid | Clear token and navigate to login. |
| 403 | Role/ownership denied | Show "You are not allowed to perform this action." |
| 404 | Not found | Show empty/not-found state. |
| 409 | Conflict/state changed | Refresh detail and show message. |
| 422 | Validation failed | Show field-specific errors. |
| 429 | Rate limited | Disable retry until cooldown. |
| 500 | Server error | Show retry/support message. |

Common field-error display:

```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "booking_id": ["Booking id is required"]
  }
}
```

## 21. Flutter Integration Notes

- Use Dio or `http` with one centralized API client.
- Store access and refresh tokens in `flutter_secure_storage`.
- Add an auth interceptor for `Authorization: Bearer <access_token>`.
- On HTTP 401, try `/auth/refresh_token.fastapi` if a refresh token exists.
- If refresh fails, clear tokens and navigate to login.
- Never manually set multipart boundary.
- Prevent duplicate button taps on accept, decline, SOS, check-in, and checkout.
- Refresh booking/detail screen after each successful action.
- Do not trust local booking status after state-changing APIs; re-fetch detail.
- Do not use hardcoded dummy data after API integration.
- Keep all date/time formatting in Flutter local UI layer.
- Treat nullable backend fields as normal and display `—` or "Not provided".

## 22. Screen-to-API Mapping

| Flutter Screen | APIs Needed | Notes |
|---|---|---|
| Splash | `GET /auth/profile.fastapi`, `GET /caretaker/profile.fastapi`, `GET /caretaker/verification_status.fastapi` | Decide navigation state. |
| Login | `POST /auth/login.fastapi` | Save access/refresh. |
| Register | `POST /auth/register_caretaker.fastapi` | Then OTP screen. |
| Register OTP | `POST /auth/verify-register-otp.fastapi`, `POST /auth/resend_email_otp.fastapi` | Save tokens after success. |
| Forgot Password | forgot-password request/verify/reset endpoints | Use `password_reset_token`. |
| Profile Setup | `GET/POST /caretaker/profile.fastapi` | Profile completion. |
| Document Upload | `GET /caretaker/verification_status.fastapi`, upload endpoints | Upload and show status. |
| Verification Waiting | `GET /caretaker/verification_status.fastapi` | Poll or manual refresh. |
| Dashboard | `GET /caretaker/dashboard.fastapi` | Summary, active visit, new requests. |
| Pricing Tiers | `GET /caretaker/pricing_tiers.fastapi` | Read-only active pricing/plan list. |
| Availability | `GET /caretaker/availability_status.fastapi`, `POST /caretaker/availability.fastapi` | Toggle availability. |
| Assigned Requests | `GET /booking/caretaker_requests.fastapi` | New pending requests. |
| Booking Detail | `GET /booking/caretaker_request_detail.fastapi`, `GET /caretaker/booking_detail.fastapi?id=` | Use based on request/list source. |
| Booking Actions | `POST /booking/respond_request.fastapi` | Accept/decline. |
| Cancellation | `POST /booking/caretaker_cancel_booking.fastapi` | Accepted future bookings only. |
| Active Visit | visit OTP/check-in/active/check-out APIs | Live visit flow. |
| Checklist | checklist and visit task status APIs | Read and complete tasks. |
| Feedback | `POST /caretaker/submit_feedback.fastapi` | App/platform feedback. |
| Replacement Request | `POST /replacement/create_ticket.fastapi` | Replacement request creation only. |
| SOS | `POST /sos/create_sos.fastapi`, `GET /sos/my_sos.fastapi` | Emergency flow. |
| Earnings | earnings dashboard/history APIs | Earnings overview and rows. |
| Payouts | `GET /caretaker/payout_summary.fastapi` | Summary only currently. |
| Notifications | notification endpoints | Device token and notification list. |
| Profile Settings | `GET/POST /auth/profile.fastapi`, `POST /auth/change_password.fastapi` | Account settings. |
| Logout | `POST /auth/logout.fastapi` | Clear local tokens. |

## 23. Recommended Integration Order

1. Build API client with base URL and JSON decoding.
2. Implement login/register/OTP.
3. Store tokens securely.
4. Add auth interceptor and 401 refresh/relogin behavior.
5. Implement `/auth/profile.fastapi`.
6. Implement caretaker profile setup.
7. Implement document upload/status.
8. Implement verification routing.
9. Implement dashboard.
10. Implement availability.
11. Implement booking lists and detail screens.
12. Implement accept/decline/cancel booking actions.
13. Implement visit lifecycle.
14. Implement checklist/task updates.
15. Implement replacement/SOS/feedback.
16. Implement earnings/payout summary.
17. Implement notifications.
18. Implement logout and account settings.

## 24. Postman / Testing Checklist

| Test | Expected Result |
|---|---|
| Register caretaker | OTP sent and pending user created. |
| Verify register OTP | Tokens returned and caretaker user created. |
| Login success | Access/refresh token returned. |
| Wrong password | 401 error shown. |
| Token saved | App persists session after restart. |
| Auth header sent | Protected APIs return data. |
| Profile incomplete | App routes to profile setup. |
| Profile update | Verification returns pending state. |
| Single document upload | Document becomes pending/uploaded. |
| Bulk document upload | Required documents uploaded. |
| Rejected document | Reason shown and re-upload allowed. |
| Approved documents | Verification waiting/dashboard state works. |
| Dashboard load | Summary and new requests display. |
| Availability change | Toggle updates status. |
| Booking list | Requests/bookings display. |
| Booking detail | Patient, family, tasks, and actions display. |
| Accept booking | Booking becomes accepted. |
| Decline booking | Booking becomes declined. |
| Verify start OTP | `can_check_in` becomes true. |
| Check in | Booking becomes in_progress. |
| Complete visit | Booking becomes completed. |
| Checklist task update | Task status updates. |
| Submit feedback | Feedback saved. |
| Create replacement ticket | Ticket id returned. |
| SOS create | SOS status open returned. |
| Earnings dashboard | Summary displays. |
| Payout summary | Payout totals display. |
| Notifications | List and unread count display. |
| Logout | Refresh token invalidated and app returns to login. |
| 401 response | App redirects to login or refreshes token. |

## 25. Missing or Recommended APIs

These endpoints were not found as caretaker-facing APIs. Add them only if the Flutter caretaker app requires these screens.

### 25.1 Caretaker Replacement Ticket List

| Item | Recommended Value |
|---|---|
| Method | `GET` |
| Path | `/replacement/my_tickets.fastapi` |
| Auth Role | caretaker |
| Purpose | Show caretaker's replacement requests and statuses. |

Suggested response:

```json
{
  "success": true,
  "message": "Replacement tickets retrieved",
  "data": {
    "items": [
      {
        "id": 7,
        "booking_id": 55,
        "reason": "Unable to attend",
        "status": "open",
        "replacement_caretaker_name": null,
        "admin_note": null,
        "created_at": "2026-05-26 10:00:00"
      }
    ]
  },
  "errors": null
}
```

Why Flutter needs it: without this, caretaker can create a ticket but cannot track admin assignment/resolution.

### 25.2 Caretaker Replacement Ticket Detail

| Item | Recommended Value |
|---|---|
| Method | `GET` |
| Path | `/replacement/view_ticket.fastapi?id={ticket_id}` |
| Auth Role | caretaker |
| Purpose | Show one ticket's full status and admin note. |

### 25.3 Caretaker Complaint APIs

Existing complaint APIs are family-only. If caretaker app needs booking dispute/support complaints, add:

| Method | Recommended Path | Purpose |
|---|---|---|
| `POST` | `/complaint/create_caretaker_complaint.fastapi` | Caretaker creates complaint/support request. |
| `GET` | `/complaint/caretaker_complaints.fastapi` | Caretaker lists own complaints. |
| `GET` | `/complaint/caretaker_complaint_detail.fastapi?id={id}` | Caretaker views complaint detail/status. |

### 25.4 Caretaker Payout List and Detail

Only payout summary exists for caretakers. If Flutter needs payout transaction screens, add:

| Method | Recommended Path | Purpose |
|---|---|---|
| `GET` | `/caretaker/payouts.fastapi` | List payout batches/transactions. |
| `GET` | `/caretaker/payout_detail.fastapi?id={payout_id}` | Show payout detail and linked bookings. |

### 25.5 Caretaker SOS Cancel/Resolve

Admin-only SOS status endpoints exist. If caretakers should cancel an accidental SOS, add:

| Method | Recommended Path | Purpose |
|---|---|---|
| `POST` | `/sos/cancel_my_sos.fastapi` | Allow caretaker to cancel own open SOS alert. |

### 25.6 Bank / Payment Method APIs

No caretaker bank-account or payout-method endpoint was confirmed. If payouts require bank details, add:

| Method | Recommended Path | Purpose |
|---|---|---|
| `GET` | `/caretaker/payment_method.fastapi` | Read saved payout method. |
| `POST` | `/caretaker/payment_method.fastapi` | Create/update payout method. |

Security note: never return full bank account numbers; return masked values only.

## 26. Documentation Audit Notes

### Files Scanned

Backend folders/files checked for this guide:

- `api/v1/`
- `app/services/`
- `middleware/`
- `database/schema.sql`
- `database/setup_local.sql`
- `database/migrations/`
- `API_INVENTORY.md`
- `LIVE_API_DOCUMENTATION.md`
- `public/api-docs.html`
- `index.txt`

### Existing APIs Confirmed for Caretaker App

Confirmed endpoint groups:

- Auth/register/login/OTP/forgot password/logout
- Auth profile and password change
- Caretaker profile update/read
- Caretaker document upload/status/view
- Caretaker dashboard
- Availability read/update
- Booking requests/list/detail
- Booking accept/decline/cancel
- Visit OTP/check-in/active/check-out/report
- Checklist read/update
- Replacement ticket creation
- SOS creation and own SOS list
- Earnings dashboard/history
- Payout summary
- Notifications device/list/read/remove
- Caretaker review read endpoint
- Caretaker feedback submission

### APIs Missing or Recommended

Missing caretaker-facing APIs:

- Replacement ticket list/detail
- Caretaker complaint create/list/detail
- Caretaker payout list/detail
- Caretaker SOS cancel/resolve-own alert
- Caretaker bank/payment method management

### Fields Needing Live/Database Verification

These fields depend on live database rows and should be verified with an authenticated caretaker test account:

- Exact booking list item aliases returned by `care_request_list_item`.
- Live UI wording for optional `experience_proof` rejection, if the product team wants custom copy beyond the standard optional document status.
- Exact `verification_status` values used by live admin approval flow.
- Whether earnings history returns hold reasons in live data.
- Whether caretaker payout statuses beyond `hold`, `ready_for_payout`, `paid`, and `disputed` appear in live data.
- Whether profile setup should enforce required fields in Flutter even when backend allows null values.
