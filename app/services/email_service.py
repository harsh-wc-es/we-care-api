"""
WeCare — SMTP Email Delivery Service

Provides real SMTP email delivery for OTP and notification flows using
only Python standard-library modules (smtplib, email.message.EmailMessage).

Features:
- STARTTLS connection (standard for Gmail SMTP: smtp.gmail.com:587)
- Branded responsive HTML template with plain-text fallback
- Centralized configuration via app.core.config.get_settings()
- Secure credential management (no passwords or credentials logged/exposed)
- Graceful exception handling and connection lifecycle management
"""

import logging
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def is_smtp_configured() -> bool:
    """
    Checks if all required SMTP settings are present in application configuration.
    """
    settings = get_settings()
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_PORT
        and settings.SMTP_USERNAME
        and settings.SMTP_PASSWORD
    )


def build_otp_email_template(
    otp: str,
    purpose: str = "Email Verification",
    expiry_minutes: int = 10,
    app_name: str = "WeCare",
) -> Dict[str, str]:
    """
    Builds subject, plain-text body, and responsive HTML body for OTP verification emails.
    """
    subject = f"{app_name} - {purpose} Code"

    # Plain text version
    text_body = (
        f"{app_name} - {purpose}\n\n"
        f"Your verification code is:\n\n"
        f"    {otp}\n\n"
        f"This code will expire in {expiry_minutes} minutes.\n\n"
        f"Do not share this code with anyone. {app_name} staff will never ask for your OTP.\n"
        f"If you did not request this verification code, you can safely ignore this email.\n\n"
        f"Regards,\n"
        f"The {app_name} Team\n"
    )

    # Branded responsive HTML version
    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{app_name} - {purpose}</title>
<style type="text/css">
  body {{
    margin: 0;
    padding: 0;
    background-color: #f4f6f9;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    color: #333333;
  }}
  .container {{
    max-width: 560px;
    margin: 30px auto;
    background-color: #ffffff;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }}
  .header {{
    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
    padding: 24px 30px;
    text-align: center;
    color: #ffffff;
  }}
  .header h1 {{
    margin: 0;
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 0.5px;
  }}
  .content {{
    padding: 30px;
  }}
  .content h2 {{
    margin-top: 0;
    color: #1e3c72;
    font-size: 20px;
  }}
  .content p {{
    font-size: 15px;
    line-height: 1.6;
    color: #555555;
    margin-bottom: 20px;
  }}
  .otp-box {{
    background-color: #f0f4fb;
    border: 2px dashed #2a5298;
    border-radius: 8px;
    padding: 18px;
    text-align: center;
    margin: 24px 0;
  }}
  .otp-code {{
    font-size: 32px;
    font-weight: 800;
    letter-spacing: 6px;
    color: #1e3c72;
    font-family: 'Courier New', Courier, monospace;
  }}
  .expiry {{
    font-size: 13px;
    color: #e65100;
    font-weight: 600;
    margin-top: 8px;
  }}
  .warning {{
    font-size: 13px;
    color: #777777;
    border-top: 1px solid #eeeeee;
    padding-top: 18px;
    margin-top: 24px;
  }}
  .footer {{
    background-color: #f8fafc;
    padding: 16px 30px;
    text-align: center;
    font-size: 12px;
    color: #999999;
    border-top: 1px solid #eeeeee;
  }}
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{app_name}</h1>
    </div>
    <div class="content">
      <h2>{purpose}</h2>
      <p>Hello,</p>
      <p>Please use the following One-Time Password (OTP) to complete your verification with <strong>{app_name}</strong>:</p>
      <div class="otp-box">
        <div class="otp-code">{otp}</div>
        <div class="expiry">&#9201; Valid for {expiry_minutes} minutes</div>
      </div>
      <p>If you did not request this verification code, please ignore this email or contact support if you have concerns.</p>
      <div class="warning">
        <strong>Security Notice:</strong> Never share your verification code with anyone. {app_name} will never ask for your code via phone, chat, or email.
      </div>
    </div>
    <div class="footer">
      &copy; {app_name} Healthcare Services. All rights reserved.
    </div>
  </div>
</body>
</html>"""

    return {
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }


def send_email(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> bool:
    """
    Sends an email via SMTP using Python's standard library smtplib and EmailMessage.
    
    Returns:
        True if sent successfully, False on missing configuration or delivery failure.
    """
    settings = get_settings()

    if not is_smtp_configured():
        logger.warning(
            "SMTP is not configured on the backend. Email to %s was not dispatched.",
            to_email,
        )
        return False

    from_email = settings.smtp_from
    from_name = settings.SMTP_FROM_NAME or "WeCare"
    sender_header = f"{from_name} <{from_email}>" if from_name else from_email

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender_header
    msg["To"] = to_email
    msg.set_content(body_text)

    if body_html:
        msg.add_alternative(body_html, subtype="html")

    host = settings.SMTP_HOST
    port = int(settings.SMTP_PORT or 587)
    username = settings.SMTP_USERNAME
    password = settings.SMTP_PASSWORD

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(username, password)
            server.send_message(msg)

        logger.info("Successfully delivered email to %s (Subject: %s)", to_email, subject)
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error("SMTP authentication failed for user %s: %s", username, str(e.smtp_error if hasattr(e, 'smtp_error') else e))
        return False
    except smtplib.SMTPConnectError as e:
        logger.error("Failed to connect to SMTP host %s:%s: %s", host, port, str(e))
        return False
    except smtplib.SMTPException as e:
        logger.error("SMTP protocol error while sending email to %s: %s", to_email, str(e))
        return False
    except Exception as e:
        logger.error("Unexpected error while sending email to %s: %s", to_email, str(e))
        return False


def send_otp_email(
    to_email: str,
    otp: str,
    purpose: str = "Email Verification",
    expiry_minutes: int = 10,
) -> bool:
    """
    Generates an OTP email template and dispatches it to the recipient email via SMTP.
    
    Returns:
        True if sent successfully, False otherwise.
    """
    settings = get_settings()
    app_name = settings.SMTP_FROM_NAME or "WeCare"
    template = build_otp_email_template(
        otp=otp,
        purpose=purpose,
        expiry_minutes=expiry_minutes,
        app_name=app_name,
    )
    return send_email(
        to_email=to_email,
        subject=template["subject"],
        body_text=template["text"],
        body_html=template["html"],
    )
