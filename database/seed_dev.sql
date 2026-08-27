-- WeCare local development seed data.
-- Stable, lightweight demo rows only. No OTPs, tokens, audit history, visits, payments, SOS, or notifications.

SET FOREIGN_KEY_CHECKS=0;

TRUNCATE TABLE `tokens`;
TRUNCATE TABLE `password_reset_tokens`;
TRUNCATE TABLE `otp_verifications`;
TRUNCATE TABLE `otp_codes`;
TRUNCATE TABLE `rate_limits`;
TRUNCATE TABLE `notifications`;
TRUNCATE TABLE `admin_audit_logs`;
TRUNCATE TABLE `sos_alerts`;
TRUNCATE TABLE `visit_tracking`;
TRUNCATE TABLE `payments`;
TRUNCATE TABLE `reviews`;
TRUNCATE TABLE `replacement_tickets`;
TRUNCATE TABLE `complaints`;
TRUNCATE TABLE `booking_checklist_tasks`;
TRUNCATE TABLE `caretaker_payout_items`;
TRUNCATE TABLE `caretaker_payouts`;
TRUNCATE TABLE `bookings`;
TRUNCATE TABLE `patient_details`;
TRUNCATE TABLE `documents`;
TRUNCATE TABLE `caretaker_availability`;
TRUNCATE TABLE `family_profiles`;
TRUNCATE TABLE `caretaker_profiles`;
TRUNCATE TABLE `pending_users`;
TRUNCATE TABLE `pricing_tiers`;
TRUNCATE TABLE `users`;

INSERT INTO `users`
    (`id`, `email`, `username`, `phone_number`, `password`, `role`, `is_verified`, `is_active`, `created_at`, `updated_at`)
VALUES
    (1, 'admin@wecare.com', 'admin', '9000000001', '$2b$10$kZdwG/oSrxBD/f/TMB1mQ.wbg9d.KR6K0jPBpYYXDUJy9UQaoeu0q', 'admin', 1, 1, NOW(), NOW()),
    (2, 'family@wecare.com', 'family', '9000000002', '$2b$10$8zqYRyGT.dnBZI7fNO1EF.pVrqTYZEyZABUW/wwv8AfZTG5N/5.Ka', 'family', 1, 1, NOW(), NOW()),
    (3, 'caretaker@wecare.com', 'caretaker', '9000000003', '$2b$10$8zqYRyGT.dnBZI7fNO1EF.pVrqTYZEyZABUW/wwv8AfZTG5N/5.Ka', 'caretaker', 1, 1, NOW(), NOW());

INSERT INTO `family_profiles`
    (`id`, `user_id`, `full_name`, `gender`, `address`, `city`, `state`, `pincode`, `emergency_contact_name`, `emergency_contact_phone`, `created_at`, `updated_at`)
VALUES
    (1, 2, 'Demo Family User', 'other', 'Demo Street', 'Ahmedabad', 'Gujarat', '380001', 'Demo Contact', '9000000099', NOW(), NOW());

INSERT INTO `pricing_tiers`
    (`id`, `name`, `slug`, `description`, `skill_level`, `customer_hourly_rate`, `caretaker_hourly_rate`, `platform_commission_hourly`, `commission_percentage`, `is_active`, `created_at`, `updated_at`)
VALUES
    (1, 'Basic', 'basic', 'Entry-level elder care support', 'beginner', 180.00, 130.00, 50.00, 27.78, 1, NOW(), NOW()),
    (2, 'Standard', 'standard', 'Reliable general care provider', 'intermediate', 250.00, 190.00, 60.00, 24.00, 1, NOW(), NOW()),
    (3, 'Professional', 'professional', 'Experienced elder care provider', 'advanced', 350.00, 280.00, 70.00, 20.00, 1, NOW(), NOW()),
    (4, 'Medical', 'medical', 'Advanced medical care support', 'expert', 550.00, 450.00, 100.00, 18.18, 1, NOW(), NOW());

INSERT INTO `caretaker_profiles`
    (`id`, `user_id`, `full_name`, `gender`, `experience_years`, `qualification`, `bio`,
     `pricing_tier_id`, `pricing_tier`, `skill_level`, `customer_hourly_rate`, `caretaker_hourly_rate`,
     `platform_commission_hourly`, `commission_percentage`, `payout_priority`, `pricing_override_enabled`,
     `address`, `city`, `state`, `pincode`, `verification_status`, `is_available`,
     `manual_availability_enabled`, `availability_reason`, `availability_changed_at`, `availability_changed_by`,
     `availability_updated_at`, `rating`, `total_reviews`, `created_at`, `updated_at`)
VALUES
    (1, 3, 'Demo Caretaker', 'other', 3, 'General Care Certification', 'Demo approved caretaker account.',
     2, 'standard', 'intermediate', 250.00, 190.00, 60.00, 24.00, 0, 0,
     'Demo Caretaker Street', 'Ahmedabad', 'Gujarat', '380001', 'approved', 1,
     1, 'manual_on', NOW(), 'system', NOW(), 4.80, 12, NOW(), NOW());

INSERT INTO `patient_details`
    (`id`, `family_user_id`, `patient_name`, `age`, `gender`, `medical_condition`, `mobility_status`, `care_type`, `created_at`, `updated_at`)
VALUES
    (1, 2, 'Demo Patient', 72, 'other', 'Stable demo patient record', 'assisted', 'elder_care', NOW(), NOW());

SET FOREIGN_KEY_CHECKS=1;
