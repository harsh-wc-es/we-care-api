# WeCare Live API Documentation

> **Generated**: 2026-05-21  
> **Backend**: FastAPI 8.x REST API (file-based routing)  
> **Database**: MySQL 8.x / MariaDB  
> **Live Base URL**: `https://we-care.eu.cc/wecare/api/v1`

---

## Table of Contents

1. [API Overview](#1-api-overview)
2. [Standard Response Structure](#2-standard-response-structure)
3. [Authentication APIs](#3-authentication-apis)
4. [Patient / Family APIs](#4-patient--family-apis)
5. [Caretaker APIs](#5-caretaker-apis)
6. [Admin APIs](#6-admin-apis)
7. [Booking APIs](#7-booking-apis)
8. [Visit & OTP Flow](#8-visit--otp-flow)
9. [Booking Status Lifecycle](#9-booking-status-lifecycle)
10. [Payment & Earnings Flow](#10-payment--earnings-flow)
11. [Notification APIs](#11-notification-apis)
12. [Complaint APIs](#12-complaint-apis)
13. [SOS Alert APIs](#13-sos-alert-apis)
14. [Replacement Ticket APIs](#14-replacement-ticket-apis)
15. [Review APIs](#15-review-apis)
16. [Checklist APIs](#16-checklist-apis)
17. [Dashboard APIs](#17-dashboard-apis)
18. [Database Important Tables](#18-database-important-tables)
19. [Authentication Usage](#19-authentication-usage)
20. [Error Handling](#20-error-handling)
21. [Live API Testing Notes](#21-live-api-testing-notes)
22. [Current Prototype Limitations](#22-current-prototype-limitations)
23. [API Summary Table](#23-api-summary-table)

---

## 1. API Overview

### Project Overview

**WeCare** is a caretaker-on-demand healthcare platform that connects families/patients with verified professional caretakers. The system supports the complete lifecycle from registration → booking → visit management → payment → payout settlement.

### Backend Technology

| Component | Technology |
|---|---|
| Language | FastAPI 8.x |
| Database | MySQL 8.x / MariaDB |
| Authentication | JWT (HS256) via `PyJWT` |
| Routing | File-based routing (no framework) |
| ORM | Raw PDO with prepared statements |
| Email | FastAPIMailer via SMTP |
| Architecture | Flat FastAPI scripts with helper functions |

### Live Base URL

```
https://we-care.eu.cc/wecare/api/v1
```

### Authentication

```
Authorization: Bearer <JWT_ACCESS_TOKEN>
```

- JWT tokens are issued on login with HS256 signing
- Access token expires in **1 hour** (3600s)
- Refresh token expires in **7 days** (604800s)

### Role System

| Role | Description | Access Scope |
|---|---|---|
| `family` | Patient / Family user | Patient CRUD, booking, payments, complaints, reviews, SOS |
| `caretaker` | Professional caretaker | Availability, visit management, earnings, booking requests |
| `admin` | Platform administrator | Full platform management, payouts, user management, reports |

### Request Format Support

| Content-Type | Usage |
|---|---|
| `application/json` | All non-file endpoints (recommended for Flutter) |
| `application/x-www-form-urlencoded` | Backward compatible |
| `multipart/form-data` | Required for file uploads (profile picture, documents, complaint proof) |

---

## 2. Standard Response Structure

All API responses use a consistent JSON envelope provided by `app/services/response`.

### Success Response

```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": {
    "id": 1,
    "field": "value"
  },
  "errors": null
}
```

### Error Response

```json
{
  "success": false,
  "message": "Validation failed",
  "data": null,
  "errors": {
    "email": ["Email is required"],
    "password": ["Password must be at least 8 characters"]
  }
}
```

### Envelope Fields

| Field | Type | Description |
|---|---|---|
| `success` | `boolean` | `true` for success, `false` for failure |
| `message` | `string` | Human-readable status message |
| `data` | `object\|array\|null` | Response payload on success |
| `errors` | `object\|null` | Field-level validation errors on failure |

### HTTP Status Codes Used

| Code | Meaning |
|---|---|
| `200` | Success |
| `201` | Created |
| `204` | No Content (CORS preflight) |
| `400` | Bad Request / Validation Error |
| `401` | Unauthorized / Invalid Token |
| `403` | Forbidden / Role Mismatch |
| `404` | Resource Not Found |
| `405` | Method Not Allowed |
| `409` | Conflict / Duplicate State |
| `429` | Rate Limited |
| `500` | Server Error |

---

## 3. Authentication APIs

### 3.1 Register Patient / Family

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/register_patient` |
| **Purpose** | Register a family/patient user account |
| **Auth Required** | No |

**Request Body:**

```json
{
  "email": "user@example.com",
  "username": "john_doe",
  "phone_number": "9876543210",
  "password": "SecurePass123",
  "password_confirm": "SecurePass123"
}
```

**Validation Rules:**
- `email` — required, valid email format, unique
- `username` — required, 3–30 chars, `a-z 0-9 _ .` only, unique (case-insensitive), stored lowercase
- `phone_number` — required, 10-digit numeric, unique
- `password` — required, min 6 characters
- `password_confirm` — required, must match password

**Success Response (200):**

```json
{
  "success": true,
  "message": "Registration successful. Please login.",
  "data": {
    "id": 42,
    "email": "user@example.com",
    "username": "john_doe",
    "role": "family",
    "phone_number": "9876543210"
  },
  "errors": null
}
```

**Duplicate Profile Response (409):**

```json
{
  "success": false,
  "message": "Patient profile already exists",
  "data": null,
  "errors": {
    "patient": [
      "Only one patient profile is allowed per family account"
    ]
  }
}
```

Flutter should call `update_patient` to edit the existing profile after the first patient profile has been created.

**Error Responses:**
- `400` — All fields are required · Invalid email format · Invalid phone number · Password too short · Password confirmation does not match · User already exists
- `405` — Method not allowed

---

### 3.2 Register Caretaker

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/register_caretaker` |
| **Purpose** | Register a caretaker account (creates blank `caretaker_profiles` row) |
| **Auth Required** | No |

**Request Body:**

```json
{
  "email": "caretaker@example.com",
  "username": "jane_ct",
  "phone_number": "9876543211",
  "password": "SecurePass123",
  "password_confirm": "SecurePass123"
}
```

**Success Response (200):**

```json
{
  "success": true,
  "message": "Registration successful. Please login.",
  "data": {
    "id": 43,
    "email": "caretaker@example.com",
    "username": "jane_ct",
    "role": "caretaker",
    "phone_number": "9876543211"
  },
  "errors": null
}
```

**Error Responses:**
- `400` — All fields are required · Password confirmation does not match · User already exists
- `405` — Method not allowed

---

### 3.3 Unified Register (Canonical)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/register` |
| **Purpose** | Canonical registration with pending user flow and OTP verification |
| **Auth Required** | No |

**Request Body:**

```json
{
  "email": "user@example.com",
  "username": "new_user",
  "phone_number": "9876543212",
  "password": "SecurePass123",
  "password_confirm": "SecurePass123",
  "role": "family"
}
```

> Registration creates a `pending_users` row. An OTP is emailed for verification via `verify-register-otp`.

---

### 3.4 Verify Registration OTP

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/verify-register-otp` |
| **Purpose** | Verify registration OTP and move from pending to verified user |
| **Auth Required** | No |

**Request Body:**

```json
{
  "email": "user@example.com",
  "otp": "123456"
}
```

---

### 3.5 Login

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/login` |
| **Purpose** | Authenticate by email, phone, or username and issue JWT tokens |
| **Auth Required** | No |

**Request Body:**

```json
{
  "email": "user@example.com",
  "password": "SecurePass123"
}
```

> You can also send `phone_number` or `username` instead of `email`.

**Success Response (200):**

```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "access": "<JWT_ACCESS_TOKEN>",
    "refresh": "<JWT_REFRESH_TOKEN>",
    "user": {
      "id": 42,
      "email": "user@example.com",
      "username": "john_doe",
      "role": "family",
      "is_verified": true,
      "phone_number": "9876543210"
    }
  },
  "errors": null
}
```

**Error Responses:**
- `400` — Please provide email/phone/username and password
- `401` — Invalid credentials
- `403` — Account is inactive
- `405` — Method not allowed

---

### 3.6 Verify Login OTP (Optional 2FA)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/verify_login_otp` |
| **Purpose** | Verify login OTP when `require_otp=1` on login |
| **Auth Required** | No |

**Request Body:**

```json
{
  "email": "user@example.com",
  "otp": "123456"
}
```

---

### 3.7 Refresh Access Token

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/refresh_token` |
| **Purpose** | Replace stored access token using a valid refresh token |
| **Auth Required** | Refresh token required in body |

**Request Body:**

```json
{
  "refresh": "<REFRESH_TOKEN>"
}
```

> Also accepts `refresh_token` as field name.

**Success Response (200):**

```json
{
  "success": true,
  "message": "Access token refreshed successfully",
  "data": {
    "access": "<NEW_ACCESS_TOKEN>",
    "user": {
      "id": 42,
      "email": "user@example.com",
      "username": "john_doe",
      "phone_number": "9876543210",
      "role": "family",
      "is_verified": true
    }
  },
  "errors": null
}
```

**Error Responses:**
- `400` — Refresh token is required
- `401` — Invalid or expired refresh token · Invalid token type · Refresh token not found or logged out · User not found or inactive

---

### 3.8 Logout

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/logout` |
| **Purpose** | Blacklist a refresh token for the authenticated user |
| **Auth Required** | Yes |

**Headers:**
```
Authorization: Bearer <ACCESS_TOKEN>
```

**Request Body:**

```json
{
  "refresh": "<REFRESH_TOKEN>"
}
```

**Success Response (200):**

```json
{
  "success": true,
  "message": "Logged out successfully",
  "data": null,
  "errors": null
}
```

---

### 3.9 Get Profile

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/profile` |
| **Purpose** | Retrieve current authenticated user profile |
| **Auth Required** | Yes (any role) |

**Success Response (200):**

```json
{
  "success": true,
  "message": "Profile retrieved",
  "data": {
    "id": 42,
    "email": "user@example.com",
    "username": "john_doe",
    "phone_number": "9876543210",
    "role": "family",
    "is_verified": true,
    "is_active": true,
    "profile_picture": "uploads/profiles/abc123.jpg"
  },
  "errors": null
}
```

---

### 3.10 Update Profile

| Property | Value |
|---|---|
| **Method** | `POST` or `PATCH` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/profile` |
| **Purpose** | Update username, phone number, and optional profile picture |
| **Auth Required** | Yes (any role) |

**Headers:**
```
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: multipart/form-data
```

**Request Body (form-data):**

| Field | Type | Required |
|---|---|---|
| `username` | string | Optional |
| `phone_number` | string | Optional |
| `profile_picture` | file | Optional |

**Success Response (200):**

```json
{
  "success": true,
  "message": "Profile updated successfully",
  "data": {
    "id": 42,
    "username": "updated_user",
    "phone_number": "9876543210",
    "profile_picture": "uploads/profiles/randomname.jpg"
  },
  "errors": null
}
```

---

### 3.11 Deactivate Account

| Property | Value |
|---|---|
| **Method** | `DELETE` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/profile` |
| **Purpose** | Soft deactivate current account (`is_active=0`) |
| **Auth Required** | Yes (any role) |

---

### 3.12 Change Password

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/change_password` |
| **Purpose** | Change password with current password verification |
| **Auth Required** | Yes (any role) |

**Request Body:**

```json
{
  "current_password": "OldPass123",
  "new_password": "NewPass456",
  "new_password_confirm": "NewPass456"
}
```

**Success Response (200):**

```json
{
  "success": true,
  "message": "Password changed successfully. Please login again.",
  "data": null,
  "errors": null
}
```

> All JWT sessions are blacklisted on success. Flutter should redirect to login.

---

### 3.13 Forgot Password — Request OTP (Canonical)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/forgot-password/request-otp` |
| **Purpose** | Request password reset OTP via email/phone/username |
| **Auth Required** | No |

**Request Body:**

```json
{
  "login": "user@example.com"
}
```

> Returns generic success to prevent account enumeration.

---

### 3.14 Forgot Password — Verify OTP (Canonical)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/forgot-password/verify-otp` |
| **Purpose** | Verify forgot-password OTP and receive a single-use reset token |
| **Auth Required** | No |

**Request Body:**

```json
{
  "login": "user@example.com",
  "otp": "123456"
}
```

---

### 3.15 Forgot Password — Reset (Canonical)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/forgot-password/reset` |
| **Purpose** | Reset password using the single-use token from verify-otp |
| **Auth Required** | No |

**Request Body:**

```json
{
  "password_reset_token": "<RESET_TOKEN>",
  "new_password": "NewSecure123",
  "confirm_password": "NewSecure123"
}
```

The reset token is returned by the verify step as `data.password_reset_token`. Clients may support older `reset_token` or `token` aliases if an older backend returns them, but must never use the OTP digits as the reset token.

---

### 3.16 Forgot Password — Legacy (Deprecated)

| Endpoint | Purpose |
|---|---|
| `POST .../auth/forgot_password` | Legacy: send reset token by email |
| `POST .../auth/reset_password` | Legacy: reset password with email + token |

> ⚠️ **Deprecated for Flutter.** Use the canonical `/forgot-password/*` three-step flow above.

---

### 3.17 Authenticated Password Reset via OTP

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/request-password-reset-otp` |
| **Purpose** | Request OTP for logged-in password reset (no old password needed) |
| **Auth Required** | Yes (any role) |

**Success Response (200):**

```json
{
  "success": true,
  "message": "OTP sent successfully",
  "data": {
    "email": "an***@gmail.com",
    "expires_in_seconds": 600
  },
  "errors": null
}
```

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/reset-password-with-otp` |
| **Purpose** | Reset password using OTP while logged in |
| **Auth Required** | Yes (any role) |

**Request Body:**

```json
{
  "otp": "123456",
  "new_password": "NewPass123",
  "new_password_confirm": "NewPass123"
}
```

---

### 3.18 Verify Email OTP

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/verify_email` |
| **Purpose** | Verify registration email OTP and mark `is_verified=1` |
| **Auth Required** | No |

**Request Body:**

```json
{
  "email": "user@example.com",
  "otp": "123456"
}
```

---

### 3.19 Resend Email OTP

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/auth/resend_email_otp` |
| **Purpose** | Regenerate and send registration email OTP with cooldown |
| **Auth Required** | No |

**Request Body:**

```json
{
  "email": "user@example.com"
}
```

**Success Response (200):**

```json
{
  "success": true,
  "message": "Email OTP resent successfully",
  "data": {
    "email_otp_sent": true,
    "otp_expires_in": 600,
    "resend_cooldown": 60
  },
  "errors": null
}
```

---

## 4. Patient / Family APIs

> **Role Required:** `family` (Bearer token required)

### 4.1 Add Patient

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/patient/add_patient` |
| **Purpose** | Create the single elder/patient profile for the current family user |

**Request Body:**

```json
{
  "patient_name": "Rajesh Shah",
  "age": 72,
  "gender": "male",
  "medical_condition": "Diabetes, Hypertension",
  "allergies": "Penicillin",
  "medications": "Metformin 500mg",
  "special_instructions": "Requires assistance with mobility",
  "mobility_status": "wheelchair",
  "care_type": "daily_care"
}
```

**Success Response (200):**

```json
{
  "success": true,
  "message": "Patient added successfully",
  "data": {
    "id": 15
  },
  "errors": null
}
```

---

### 4.2 List Patients

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/patient/list_patients` |
| **Purpose** | Return current family's patient profile list; contains at most one profile |

**Query Params:** accepted for compatibility, but the response is capped to one profile.

**Success Response (200):**

```json
{
  "success": true,
  "message": "Patients retrieved successfully",
  "data": [
    {
      "id": 15,
      "family_user_id": 42,
      "patient_name": "Rajesh Shah",
      "age": 72,
      "gender": "male",
      "medical_condition": "Diabetes",
      "care_type": "daily_care"
    }
  ],
  "errors": null
}
```

---

### 4.3 View Patient

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/patient/view_patient?id={patient_id}` |
| **Purpose** | Retrieve one patient owned by current family user |

---

### 4.4 Update Patient

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/patient/update_patient` |
| **Purpose** | Update an owned patient record |

**Request Body:**

```json
{
  "id": 15,
  "patient_name": "Rajesh Shah",
  "age": 73,
  "medical_condition": "Diabetes, Hypertension (controlled)"
}
```

---

### 4.5 Delete Patient

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/patient/delete_patient` |
| **Purpose** | Delete an owned patient record |

**Request Body:**

```json
{
  "id": 15
}
```

---

## 5. Caretaker APIs

> **Role Required:** `caretaker` (Bearer token required)

### 5.1 Get Caretaker Profile

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/profile` |
| **Purpose** | Retrieve caretaker profile details |

---

### 5.2 Update Caretaker Profile

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/profile` |
| **Purpose** | Update caretaker profile (resets verification to pending) |

**Request Body:**

```json
{
  "full_name": "Amit Sharma",
  "gender": "male",
  "date_of_birth": "1990-05-15",
  "experience_years": 5,
  "qualification": "BSc Nursing",
  "bio": "Experienced caretaker specializing in elder care",
  "address": "123 Main Street, Ahmedabad",
  "city": "Ahmedabad",
  "state": "Gujarat",
  "pincode": "380015"
}
```

---

### 5.3 List Caretakers (Family / All Roles)

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/list_caretaker` |
| **Purpose** | List available, approved caretakers |
| **Auth Required** | Yes (family, caretaker, admin) |

**Query Params:** `?page=1&limit=20&online_only=true&city=Ahmedabad`

> Family users see customer-facing pricing only (`pricing_tier`, `skill_level`, `customer_hourly_rate`). Caretaker share and platform commission are hidden.

---

### 5.4 Availability Status

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/availability_status` |
| **Purpose** | Get caretaker's current availability status with full payload |

---

### 5.5 Update Availability

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/update_availability` |
| **Purpose** | Toggle caretaker availability on/off |

**Request Body:**

```json
{
  "is_available": true
}
```

> Blocked when admin-locked (403). Blocked during active visit (409).

---

### 5.6 Get Availability Schedule

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/availability` |
| **Purpose** | Get caretaker availability schedule |

---

### 5.7 Booking Requests (Pending)

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/requests` |
| **Purpose** | List pending booking requests for the caretaker |

---

### 5.8 Booking Detail

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/booking_detail?booking_id={id}` |
| **Purpose** | View detailed booking information for assigned bookings |

---

### 5.9 Visit History

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/visit_history` |
| **Purpose** | Grouped caretaker history (completed, cancelled, declined visits) |

**Query Params:** `?page=1&limit=20&status=all&start_date=&end_date=&patient_name=`

> Groups by `Today`, `Yesterday`, `This Week`, `Earlier`.

---

### 5.10 Earnings Dashboard

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/earnings_dashboard` |
| **Purpose** | Caretaker earnings overview |

> Shows `total_earnings`, `pending_earnings`, `paid_earnings`, `hold_earnings` — all based on `caretaker_earning_amount` only.

---

### 5.11 Earnings History

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/earnings_history` |
| **Purpose** | Paginated list of individual earning records |

---

### 5.12 Payout Summary

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/payout_summary` |
| **Purpose** | Summary of payout batches for the caretaker |

---

### 5.13 Caretaker Pricing Tiers

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/pricing_tiers` |
| **Auth** | Yes |
| **Role** | `caretaker` |
| **Purpose** | Read-only active pricing tiers/plans for the caretaker Flutter app |

**Query Params:** `service_type`, `city`, and `duration_days` are accepted only if the live `pricing_tiers` schema has those columns. Current schema supports `is_active=true` and active-only `status` behavior. Inactive tiers are not exposed to the caretaker app.

**Success Response:**

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
    "count": 1
  },
  "errors": null
}
```

---

### 5.14 Upload Document

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/upload_document` |
| **Purpose** | Upload verification documents (ID, certificate, etc.) |

**Headers:** `Content-Type: multipart/form-data`

**Request Body (form-data):**

| Field | Type | Required |
|---|---|---|
| `document_type` | string | Yes |
| `document` | file | Yes |

---

### 5.14 Verification Status

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/verification_status` |
| **Purpose** | Check caretaker verification/approval status |

The response includes `is_verified`, `otp_verified`, `caretaker_verification_status`, `account_status`, `rejected_documents`, `documents`, `document_map`, and `documents_by_type`. `users.is_verified` means only OTP/email/mobile verification and is not changed by caretaker document approval/rejection, reupload, or ban flows. Each document slot includes `id`, `document_id`, `document_type`, `display_name`, `required`, `optional`, `status`, `admin_note`, `rejection_reason`, `needs_reupload`, `blocks_verification`, and `can_reupload`. Rejected required documents expose the admin rejection reason and block verification until reuploaded/approved; rejected optional `experience_proof` does not block verification.

When a caretaker reuploads a rejected document, `upload_document` replaces the existing document row for that type, resets status to `pending`, and clears `admin_note`/`rejection_reason`. Bulk `upload_documents` resets status to `uploaded` and also clears the rejection note.

---

### 5.15 Submit Feedback

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/caretaker/submit_feedback` |
| **Purpose** | Submit platform feedback as a caretaker |

**Request Body:**

```json
{
  "rating": 4,
  "feedback": "Great platform, easy to use",
  "suggestion": "Add in-app chat feature",
  "is_anonymous": false
}
```

---

## 6. Admin APIs

> **Role Required:** `admin` (Bearer token required)

### 6.1 All Users

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/users` |
| **Purpose** | List all users with filters and pagination |

**Query Params:** `?page=1&limit=20&role=caretaker&status=active&search=john&online_only=true&active_visit=true&admin_locked=true&availability_reason=on_visit`

When `role=caretaker`, each admin table item includes the same normalized caretaker fields used by caretaker detail: `caretaker_id`, `full_name`, `phone`, `city`, `gender`, `dob`, `experience`, `specialization`, `pricing_tier_id`, `pricing_tier`, `pricing_tier_label`, `customer_hourly_rate`, `caretaker_hourly_rate`, `platform_commission_percentage`, `average_rating`, `rating_count`, and availability state. `average_rating` is `null` with `rating_count=0` when no ratings exist; city and experience remain `null` when not stored.

Availability uses separate meanings: `availability_status` is the current operational state (`available`, `unavailable`, `busy`, `offline`), while `availability_source` is `caretaker_manual`, `admin_override`, or `system_active_visit`. Admin overrides set `admin_locked=1`; manual caretaker control sets `admin_locked=0` and exposes `manual_preference=on|off`.

---

### 6.1a Admin Patient Profile

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/patient_profile?family_user_id=312` |
| **Purpose** | View the `patient_details` profile linked to a family user |

**Success Response (200):**

```json
{
  "success": true,
  "message": "Patient profile retrieved",
  "data": {
    "id": 3,
    "family_user_id": 312,
    "patient_name": "harsh patient",
    "age": 50,
    "gender": "male",
    "medical_condition": "cant walk",
    "allergies": null,
    "medications": "none",
    "special_instructions": "none",
    "mobility_status": null,
    "care_type": null,
    "created_at": "...",
    "updated_at": "..."
  },
  "errors": null
}
```

If the family user exists but no patient profile exists, this API returns `success=true`, message `No patient profile found`, and `data=null`.

---

### 6.2 Update User Status

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/update_user_status` |
| **Purpose** | Activate or deactivate a user account |

**Request Body:**

```json
{
  "user_id": 42,
  "is_active": false
}
```

---

### 6.3 Pending Caretakers

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/pending_caretakers` |
| **Purpose** | List caretakers awaiting admin approval |

---

### 6.4 View Caretaker Detail

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/view_caretaker?user_id={id}` |
| **Purpose** | Full caretaker profile including documents and availability detail |

The detail response uses the same normalized fields as the admin caretaker table. It keeps legacy document rows in `documents` and adds null-safe `document_map` keys for `id_proof_front`, `id_proof_back`, `training_certificate`, `experience_proof`, and `police_verification`. Rejected document slots include `status`, `admin_note`, and `rejection_reason` for the admin preview modal.

The same response also includes actual user reviews for the caretaker. `reviews` is the canonical array and each item includes `id`, `booking_id`, `booking_reference`, `family_user_id`, `family_name`, `family_email`, `patient_name`, `rating`, `review`, `comment`, `feedback`, and `created_at`. `review_stats` includes `average_rating`, `total_reviews`, `rating_count`, and one-to-five star distribution counts. If no review exists, `reviews` is `[]` and the stats values are zero.

---

### 6.5 Approve Caretaker

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/approve_caretaker` |
| **Purpose** | Approve a pending caretaker with pricing tier assignment |

**Request Body:**

```json
{
  "user_id": 43,
  "pricing_tier_id": 2,
  "customer_hourly_rate": 500,
  "caretaker_hourly_rate": 350,
  "pricing_override_enabled": false
}
```

> `pricing_tier_id` is required. Copies final rates into `caretaker_profiles`.

---

### 6.6 Reject Caretaker

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/reject_caretaker` |
| **Purpose** | Reject a pending caretaker with reason |

**Request Body:**

```json
{
  "user_id": 43,
  "rejection_reason": "Incomplete documentation"
}
```

---

### 6.6a Reject Caretaker Document

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/reject_document` |
| **Purpose** | Reject one uploaded caretaker verification document with an admin reason |

**Request Body:**

```json
{
  "document_id": 21,
  "reason": "Document is unclear. Please upload again."
}
```

Accepted aliases: `id` may replace `document_id`; `admin_note` or `rejection_reason` may replace `reason`.

**Success Response:**

```json
{
  "success": true,
  "message": "Document rejected successfully",
  "data": {
    "document": {
      "id": 21,
      "document_type": "id_proof_front",
      "status": "rejected",
      "admin_note": "Document is unclear. Please upload again."
    }
  },
  "errors": null
}
```

This endpoint is admin-only, does not delete the uploaded file, and only accepts caretaker verification document types: `id_proof_front`, `id_proof_back`, `training_certificate`, `experience_proof`, and `police_verification` plus legacy aliases.

---

### 6.6b Caretaker Verification Categories

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/caretaker_verification?status=pending_review` |
| **Purpose** | List caretakers by verification category with document counts and action flags |

Supported `status` values: `pending_review`, `approved`, `needs_resubmission`, `rejected`, `banned`, and `all`.

Rows include `document_summary`, `total_required_documents`, `uploaded_documents_count`, `pending_documents_count`, `approved_documents_count`, `rejected_documents_count`, `can_approve`, `can_reject`, `can_ban`, `can_unban`, and `latest_reupload_at`. The verification summary counts only four required documents: `id_proof_front`, `id_proof_back`, `training_certificate`, and `police_verification`. `experience_proof` is returned as an optional slot and does not block approval.

---

### 6.6c Approve Caretaker Document

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/caretaker_documents/approve` |
| **Purpose** | Approve one caretaker verification document and recalculate profile status |

```json
{
  "caretaker_user_id": 12,
  "document_id": 5
}
```

---

### 6.6d Reject Selected Caretaker Documents

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/caretaker_documents/reject_selected` |
| **Purpose** | Reject selected documents together, with one reason per selected document |

```json
{
  "caretaker_user_id": 12,
  "documents": [
    {
      "document_id": 5,
      "reason": "Image is blurry"
    }
  ]
}
```

Successful rejection moves the caretaker to `needs_resubmission` where supported, with a `rejected` fallback on older schemas until the migration is applied.

---

### 6.6e Approve Caretaker After Documents

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/caretakers/approve` |
| **Purpose** | Approve a caretaker only after all four required documents are approved |

```json
{
  "caretaker_user_id": 12,
  "pricing_tier_id": 2
}
```

If required documents are missing, pending, or rejected, the API returns: `Cannot approve caretaker until all required documents are approved.` Optional `experience_proof` may be missing or rejected without blocking caretaker approval.

This admin approval endpoint updates `caretaker_profiles.verification_status`; it does not update `users.is_verified`.

---

### 6.6f Ban Caretaker

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/caretakers/ban` |
| **Purpose** | Ban a caretaker at any time and disable booking availability |

Ban uses caretaker/account status fields (`caretaker_profiles.verification_status`, ban metadata, and `users.is_active`) and does not clear `users.is_verified`.

```json
{
  "caretaker_user_id": 12,
  "reason": "Fake documents"
}
```

Ban disables availability, sets the caretaker status to `banned` where supported, deactivates the user account, and prevents booking availability.

---

### 6.7 All Bookings

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/bookings` |
| **Purpose** | List all bookings with filters |

**Query Params:** `?page=1&limit=20&status=pending&search=&start_date=&end_date=`

---

### 6.8 Booking Detail

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/booking_detail?booking_id={id}` |
| **Purpose** | Full booking detail with financial breakdown |

Cancelled booking detail includes `paid_amount`, `remaining_amount`, `payment_status`, `refund_eligible`, `refund_percentage`, `refund_amount`, `refund_status`, `cancellation_fee`, a concrete `refund` object from `booking_refunds` or `refund: null`, and a `refund_warning` when a cancelled paid booking has no refund row.

```json
{
  "success": true,
  "message": "Booking detail retrieved",
  "data": {
    "booking_id": 12,
    "status": "cancelled",
    "paid_amount": 400,
    "remaining_amount": 400,
    "payment_status": "pending",
    "refund_eligible": true,
    "refund_percentage": 50,
    "refund_amount": 200,
    "refund_status": "processed",
    "cancellation_fee": 200,
    "refund_warning": null,
    "refund": {
      "id": 1,
      "paid_amount": 400,
      "refund_percentage": 50,
      "refund_amount": 200,
      "status": "processed",
      "reason": "Booking cancelled refund",
      "refund_method": null,
      "refund_transaction_id": null,
      "approved_at": "2026-05-22T11:37:00+05:30",
      "processed_at": "2026-05-22T11:37:41+05:30",
      "created_at": "2026-05-22T11:36:11+05:30"
    }
  },
  "errors": null
}
```

---

### 6.9 Cancel Booking (Admin)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/cancel_booking` |
| **Purpose** | Admin cancels any booking with reason |

**Request Body:**

```json
{
  "booking_id": 101,
  "reason": "Administrative decision"
}
```

**Refund behavior:** Admin cancellation uses successful `payments.amount` rows only. It updates the booking refund snapshot and creates one pending `booking_refunds` row when the 24h/12h cancellation policy yields a payable refund. Partial payments refund only the successful amount paid.

**Success response includes:**

```json
{
  "success": true,
  "message": "Booking cancelled successfully",
  "data": {
    "booking_id": 101,
    "refund": {
      "paid_amount": 400,
      "refund_eligible": true,
      "refund_percentage": 100,
      "refund_amount": 400,
      "refund_status": "pending",
      "refund_record_created": true
    }
  },
  "errors": null
}
```

---

### 6.10 Pricing Tiers

| Endpoint | Method | Purpose |
|---|---|---|
| `.../admin/pricing_tiers` | `GET` | List all pricing tiers |
| `.../admin/pricing_tier_detail?id={id}` | `GET` | Get single tier detail |
| `.../admin/create_pricing_tier` | `POST` | Create new tier |
| `.../admin/update_pricing_tier` | `POST` | Update existing tier |
| `.../admin/delete_pricing_tier` | `POST` or `DELETE` | Deactivate a tier |
| `.../admin/update_caretaker_pricing` | `POST` | Update caretaker's pricing |
| `.../admin/update_caregiver_tier_pricing` | `POST` | Update caregiver tier, rates, commission, and pricing history |

`POST .../admin/update_caregiver_tier_pricing` is admin-only and is used by the Admin Web caregiver detail pricing section. It accepts `caretaker_user_id`, `tier_id`, `customer_rate_per_hour`, `caregiver_rate_per_hour`, `commission_percent`, and `admin_note`; aliases include `caregiver_user_id`, `user_id`, `tier`, `customer_rate`, `caregiver_rate`, `commission`, and `reason`. It validates caretaker role, active tier, numeric rates, caregiver rate <= customer rate, and commission 0-100. It cannot change role or password. If `caregiver_pricing_history` exists, it inserts a history row.

**Create Pricing Tier Request:**

```json
{
  "name": "Professional",
  "description": "Experienced medical caretakers",
  "skill_level": "professional",
  "customer_hourly_rate": 800,
  "caretaker_hourly_rate": 560,
  "platform_commission_hourly": 240,
  "commission_percentage": 30
}
```

---

### 6.11 Earnings & Payouts

| Endpoint | Method | Purpose |
|---|---|---|
| `.../admin/earnings` | `GET` | Earnings with tabs: `ready_to_pay`, `hold`, `disputed`, `paid_history` |
| `.../admin/create_payout` | `POST` | Create weekly payout batch |
| `.../admin/update_payout` | `POST` | Mark payout as `paid`, `processing`, or `failed` |
| `.../admin/refresh_payout_eligibility` | `POST` | Move eligible bookings from `hold` to `ready_for_payout` |
| `.../admin/earnings_export` | `GET` | Export earnings data |

**Create Payout Request:**

```json
{
  "caretaker_user_id": 43,
  "week_end": "2026-05-18",
  "payment_method": "bank_transfer",
  "admin_note": "Weekly payout batch"
}
```

---

### 6.12 SOS Detail

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/sos_detail?id={sos_id}` |
| **Purpose** | View SOS alert detail |

---

### 6.13 Admin Set Caretaker Availability

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/admin/set_caretaker_availability` |
| **Purpose** | Admin override caretaker availability with optional lock |

**Request Body:**

```json
{
  "caretaker_user_id": 43,
  "is_available": false,
  "lock": true,
  "note": "Under investigation for complaint #12"
}
```

---

### 6.14 Caretaker Feedback

| Endpoint | Method | Purpose |
|---|---|---|
| `.../admin/caretaker_feedback` | `GET` | List caretaker feedback entries |
| `.../admin/update_feedback_status` | `POST` | Update feedback status (pending/reviewed/archived) |

---

### 6.15 Reports & Audit

| Endpoint | Method | Purpose |
|---|---|---|
| `.../admin/reports_summary` | `GET` | Platform summary reports |
| `.../admin/audit_logs` | `GET` | Admin audit log listing |
| `.../admin/notification_history` | `GET` | Notification history |

---

## 7. Booking APIs

### 7.1 Create Booking (Family)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/booking/create_booking` |
| **Purpose** | Create a new booking for a caretaker |
| **Auth Required** | Yes (family only) |

**Request Body:**

```json
{
  "caretaker_user_id": 43,
  "patient_id": 15,
  "service_type": "elder_care",
  "booking_date": "2026-05-25",
  "start_time": "09:00",
  "end_time": "13:00",
  "address": "123 Main Street, Satellite, Ahmedabad",
  "location_latitude": 23.0225,
  "location_longitude": 72.5714,
  "notes": "Patient needs wheelchair assistance",
  "request_priority": "normal"
}
```

> Booking creation uses `SELECT ... FOR UPDATE` on the caretaker row for race-condition protection. Snapshots pricing from `caretaker_profiles` at booking time.

---

### 7.2 My Bookings

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/booking/my_bookings` |
| **Purpose** | List bookings for the authenticated user |
| **Auth Required** | Yes (family, caretaker, admin) |

**Query Params:** `?page=1&limit=20&status=pending`

---

### 7.3 Caretaker Booking Requests

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/booking/caretaker_requests` |
| **Purpose** | List pending booking requests for caretaker |
| **Auth Required** | Yes (caretaker only) |

**Query Params:** `?page=1&limit=50`

**Success Response (200):**

```json
{
  "success": true,
  "message": "Caretaker booking requests retrieved",
  "data": {
    "requests": [
      {
        "booking_id": 101,
        "request_id": 101,
        "patient_name": "Rajesh Shah",
        "elder_name": "Rajesh Shah",
        "location_short": "Satellite",
        "visit_date": "2026-05-25",
        "start_time": "09:00:00",
        "end_time": "13:00:00",
        "display_time": "9:00 AM - 1:00 PM",
        "service_type": "elder_care",
        "care_type": "daily_care",
        "priority": "normal",
        "is_urgent": false,
        "status": "pending",
        "created_at": "2026-05-20T12:30:00+05:30"
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 50,
      "total": 1,
      "total_pages": 1
    }
  },
  "errors": null
}
```

---

### 7.4 Caretaker Request Detail

| Property | Value |
|---|---|
| **Method** | `GET` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/booking/caretaker_request_detail?booking_id={id}` |
| **Purpose** | Full request detail with patient summary |

---

### 7.5 Respond to Request (Accept/Decline)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/booking/respond_request` |
| **Purpose** | Accept or decline a pending booking request |
| **Auth Required** | Yes (caretaker only) |

**Accept Request:**

```json
{
  "booking_id": 101,
  "action": "accept"
}
```

**Decline Request:**

```json
{
  "booking_id": 101,
  "action": "decline",
  "decline_reason_code": "location_too_far",
  "decline_note": "Patient location is 40km away"
}
```

**Allowed decline reason codes:** `not_available`, `location_too_far`, `not_comfortable_with_care`, `personal_reasons`, `other`

---

### 7.6 Accept Booking (Legacy Wrapper)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/booking/accept_booking` |
| **Purpose** | Legacy wrapper around `respond_request` |

---

### 7.7 Reject Booking (Legacy Wrapper)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/booking/reject_booking` |
| **Purpose** | Legacy wrapper for declining |

---

### 7.8 Cancel Booking (Family)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/booking/cancel_booking` |
| **Purpose** | Cancel owned upcoming booking (pending or accepted) |
| **Auth Required** | Yes (family only) |

**Request Body:**

```json
{
  "booking_id": 101,
  "cancel_reason_code": "schedule_change",
  "cancel_note": "Patient appointment rescheduled"
}
```

**Refund Policy:**
| Time Before Booking | Refund % |
|---|---|
| 24+ hours | 100% |
| 12-24 hours | 50% |
| Under 12 hours | 0% |

Refund is calculated from successful rows in `payments`, not from booking totals. Partial payments refund only the successful amount paid. Payable refunds create one `booking_refunds` row per booking and are manually reviewed by admin. Cancellation responses include `paid_amount`, `refund_eligible`, `refund_percentage`, `refund_amount`, `refund_status`, and `refund_record_created`.

---

### 7.9 Cancel Booking (Caretaker)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/booking/caretaker_cancel_booking` |
| **Purpose** | Caretaker cancels accepted future booking |
| **Auth Required** | Yes (caretaker only) |

> Family gets 100% refund. A replacement ticket is auto-created for admin.

---

### 7.10 Complete Booking

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/booking/complete_booking` |
| **Purpose** | Legacy completion endpoint (accepted → in_progress → completed) |
| **Auth Required** | Yes (caretaker only) |

---

### 7.11 Visit OTP (Family)

| Property | Value |
|---|---|
| **Method** | `POST` |
| **URL** | `https://we-care.eu.cc/wecare/api/v1/booking/visit_otp` |
| **Purpose** | Generate/retrieve visit-start OTP for family user |
| **Auth Required** | Yes (family only) |

**Request Body:**

```json
{
  "booking_id": 101
}
```

> OTP is returned once and stored hashed. Family displays this OTP to the caretaker.

---

## 8. Visit & OTP Flow

### Visit APIs

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `.../visit/verify_start_otp` | `POST` | Caretaker | Verify family-provided visit OTP |
| `.../visit/check_in` | `POST` | Caretaker | Check-in (booking → `in_progress`) |
| `.../visit/check_out` | `POST` | Caretaker | Check-out (booking → `completed`) |
| `.../visit/active_visit` | `GET` | Caretaker | Live care tracking data |
| `.../visit/view_visit` | `GET` | All | View visit details |
| `.../visit/add_note` | `POST` | Caretaker | Add live care note |
| `.../visit/update_task_status` | `POST` | Caretaker | Update checklist task status |
| `.../visit/completed_summary` | `GET` | Caretaker | Completed visit popup data |
| `.../visit/full_report` | `GET` | Caretaker | Full visit report |

### Complete Visit-Start Flow

```
1. Family books caretaker
   └─ Booking status: pending

2. Caretaker accepts request
   └─ Booking status: accepted
   └─ visit_tracking row prepared
   └─ Visit-start OTP generated

3. Family opens booking → taps "Show OTP"
   └─ POST /booking/visit_otp → returns 6-digit OTP
   └─ Family displays OTP on screen

4. Caretaker arrives at patient location
   └─ POST /visit/verify_start_otp → verifies OTP
   └─ {"booking_id": 101, "otp": "123456"}

5. Caretaker checks in
   └─ POST /visit/check_in
   └─ {"booking_id": 101, "latitude": 23.0225, "longitude": 72.5714}
   └─ Booking status: in_progress
   └─ Caretaker auto-marked unavailable (on_visit)

6. During visit (Live Care Tracking):
   └─ GET /visit/active_visit → tasks, notes, patient info
   └─ POST /visit/update_task_status → pending/ongoing/completed
   └─ POST /visit/add_note → immutable care notes

7. Caretaker checks out
   └─ POST /visit/check_out
   └─ Booking status: completed
   └─ Care points earned: 20
   └─ Payout status: hold (24-hour window)
   └─ Caretaker availability auto-restored

8. Post-visit:
   └─ GET /visit/completed_summary → popup data
   └─ GET /visit/full_report → detailed report
```

### Verify Start OTP Request:

```json
{
  "booking_id": 101,
  "otp": "123456"
}
```

### Check-In Request:

```json
{
  "booking_id": 101,
  "latitude": 23.0225,
  "longitude": 72.5714,
  "notes": "Reached patient location"
}
```

### Check-In Response:

```json
{
  "success": true,
  "message": "Check-in successful",
  "data": {
    "booking_id": 101,
    "visit_id": 78,
    "status": "in_progress",
    "check_in_time": "2026-05-25T09:15:00+05:30",
    "booking_status": "in_progress",
    "availability_status": "unavailable",
    "availability_reason": "on_visit"
  },
  "errors": null
}
```

### Check-Out Response:

```json
{
  "success": true,
  "message": "Check-out successful",
  "data": {
    "booking_id": 101,
    "visit_id": 78,
    "status": "completed",
    "check_out_time": "2026-05-25T13:00:00+05:30",
    "duration_minutes": 225,
    "care_points_earned": 20,
    "booking_status": "completed",
    "payout_status": "hold"
  },
  "errors": null
}
```

---

## 9. Booking Status Lifecycle

### Status Values

| Status | Description |
|---|---|
| `pending` | Booking created, awaiting caretaker response |
| `accepted` | Caretaker accepted the booking |
| `in_progress` | Caretaker checked in, visit is active |
| `completed` | Caretaker checked out, visit finished |
| `declined` | Caretaker declined the booking request |
| `cancelled` | Booking cancelled (by family, caretaker, or admin) |

### State Transitions

```
pending ──────→ accepted ──────→ in_progress ──────→ completed
   │               │                                      
   │               └──→ cancelled (family/caretaker/admin) 
   │                                                       
   ├──→ declined (caretaker)                               
   │                                                       
   └──→ cancelled (family/admin)                           
```

### Payment Status Values

| Status | Description |
|---|---|
| `pending` | No payment received yet |
| `paid` | Full payment completed |
| `failed` | Payment attempt failed |
| `refunded` | Payment has been refunded |

### Payout Status Values

| Status | Description |
|---|---|
| `not_applicable` | Non-completed bookings |
| `hold` | Completed, under 24-hour review window |
| `ready_for_payout` | Cleared review, ready for admin payout |
| `disputed` | Complaint/SOS blocks payout |
| `paid` | Payout completed to caretaker |

---

## 10. Payment & Earnings Flow

### Payment APIs

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `.../payment/pay_advance` | `POST` | Family | Pay 50% advance |
| `.../payment/pay_remaining` | `POST` | Family | Pay remaining amount |
| `.../payment/payment_history` | `GET` | Family | Payment transaction history |
| `.../payment/payment_summary` | `GET` | Family | Payment summary for a booking |
| `.../payment/my_refunds` | `GET` | Family | List own refund requests |
| `.../payment/refund_detail?id=1` | `GET` | Family | View owned refund detail |

### Pay Advance Request:

```json
{
  "booking_id": 101,
  "payment_method": "upi",
  "transaction_id": "TXN_123456",
  "idempotency_key": "pay_adv_101_1716600000"
}
```

> Advance is calculated server-side as 50% of `total_customer_amount`.

### Pay Remaining Request:

```json
{
  "booking_id": 101,
  "payment_method": "card",
  "transaction_id": "TXN_789012",
  "idempotency_key": "pay_rem_101_1716600001"
}
```

### Allowed Payment Methods

`card` · `upi` · `netbanking` · `wallet` · `cash` · `insurance` · `other`

### Manual Refund APIs

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `.../admin/refunds` | `GET` | Admin | List refunds with filters, pagination, and summary totals |
| `.../admin/refund_detail?id=1` | `GET` | Admin | View full refund detail |
| `.../admin/approve_refund` | `POST` | Admin | Approve a pending refund |
| `.../admin/reject_refund` | `POST` | Admin | Reject a pending refund |
| `.../admin/mark_refund_processed` | `POST` | Admin | Mark approved refund as manually processed |

Refund status values: `pending`, `approved`, `rejected`, `processed`, `failed`.

Approve request:

```json
{
  "refund_id": 1,
  "admin_note": "Approved as per cancellation policy"
}
```

Process request:

```json
{
  "refund_id": 1,
  "refund_method": "upi",
  "refund_transaction_id": "manual_ref_123",
  "admin_note": "Refund sent manually"
}
```

### Complete Payment & Payout Lifecycle

```
1. ADVANCE PAYMENT
   └─ Family pays 50% of total_customer_amount
   └─ booking.paid_amount updated
   └─ booking.remaining_amount calculated

2. REMAINING PAYMENT
   └─ Family pays remaining amount
   └─ Allowed after: confirmed, caretaker_arrived, in_progress, completed
   └─ booking.payment_status → paid

3. VISIT COMPLETION
   └─ booking.payout_status → hold
   └─ booking.payout_hold_until = completed_at + 24 hours

4. PAYOUT ELIGIBILITY (Admin)
   └─ POST /admin/refresh_payout_eligibility
   └─ Checks: 24h passed, no complaints, no SOS, no pending tasks, no refunds
   └─ booking.payout_status → ready_for_payout

5. PAYOUT CREATION (Admin)
   └─ POST /admin/create_payout
   └─ Weekly batch for eligible bookings
   └─ Pays caretaker_earning_amount (NOT total_customer_amount)

6. PAYOUT SETTLEMENT (Admin)
   └─ POST /admin/update_payout
   └─ payout.status → paid
   └─ booking.payout_status → paid
   └─ booking.payout_paid_at set

DISPUTED PAYOUTS:
   └─ Active complaint → booking.payout_status = disputed
   └─ Blocked from payout until resolved
```

### Pricing Snapshot Architecture

When a booking is created, the following are snapshot from `caretaker_profiles`:

| Booking Field | Source |
|---|---|
| `pricing_tier` | caretaker_profiles.pricing_tier |
| `customer_hourly_rate` | caretaker_profiles.customer_hourly_rate |
| `caretaker_hourly_rate` | caretaker_profiles.caretaker_hourly_rate |
| `platform_commission_hourly` | caretaker_profiles.platform_commission_hourly |
| `total_customer_amount` | customer_hourly_rate × total_hours |
| `caretaker_earning_amount` | caretaker_hourly_rate × total_hours |
| `platform_commission_amount` | commission_hourly × total_hours |
| `total_hours` | Calculated from start_time / end_time |

### Data Visibility Rules

| Data | Family Sees | Caretaker Sees | Admin Sees |
|---|---|---|---|
| `total_customer_amount` | ✅ | ❌ | ✅ |
| `customer_hourly_rate` | ✅ | ❌ | ✅ |
| `caretaker_earning_amount` | ❌ | ✅ | ✅ |
| `caretaker_hourly_rate` | ❌ | ✅ | ✅ |
| `platform_commission_amount` | ❌ | ❌ | ✅ |
| `commission_percentage` | ❌ | ❌ | ✅ |

---

## 11. Notification APIs

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `.../notification/my_notifications` | `GET` | All | List user notifications |
| `.../notification/mark_read` | `POST` | All | Mark one notification read |
| `.../notification/mark_all_read` | `POST` | All | Mark all notifications read |
| `.../notification/create_notification` | `POST` | Admin | Create manual notification |
| `.../notification/register_device` | `POST` | All | Register FCM device token |
| `.../notification/remove_device` | `POST` | All | Remove device token |

### List Notifications

**URL:** `GET .../notification/my_notifications?page=1&limit=20&unread_only=false&type=`

**Response:**

```json
{
  "success": true,
  "message": "Notifications retrieved",
  "data": {
    "items": [
      {
        "id": 1,
        "title": "Booking Accepted",
        "message": "Your booking #101 has been accepted",
        "type": "booking_accepted",
        "related_type": "booking",
        "related_id": 101,
        "is_read": false,
        "created_at": "2026-05-20T12:30:00+05:30"
      }
    ],
    "unread_count": 5,
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 12,
      "total_pages": 1
    }
  },
  "errors": null
}
```

### Automatic Notification Triggers

| Event | Type | Recipient |
|---|---|---|
| Family creates booking | `booking_created` | Assigned caretaker |
| Caretaker accepts | `booking_accepted` | Family |
| Caretaker declines | `booking_declined` | Family |
| Visit OTP generated | `otp_generated` | Family |
| Caretaker checks in | `visit_started` | Family |
| Caretaker checks out | `visit_completed` | Family |
| SOS created | `sos_created` | Family + Admin |
| Caretaker approved | `caretaker_approved` | Caretaker |
| Caretaker rejected | `caretaker_rejected` | Caretaker |
| Payout processed | `payout_processed` | Caretaker |
| Complaint updated | `complaint_updated` | Family |
| Replacement updated | `replacement_updated` | Family |

### Register Device Token

```json
{
  "device_token": "fcm_token_string",
  "platform": "android",
  "app_type": "family"
}
```

> `platform`: `android`, `ios`, `web`  
> `app_type`: `family`, `caretaker`, `admin`

---

## 12. Complaint APIs

### Family Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `.../complaint/create_complaint` | `POST` | File a complaint against a booking |
| `.../complaint/my_complaints` | `GET` | List user's complaints |

**Create Complaint (multipart/form-data):**

| Field | Type | Required |
|---|---|---|
| `booking_id` | integer | Yes |
| `subject` | string | Yes |
| `description` | string | Yes |
| `proof_file` | file | No |

### Admin Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `.../complaint/admin_list` | `GET` | List all complaints |
| `.../complaint/admin_view?id={id}` | `GET` | View complaint detail |
| `.../complaint/admin_update_status` | `POST` | Update complaint status |
| `.../complaint/view_proof?id={id}` | `GET` | Stream complaint proof inline |

`GET .../complaint/view_proof?id={id}` is admin-only and returns a file/blob stream on success, not JSON. It is used by the Admin Web in-app document viewer. Supported proof types: `jpg`, `jpeg`, `png`, `webp`, `pdf`. Success headers include `Content-Type`, `Content-Disposition: inline`, `X-Content-Type-Options: nosniff`, and `Cache-Control: private, max-age=300`. JSON errors use the standard envelope. Complaint admin list/view payloads include proof compatibility fields such as `proof_file`, `proof_file_url`, `proof_url`, and `has_proof`.

**Update Status:**

```json
{
  "complaint_id": 5,
  "status": "resolved",
  "admin_note": "Investigated and resolved"
}
```

**Complaint Statuses:** `open` · `in_review` · `resolved` · `rejected`

---

## 13. SOS Alert APIs

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `.../sos/create_sos` | `POST` | All | Create emergency SOS alert |
| `.../sos/create` | `POST` | All | Alternative SOS creation |
| `.../sos/my_sos` | `GET` | All | List user's SOS alerts |
| `.../sos/admin_sos_list` | `GET` | Admin | List all SOS alerts |
| `.../sos/resolve_sos` | `POST` | Admin | Resolve an SOS alert |
| `.../sos/update_status` | `POST` | Admin | Update SOS status |

### Create SOS Alert

```json
{
  "booking_id": 101,
  "message": "Patient has fallen, needs immediate assistance",
  "latitude": "23.0225",
  "longitude": "72.5714"
}
```

**SOS Statuses:** `open` · `resolved`

Admin SOS list accepts `status=all`, `status=open`, and `status=resolved`. Omitted or empty status is treated as `all`; dashboard widgets that need only active alerts should pass `status=open`. The admin list response keeps legacy `username`, `email`, and `role` fields and adds display aliases: `sos_id`, `alert_id`, `reporter_user_id`, `reporter_name`, `reporter_username`, `user_name`, `reporter_email`, `reporter_role`, `reporter_phone`, `booking_id`, `formatted_booking_id`, `patient_name`, `family_name`, `caretaker_user_id`, `caretaker_name`, `caregiver_name`, `caretaker_phone`, `caregiver_phone`, `caretaker_email`, `location_text`, `triggered_at`, `resolved_at`, and `resolved_by_name`. If `sos_alerts.booking_id` is null and the reporter is a caretaker with an active `in_progress` booking, admin SOS responses derive the booking context from existing booking ownership.

Admin active visits use `GET /admin/bookings?status=in_progress` and now include display-ready fields for the Active Visits page: `booking_id`, `formatted_booking_id`, `booking_code`, `patient_name`, `family_name`, `family_phone`, `caretaker_user_id`, `caretaker_name`, `caregiver_name`, `caretaker_phone`, `caregiver_phone`, `caretaker_email`, `city`, `address`, `booking_status`, `visit_status`, `visit_id`, `checked_in_at`, `checked_out_at`, `duration_hours`, `active_sos_count`, `latest_sos_status`, `has_sos`, and `sos_count`.

---

## 14. Replacement Ticket APIs

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `.../replacement/create_ticket` | `POST` | Caretaker | Request replacement / substitute handling for an assigned booking |
| `.../replacement/admin_list` | `GET` | Admin | List all tickets |
| `.../replacement/admin_view?id={id}` | `GET` | Admin | View ticket detail |
| `.../replacement/admin_update_status` | `POST` | Admin | Update ticket status |
| `.../replacement/admin_assign` | `POST` | Admin | Assign replacement caretaker |
| `.../replacement/admin_cancel` | `POST` | Admin | Cancel open/assigned replacement ticket |
| `.../replacement/admin_resolve` | `POST` | Admin | Resolve assigned replacement ticket |
| `.../replacement/admin_delete` | `POST`/`DELETE` | Admin | Delete ticket |

Compatibility aliases are also present under `.../replacement_tickets/` for `admin_list`, `admin_view`, `admin_assign`, `admin_cancel`, `admin_resolve`, and `admin_update_status`. They require the same admin bearer token and include the same response shape.

### Create Ticket

Auth: Yes  
Role: caretaker  
Used By: Caretaker App  
Middleware: `caretaker_only`  
Source: `api/v1/replacement/create_ticket`

```json
{
  "booking_id": "required",
  "complaint_id": "optional",
  "reason": "required"
}
```

Protected by bearer JWT through `caretaker_only`. Caretaker ownership must match the authenticated user through `bookings.caretaker_user_id`.

### Admin Assignment Flow

`GET .../replacement/admin_list` returns `data.items` as the canonical array and also returns `data.tickets` and `data.replacements` as compatibility aliases of the same array.

```json
{
  "success": true,
  "message": "Replacement tickets retrieved",
  "data": {
    "items": [
      {
        "id": 1,
        "booking_id": 29,
        "booking_reference": "#29",
        "original_caretaker_user_id": 12,
        "original_caretaker_name": "Caregiver Name",
        "replacement_caretaker_user_id": null,
        "family_user_id": 31,
        "family_name": "Family Name",
        "patient_name": "Patient Name",
        "requested_by_user_id": 12,
        "requested_by_name": "Caregiver Name",
        "complaint_id": null,
        "reason": "not available",
        "status": "open",
        "admin_note": null,
        "created_at": "2026-05-25 14:17:19",
        "updated_at": "2026-05-25 14:17:19"
      }
    ],
    "tickets": [
      {
        "id": 1,
        "booking_id": 29,
        "status": "open"
      }
    ],
    "replacements": [
      {
        "id": 1,
        "booking_id": 29,
        "status": "open"
      }
    ],
    "page": 1,
    "limit": 20,
    "total": 1,
    "total_pages": 1
  }
}
```

`GET .../replacement/admin_view?id={id}` returns the ticket plus booking status/date/time/service, family contact, patient details, linked complaint details, and `available_replacement_caretakers` when status is `open`.

Assign:

```json
{
  "ticket_id": 1,
  "replacement_caretaker_user_id": 123,
  "admin_note": "Assigned replacement caretaker"
}
```

Cancel:

```json
{
  "ticket_id": 1,
  "admin_note": "Cancelled by admin"
}
```

Resolve:

```json
{
  "ticket_id": 1,
  "admin_note": "Replacement resolved"
}
```

Migration present: `database/migrations/2026_05_25_replacement_ticket_admin_flow_columns.sql` adds/checks `requested_by_user_id`, `original_caretaker_user_id`, `replacement_caretaker_user_id`, `admin_note`, and `updated_at`.

**Ticket Statuses:** `open` · `assigned` · `resolved` · `cancelled`

---

## 15. Review APIs

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `.../review/add_review` | `POST` | Family | Review a completed booking |
| `.../review/caretaker_reviews` | `GET` | All | List reviews for a caretaker |

### Add Review

```json
{
  "booking_id": 101,
  "rating": 5,
  "comment": "Excellent care, very professional"
}
```

### Get Caretaker Reviews

**URL:** `GET .../review/caretaker_reviews?caretaker_user_id={id}`

---

## 16. Checklist APIs

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `.../checklist/create_task` | `POST` | Family | Create checklist task for a booking |
| `.../checklist/booking_tasks` | `GET` | Family/Caretaker/Admin | List tasks for a booking |
| `.../checklist/mark_done` | `POST` | Caretaker | Mark a task as completed |

### Create Task

```json
{
  "booking_id": 101,
  "title": "Give medication at 10 AM",
  "description": "Metformin 500mg after breakfast"
}
```

### Mark Done

```json
{
  "task_id": 5
}
```

**Task Statuses:** `pending` · `ongoing` · `completed`

---

## 17. Dashboard APIs

| Endpoint | Method | Role | Purpose |
|---|---|---|---|
| `.../dashboard/family_dashboard` | `GET` | Family | Family home dashboard |
| `.../dashboard/caretaker_dashboard` | `GET` | Caretaker | Caretaker home dashboard |
| `.../dashboard/admin_dashboard` | `GET` | Admin | Admin overview dashboard |

### Caretaker Dashboard Response (example):

```json
{
  "success": true,
  "message": "Dashboard loaded",
  "data": {
    "today_visits": 2,
    "new_requests": 3,
    "active_visit": {
      "booking_id": 101,
      "patient_name": "Rajesh Shah",
      "status": "in_progress"
    },
    "upcoming_visits": [],
    "total_earnings": 25000,
    "pending_earnings": 5000,
    "availability_reason": "manual_on",
    "has_active_visit": false,
    "availability_locked_by_admin": false
  },
  "errors": null
}
```

---

## 18. Database Important Tables

| Table | Purpose | Key Columns |
|---|---|---|
| `users` | All user accounts | `id`, `email`, `username`, `phone_number`, `role`, `is_verified`, `is_active` |
| `tokens` | JWT session storage | `user_id`, `access_token`, `refresh_token`, `is_blacklisted`, `expires_at` |
| `family_profiles` | Family user profiles | `user_id`, `full_name`, `address`, `emergency_contact_*` |
| `caretaker_profiles` | Caretaker details + pricing | `user_id`, `verification_status`, `is_available`, `pricing_tier`, `customer_hourly_rate`, `caretaker_hourly_rate`, `rating` |
| `patient_details` | Elder/patient records | `family_user_id`, `patient_name`, `age`, `gender`, `medical_condition`, `care_type` |
| `bookings` | All bookings with pricing snapshot | `family_user_id`, `caretaker_user_id`, `patient_id`, `status`, `total_customer_amount`, `caretaker_earning_amount`, `payout_status` |
| `payments` | Payment transactions | `booking_id`, `amount`, `payment_method`, `payment_type`, `status`, `idempotency_key` |
| `booking_refunds` | Manual refund requests for cancelled paid bookings | `booking_id`, `paid_amount`, `refund_amount`, `refund_percentage`, `status`, `processed_at` |
| `visit_tracking` | Visit check-in/out records | `booking_id`, `check_in_time`, `check_out_time`, `check_in_lat/lng`, `check_out_lat/lng` |
| `visit_notes` | Immutable live care notes | `booking_id`, `visit_id`, `note` |
| `visit_activity_logs` | Visit timeline events | `booking_id`, `activity_type`, `message` |
| `booking_checklist_tasks` | Care checklist items | `booking_id`, `title`, `status` (pending/ongoing/completed) |
| `reviews` | Post-visit reviews | `booking_id`, `rating`, `comment` |
| `complaints` | Family complaints | `booking_id`, `subject`, `status` (open/in_review/resolved/rejected) |
| `sos_alerts` | Emergency alerts | `user_id`, `booking_id`, `message`, `latitude`, `longitude`, `status` |
| `replacement_tickets` | Caretaker replacement requests | `booking_id`, `reason`, `status` (open/assigned/resolved/cancelled) |
| `caretaker_payouts` | Weekly payout batches | `caretaker_user_id`, `amount`, `status` (pending/processing/paid/failed) |
| `caretaker_payout_items` | Individual payout line items | `payout_id`, `booking_id`, `amount` |
| `pricing_tiers` | Admin-managed pricing tiers | `name`, `slug`, `customer_hourly_rate`, `caretaker_hourly_rate`, `commission_percentage` |
| `notifications` | In-app notifications | `user_id`, `title`, `type`, `related_type`, `related_id`, `is_read` |
| `notification_device_tokens` | FCM push tokens | `user_id`, `device_token`, `platform`, `app_type` |
| `otp_codes` | Hashed OTP storage | `user_id`, `purpose`, `otp_hash`, `expires_at`, `attempts` |
| `otp_verifications` | Forgot-password OTPs | `user_id`, `login_identifier`, `otp_hash`, `verified_at` |
| `password_reset_tokens` | Single-use reset tokens | `user_id`, `token_hash`, `expires_at`, `used_at` |
| `pending_users` | Pre-verification registrations | `username`, `email`, `password_hash`, `role`, `expires_at` |
| `documents` | Caretaker verification docs | `user_id`, `document_type`, `file_path`, `status` |
| `caretaker_feedback` | Platform feedback from caretakers | `caretaker_user_id`, `rating`, `feedback`, `status` |
| `admin_audit_logs` | Audit trail | `admin_user_id`, `action`, `entity_type`, `entity_id`, `old_values`, `new_values` |
| `rate_limits` | Rate limiting state | `rate_key`, `action`, `attempts`, `blocked_until` |
| `support_tickets` | Support ticket system | `user_id`, `subject`, `message`, `status` |

---

## 19. Authentication Usage

### Request Header Format

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Token Payload Structure

**Access Token:**

```json
{
  "user_id": 42,
  "role": "family",
  "type": "access",
  "iat": 1716600000,
  "exp": 1716603600
}
```

**Refresh Token:**

```json
{
  "user_id": 42,
  "role": "caretaker",
  "type": "refresh",
  "iat": 1716600000,
  "exp": 1717204800
}
```

### Token Lifetimes

| Token | Validity |
|---|---|
| Access Token | 1 hour (3600s) |
| Refresh Token | 7 days (604800s) |

### Example Authenticated Request (cURL)

```bash
curl -X GET \
  "https://we-care.eu.cc/wecare/api/v1/auth/profile" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Example POST with JSON Body (cURL)

```bash
curl -X POST \
  "https://we-care.eu.cc/wecare/api/v1/booking/create_booking" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "caretaker_user_id": 43,
    "patient_id": 15,
    "service_type": "elder_care",
    "booking_date": "2026-05-25",
    "start_time": "09:00",
    "end_time": "13:00",
    "address": "123 Main Street, Ahmedabad"
  }'
```

---

## 20. Error Handling

### Standard Error Codes

| HTTP Code | Meaning | Example |
|---|---|---|
| `400` | Bad Request / Validation Error | Missing required fields, invalid format |
| `401` | Unauthorized | Missing/expired/invalid JWT token |
| `403` | Forbidden | Role mismatch, ownership violation, admin-locked |
| `404` | Not Found | Resource does not exist |
| `405` | Method Not Allowed | Wrong HTTP method (e.g., GET on POST-only endpoint) |
| `409` | Conflict | Duplicate payment, already accepted, status transition conflict |
| `429` | Too Many Requests | Rate limited (login, OTP, SOS) |
| `500` | Server Error | Internal error (no raw exception text in response) |

### Validation Error Example

```json
{
  "success": false,
  "message": "Validation failed",
  "data": null,
  "errors": {
    "email": ["Email is required", "Invalid email format"],
    "password": ["Password must be at least 8 characters"],
    "booking_id": ["Booking id must be an integer"]
  }
}
```

### Auth Error Example

```json
{
  "success": false,
  "message": "Authentication required",
  "data": null,
  "errors": null
}
```

### Conflict Error Example (409)

```json
{
  "success": false,
  "message": "Booking has already been accepted",
  "data": null,
  "errors": {
    "status": ["Booking is no longer in pending state"]
  }
}
```

### Rate Limit Error Example (429)

```json
{
  "success": false,
  "message": "Too many attempts. Please try again later.",
  "data": null,
  "errors": null
}
```

---

## 21. Live API Testing Notes

### Postman Setup

1. **Base URL Variable:** Set `{{base_url}}` = `https://we-care.eu.cc/wecare/api/v1`
2. **Auth Flow:**
   - Call `POST {{base_url}}/auth/login` with credentials
   - Copy `data.access` from response
   - Set `Authorization` header: `Bearer <access_token>`
3. **Environment Variables (recommended):**
   - `base_url` = `https://we-care.eu.cc/wecare/api/v1`
   - `access_token` = (auto-set from login response)
   - `refresh_token` = (auto-set from login response)

### Required Headers

| Header | Value | Required For |
|---|---|---|
| `Authorization` | `Bearer <token>` | All protected endpoints |
| `Content-Type` | `application/json` | All non-file POST/PATCH/DELETE |
| `Content-Type` | `multipart/form-data` | File upload endpoints |

### Content-Type Notes

- Non-file endpoints accept: `application/json` (recommended), `application/x-www-form-urlencoded`, `multipart/form-data`
- File upload endpoints **require**: `multipart/form-data`
- Invalid JSON returns `400` with structured error

### File Upload Endpoints

| Endpoint | File Field | Notes |
|---|---|---|
| `auth/profile` | `profile_picture` | Profile image upload |
| `caretaker/upload_document` | `document` | Verification documents |
| `complaint/create_complaint` | `proof_file` | Complaint evidence |

### Image Upload Notes

- Files are saved with randomized filenames
- MIME type and file size are validated
- Upload directory has FastAPI static file security protection
- Returned path format: `uploads/profiles/<random>.jpg`

### JWT Notes

- JWT uses HS256 algorithm
- `JWT_SECRET` must be set in environment (no hardcoded fallback)
- Access tokens include `type: "access"` — refresh tokens include `type: "refresh"`
- Token type enforcement is checked on protected endpoints
- Blacklisted tokens are rejected

---

## 22. Current Prototype Limitations

### System Scope

> ⚠️ This is a **prototype/academic project** backend. The following limitations apply:

| Area | Limitation |
|---|---|
| **Payment Gateway** | Mock/simulated payments only. No real Razorpay/Stripe integration. `verification_status` is set to `verified` for non-cash and `not_required` for cash locally. |
| **Push Notifications** | FCM device token storage is implemented but push delivery is a **no-op**. Only database notifications are active. |
| **Realtime Features** | No WebSocket/SSE support. Clients must poll for updates. |
| **Email Delivery** | Requires SMTP environment variables. OTP emails may not send without configured mail server. |
| **CSRF Protection** | Not present for browser/admin panel usage. |
| **Rate Limiting** | Basic rate limiting exists for login, OTP, SOS, and password reset. Not comprehensive. |
| **File Storage** | Local filesystem only. No CDN or cloud storage integration. |
| **Scaling** | Single-server architecture. No load balancing, caching layer, or queue system. |
| **Audit Logging** | Present but no UI for complex analytics queries. |
| **Role Management** | Fixed three-role system. No dynamic permissions or RBAC. |
| **Report Export** | Limited. `earnings_export` available but no comprehensive report generation. |
| **Refund Processing** | Calculated and stored but no automated refund execution. |

### Settings / Admin Profile

- `GET /api/v1/health` is implemented as a public settings/API connection test endpoint.
- `GET /api/v1/admin/me` fetches the authenticated admin profile for the Settings page.
- `POST /api/v1/admin/update_profile` updates only the authenticated admin's name/email/phone. Submitted `id`, `user_id`, `role`, and password fields are ignored.

### Health Check

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `.../health` | `GET` | No | Public API reachability check for Admin Web settings |
| `.../admin/me` | `GET` | Yes, admin | Fetch current admin profile |
| `.../admin/update_profile` | `POST` | Yes, admin | Update current admin profile |

```json
{
  "success": true,
  "message": "API is reachable",
  "data": {
    "app": "WeCare API",
    "environment": "local",
    "time": "2026-05-25 16:00:00",
    "version": "Demo Prototype",
    "api_base_path": "/api/v1"
  },
  "errors": null
}
```
- Admin profile responses return only `id`, `name`, `username`, `email`, `phone_number`, `role`, `created_at`, and `updated_at`.
- Admin profile update accepts JSON, form-data, and x-www-form-urlencoded. Validation errors use HTTP 422, including `Email is already in use`.
- Password hashes, reset tokens, OTP values, JWT secrets, and role changes are never exposed or accepted by these settings endpoints.
- Comprehensive report export APIs deferred
- Role/permission management not present
- Payment refund/reconciliation workflows not automated

---

## 23. API Summary Table

| Module | Endpoint Count | Status |
|---|---|---|
| **Auth** | 19 | ✅ Live |
| **Root / Health** | 1 | Live |
| **Patient** | 5 | Live |
| **Caretaker** | 17 | Live |
| **Admin** | 37 | Live |
| **Booking** | 11 | Live |
| **Visit** | 9 | Live |
| **Payment** | 6 | Live |
| **Notification** | 6 | Live |
| **Complaint** | 6 | Live |
| **SOS** | 6 | Live |
| **Replacement** | 8 | Live |
| **Replacement Ticket Aliases** | 6 | Live |
| **Review** | 2 | Live |
| **Checklist** | 3 | Live |
| **Dashboard** | 3 | Live |
| **System** | 1 | Live |
| **TOTAL** | **146** | All Live |

### Role Access Summary

| Module | Public | Family | Caretaker | Admin |
|---|---|---|---|---|
| Auth (register, login, OTP) | ✅ | — | — | — |
| Auth (profile, password) | — | ✅ | ✅ | ✅ |
| Patient CRUD | — | ✅ | — | — |
| Caretaker Listing | — | ✅ | ✅ | ✅ |
| Caretaker Profile/Availability | — | — | ✅ | — |
| Caretaker Earnings | — | — | ✅ | — |
| Booking Create/Cancel | — | ✅ | — | — |
| Booking Requests | — | — | ✅ | — |
| Visit OTP | — | ✅ | — | — |
| Visit Check-in/out | — | — | ✅ | — |
| Payment | — | ✅ | — | — |
| Reviews | — | ✅ | — | — |
| Complaints | — | ✅ | — | ✅ |
| SOS | — | ✅ | ✅ | ✅ |
| Replacement | — | ✅ | — | ✅ |
| Notifications | — | ✅ | ✅ | ✅ |
| Checklist | — | ✅ | ✅ | ✅ |
| Dashboard | — | ✅ | ✅ | ✅ |
| User Management | — | — | — | ✅ |
| Pricing Tiers | — | — | — | ✅ |
| Earnings/Payouts | — | — | — | ✅ |
| Audit Logs | — | — | — | ✅ |

---

> **Document Version:** 1.0  
> **Last Updated:** 2026-05-25  
> **Live Base URL:** `https://we-care.eu.cc/wecare/api/v1`  
> **Total Endpoints:** 146  
> **Backend:** FastAPI 8.x + MySQL + JWT Auth
