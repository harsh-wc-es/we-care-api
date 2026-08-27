"""
Tests for WeCare SMTP Email Service (app.services.email_service).

Verifies:
1. SMTP connection, STARTTLS, authentication, message dispatch, and context cleanup.
2. SMTP authentication error handling (no credential leakage).
3. SMTP connection error handling.
4. OTP email content (recipient, subject, OTP code in text/HTML body, expiry info).
5. Registration OTP integration with mocked SMTP.
6. Password reset OTP integration with mocked SMTP.
7. Resend OTP integration with rate-limiting / cooldown preservation.
"""

import smtplib
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.services.email_service import (
    build_otp_email_template,
    is_smtp_configured,
    send_email,
    send_otp_email,
)
from tests.conftest import make_auth_headers


def test_build_otp_email_template():
    """Verify template generation contains required fields, OTP code, and no sensitive leakage."""
    otp = "654321"
    tpl = build_otp_email_template(otp=otp, purpose="Email Verification", expiry_minutes=10)

    assert "subject" in tpl
    assert "text" in tpl
    assert "html" in tpl

    assert "WeCare - Email Verification Code" in tpl["subject"]
    assert otp in tpl["text"]
    assert "10 minutes" in tpl["text"]
    assert "never ask for your OTP" in tpl["text"]

    assert otp in tpl["html"]
    assert "10 minutes" in tpl["html"]


@patch("smtplib.SMTP")
def test_send_email_success(mock_smtp_class):
    """Test 1: Verify successful email delivery with EHLO, STARTTLS, login, and send."""
    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    with patch("app.services.email_service.is_smtp_configured", return_value=True):
        with patch.object(get_settings(), "SMTP_HOST", "smtp.gmail.com"), \
             patch.object(get_settings(), "SMTP_PORT", 587), \
             patch.object(get_settings(), "SMTP_USERNAME", "test@wecare.com"), \
             patch.object(get_settings(), "SMTP_PASSWORD", "secret_app_password"), \
             patch.object(get_settings(), "SMTP_FROM_EMAIL", "noreply@wecare.com"), \
             patch.object(get_settings(), "SMTP_FROM_NAME", "WeCare"):

            result = send_email(
                to_email="recipient@example.com",
                subject="Test Subject",
                body_text="Test Body Plain",
                body_html="<p>Test Body HTML</p>",
            )

            assert result is True
            mock_smtp_class.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
            assert mock_server.ehlo.call_count == 2
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("test@wecare.com", "secret_app_password")
            mock_server.send_message.assert_called_once()

            # Inspect sent email message
            sent_msg = mock_server.send_message.call_args[0][0]
            assert sent_msg["To"] == "recipient@example.com"
            assert sent_msg["Subject"] == "Test Subject"
            assert "WeCare <noreply@wecare.com>" in sent_msg["From"]


@patch("smtplib.SMTP")
def test_send_email_authentication_error(mock_smtp_class):
    """Test 2: Verify SMTPAuthenticationError is handled safely without raising exception."""
    mock_server = MagicMock()
    mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    with patch("app.services.email_service.is_smtp_configured", return_value=True):
        result = send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            body_text="Body",
        )
        assert result is False


@patch("smtplib.SMTP")
def test_send_email_connect_error(mock_smtp_class):
    """Test 3: Verify SMTPConnectError is handled safely."""
    mock_smtp_class.side_effect = smtplib.SMTPConnectError(421, b"Cannot connect to SMTP server")

    with patch("app.services.email_service.is_smtp_configured", return_value=True):
        result = send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            body_text="Body",
        )
        assert result is False


def test_send_email_unconfigured_returns_false():
    """Verify that if SMTP settings are missing, send_email returns False without crashing."""
    with patch("app.services.email_service.is_smtp_configured", return_value=False):
        result = send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            body_text="Body",
        )
        assert result is False


@patch("app.services.email_service.send_email")
def test_send_otp_email_helper(mock_send_email):
    """Test 4: Verify send_otp_email helper builds template and calls send_email."""
    mock_send_email.return_value = True

    result = send_otp_email(
        to_email="user@example.com",
        otp="987654",
        purpose="Registration Verification",
        expiry_minutes=10,
    )

    assert result is True
    mock_send_email.assert_called_once()
    args, kwargs = mock_send_email.call_args
    assert kwargs["to_email"] == "user@example.com"
    assert "Registration Verification" in kwargs["subject"]
    assert "987654" in kwargs["body_text"]
    assert "987654" in kwargs["body_html"]


@patch("app.services.registration_service.send_otp_email")
def test_registration_otp_email_integration(mock_send_otp, client, db):
    """Test 5: Registration flow triggers send_otp_email and marks email_otp_sent."""
    import time
    ts = int(time.time() * 1000) % 10000000
    email = f"reg_smtp_{ts}@example.com"
    username = f"user_smtp_{ts}"
    mock_send_otp.return_value = True

    try:
        res = client.post("/api/v1/auth/register", json={
            "full_name": "SMTP Test User",
            "username": username,
            "email": email,
            "phone_number": f"9{ts:09d}"[:10],
            "password": "Password123!",
            "password_confirm": "Password123!",
            "role": "family",
        })

        assert res.status_code == 201
        data = res.json()["data"]
        assert data["email"] == email
        assert data["email_otp_required"] is True
        assert data["email_otp_sent"] is True
        mock_send_otp.assert_called_once()
        assert mock_send_otp.call_args[1]["to_email"] == email

    finally:
        # Cleanup
        db.execute(text("DELETE FROM otp_codes WHERE email = :email"), {"email": email})
        db.execute(text("DELETE FROM pending_users WHERE email = :email"), {"email": email})
        db.commit()


@patch("app.api.v1.auth.password.send_otp_email")
def test_authenticated_password_reset_otp_email_integration(mock_send_otp, client, test_user, db):
    """Test 6: Authenticated password reset request triggers send_otp_email."""
    mock_send_otp.return_value = True
    headers = make_auth_headers(test_user, db=db)

    res = client.post(
        "/api/v1/auth/request-password-reset-otp",
        headers=headers,
    )

    assert res.status_code == 200
    mock_send_otp.assert_called_once()
    assert mock_send_otp.call_args[1]["to_email"] == test_user["email"]


@patch("app.services.password_service.send_otp_email")
def test_forgot_password_3step_otp_email_integration(mock_send_otp, client, test_user, db):
    """Test 6b: 3-step forgot password request triggers send_otp_email."""
    mock_send_otp.return_value = True

    res = client.post(
        "/api/v1/auth/forgot-password/request-otp",
        json={"login": test_user["email"]},
    )

    assert res.status_code == 200
    mock_send_otp.assert_called_once()
    assert mock_send_otp.call_args[1]["to_email"] == test_user["email"]


@patch("app.services.registration_service.send_otp_email")
def test_resend_registration_otp_integration(mock_send_otp, client, db):
    """Test 7: Resend registration OTP triggers email and preserves cooldown."""
    import time
    ts = int(time.time() * 1000) % 10000000
    email = f"resend_smtp_{ts}@example.com"
    username = f"resend_user_{ts}"
    mock_send_otp.return_value = True

    try:
        # 1. Register first
        reg_res = client.post("/api/v1/auth/register", json={
            "full_name": "Resend Test User",
            "username": username,
            "email": email,
            "phone_number": f"9{ts:09d}"[:10],
            "password": "Password123!",
            "password_confirm": "Password123!",
            "role": "family",
        })
        assert reg_res.status_code == 201

        # 2. Immediate resend should be blocked by cooldown (429)
        resend_res1 = client.post("/api/v1/auth/resend-email-otp", json={"email": email})
        assert resend_res1.status_code == 429

        # 3. Simulate cooldown expiration in DB
        db.commit()
        db.execute(
            text("UPDATE otp_codes SET resend_available_at = DATE_SUB(NOW(), INTERVAL 10 SECOND) WHERE email = :email"),
            {"email": email},
        )
        db.commit()

        # 4. Resend should now succeed and dispatch email
        mock_send_otp.reset_mock()
        resend_res2 = client.post("/api/v1/auth/resend-email-otp", json={"email": email})
        assert resend_res2.status_code == 200
        assert resend_res2.json()["data"]["email_otp_sent"] is True
        mock_send_otp.assert_called_once()

    finally:
        # Cleanup
        db.execute(text("DELETE FROM otp_codes WHERE email = :email"), {"email": email})
        db.execute(text("DELETE FROM pending_users WHERE email = :email"), {"email": email})
        db.commit()
