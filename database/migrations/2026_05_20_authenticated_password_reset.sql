-- Migration: Add password_reset_authenticated to otp_codes purpose ENUM
-- Date: 2026-05-20
-- Description: Adds 'password_reset_authenticated' as a valid purpose for OTP codes,
--              used by the new authenticated OTP-based password reset flow.

ALTER TABLE `otp_codes`
  MODIFY COLUMN `purpose` enum(
    'register_email',
    'login',
    'password_reset',
    'visit_start',
    'password_reset_authenticated'
  ) NOT NULL;
