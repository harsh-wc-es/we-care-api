-- WeCare complete local setup script for MySQL / MariaDB.
-- Import this into an empty selected database such as `wecare_db`.
-- Optional mysql CLI setup:
-- CREATE DATABASE IF NOT EXISTS wecare_db CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
-- USE wecare_db;

-- WeCare local development schema only. No runtime data.
-- Safe to import into a fresh MySQL / MariaDB database.
SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";
SET FOREIGN_KEY_CHECKS=0;

DROP TABLE IF EXISTS `visit_activity_logs`;
DROP TABLE IF EXISTS `visit_notes`;
DROP TABLE IF EXISTS `visit_tracking`;
DROP TABLE IF EXISTS `users`;
DROP TABLE IF EXISTS `tokens`;
DROP TABLE IF EXISTS `support_tickets`;
DROP TABLE IF EXISTS `sos_alerts`;
DROP TABLE IF EXISTS `reviews`;
DROP TABLE IF EXISTS `replacement_tickets`;
DROP TABLE IF EXISTS `rate_limits`;
DROP TABLE IF EXISTS `pricing_tiers`;
DROP TABLE IF EXISTS `pending_users`;
DROP TABLE IF EXISTS `payments`;
DROP TABLE IF EXISTS `patient_details`;
DROP TABLE IF EXISTS `password_reset_tokens`;
DROP TABLE IF EXISTS `otp_verifications`;
DROP TABLE IF EXISTS `otp_codes`;
DROP TABLE IF EXISTS `notifications`;
DROP TABLE IF EXISTS `family_profiles`;
DROP TABLE IF EXISTS `documents`;
DROP TABLE IF EXISTS `complaints`;
DROP TABLE IF EXISTS `caretaker_feedback`;
DROP TABLE IF EXISTS `caregiver_pricing_history`;
DROP TABLE IF EXISTS `caretaker_profiles`;
DROP TABLE IF EXISTS `caretaker_payouts`;
DROP TABLE IF EXISTS `caretaker_payout_items`;
DROP TABLE IF EXISTS `caretaker_availability`;
DROP TABLE IF EXISTS `booking_refunds`;
DROP TABLE IF EXISTS `bookings`;
DROP TABLE IF EXISTS `booking_checklist_tasks`;
DROP TABLE IF EXISTS `admin_audit_logs`;

-- --------------------------------------------------------
-- Table structure for `admin_audit_logs`
-- --------------------------------------------------------
CREATE TABLE `admin_audit_logs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `admin_user_id` int(11) DEFAULT NULL,
  `action` varchar(120) NOT NULL,
  `entity_type` varchar(80) NOT NULL,
  `entity_id` int(11) DEFAULT NULL,
  `old_values` text DEFAULT NULL,
  `new_values` text DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `user_agent` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_audit_admin` (`admin_user_id`),
  KEY `idx_audit_entity` (`entity_type`,`entity_id`),
  KEY `idx_audit_created_at` (`created_at`),
  CONSTRAINT `fk_audit_admin` FOREIGN KEY (`admin_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `booking_checklist_tasks`
-- --------------------------------------------------------
CREATE TABLE `booking_checklist_tasks` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `booking_id` int(11) NOT NULL,
  `family_user_id` int(11) NOT NULL,
  `caretaker_user_id` int(11) DEFAULT NULL,
  `title` varchar(150) NOT NULL,
  `description` text DEFAULT NULL,
  `status` enum('pending','ongoing','completed') NOT NULL DEFAULT 'pending',
  `completed_by` int(11) DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_tasks_booking` (`booking_id`),
  KEY `idx_tasks_family` (`family_user_id`),
  KEY `idx_tasks_caretaker` (`caretaker_user_id`),
  KEY `fk_tasks_completed_by` (`completed_by`),
  CONSTRAINT `fk_tasks_booking` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_tasks_caretaker` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_tasks_completed_by` FOREIGN KEY (`completed_by`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_tasks_family` FOREIGN KEY (`family_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `bookings`
-- --------------------------------------------------------
CREATE TABLE `bookings` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `family_user_id` int(11) NOT NULL,
  `caretaker_user_id` int(11) DEFAULT NULL,
  `patient_id` int(11) DEFAULT NULL,
  `service_type` varchar(100) NOT NULL,
  `booking_date` date NOT NULL,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL,
  `address` text NOT NULL,
  `location_latitude` decimal(10,7) DEFAULT NULL,
  `location_longitude` decimal(10,7) DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `request_priority` enum('normal','high','urgent') NOT NULL DEFAULT 'normal',
  `status` enum('pending','accepted','in_progress','completed','declined','cancelled') DEFAULT 'pending',
  `cancelled_by` varchar(30) DEFAULT NULL,
  `cancellation_reason` text DEFAULT NULL,
  `decline_reason_code` varchar(50) DEFAULT NULL,
  `decline_reason_label` varchar(120) DEFAULT NULL,
  `decline_note` text DEFAULT NULL,
  `responded_at` datetime DEFAULT NULL,
  `cancelled_at` datetime DEFAULT NULL,
  `cancelled_by_user_id` int(11) DEFAULT NULL,
  `cancelled_by_role` varchar(30) DEFAULT NULL,
  `cancel_reason_code` varchar(50) DEFAULT NULL,
  `cancel_reason_label` varchar(100) DEFAULT NULL,
  `cancel_note` text DEFAULT NULL,
  `refund_percentage` decimal(5,2) NOT NULL DEFAULT 0.00,
  `refund_amount` decimal(10,2) NOT NULL DEFAULT 0.00,
  `cancellation_fee` decimal(10,2) NOT NULL DEFAULT 0.00,
  `refund_status` enum('not_applicable','pending','processed','failed') NOT NULL DEFAULT 'not_applicable',
  `refund_eligible` tinyint(1) NOT NULL DEFAULT 0,
  `total_amount` decimal(10,2) DEFAULT 0.00,
  `pricing_tier_id` bigint(20) DEFAULT NULL,
  `pricing_tier` varchar(30) DEFAULT NULL,
  `skill_level` varchar(30) DEFAULT NULL,
  `customer_hourly_rate` decimal(10,2) NOT NULL DEFAULT 0.00,
  `caretaker_hourly_rate` decimal(10,2) NOT NULL DEFAULT 0.00,
  `platform_commission_hourly` decimal(10,2) NOT NULL DEFAULT 0.00,
  `total_customer_amount` decimal(10,2) NOT NULL DEFAULT 0.00,
  `caretaker_earning_amount` decimal(10,2) NOT NULL DEFAULT 0.00,
  `platform_commission_amount` decimal(10,2) NOT NULL DEFAULT 0.00,
  `care_points_earned` int(11) NOT NULL DEFAULT 0,
  `total_hours` decimal(6,2) NOT NULL DEFAULT 0.00,
  `payment_status` enum('pending','paid','failed','refunded') DEFAULT 'pending',
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `completed_at` datetime DEFAULT NULL,
  `payout_status` enum('not_applicable','hold','ready_for_payout','disputed','paid') NOT NULL DEFAULT 'not_applicable',
  `payout_hold_until` datetime DEFAULT NULL,
  `payout_paid_at` datetime DEFAULT NULL,
  `payout_id` int(11) DEFAULT NULL,
  `paid_amount` decimal(10,2) DEFAULT 0.00,
  `remaining_amount` decimal(10,2) DEFAULT 0.00,
  PRIMARY KEY (`id`),
  KEY `family_user_id` (`family_user_id`),
  KEY `caretaker_user_id` (`caretaker_user_id`),
  KEY `patient_id` (`patient_id`),
  KEY `idx_booking_payout_status` (`payout_status`),
  KEY `idx_booking_payout_hold_until` (`payout_hold_until`),
  KEY `idx_booking_completed_at` (`completed_at`),
  KEY `idx_booking_payout_id` (`payout_id`),
  KEY `idx_booking_pricing_tier` (`pricing_tier`),
  KEY `idx_booking_caretaker_earning` (`caretaker_earning_amount`),
  KEY `idx_booking_pricing_tier_id` (`pricing_tier_id`),
  KEY `idx_booking_skill_level` (`skill_level`),
  KEY `idx_booking_cancelled_at` (`cancelled_at`),
  KEY `idx_bookings_cancel_reason_code` (`cancel_reason_code`),
  KEY `idx_bookings_refund_status` (`refund_status`),
  KEY `idx_bookings_cancelled_by_user` (`cancelled_by_user_id`),
  KEY `idx_bookings_request_priority` (`request_priority`),
  KEY `idx_bookings_responded_at` (`responded_at`),
  CONSTRAINT `bookings_ibfk_1` FOREIGN KEY (`family_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `bookings_ibfk_2` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `bookings_ibfk_3` FOREIGN KEY (`patient_id`) REFERENCES `patient_details` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `caretaker_availability`
-- --------------------------------------------------------
CREATE TABLE `caretaker_availability` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `caretaker_user_id` int(11) NOT NULL,
  `available_date` date NOT NULL,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL,
  `is_available` tinyint(1) DEFAULT 1,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `caretaker_user_id` (`caretaker_user_id`),
  CONSTRAINT `caretaker_availability_ibfk_1` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `caretaker_payout_items`
-- --------------------------------------------------------
CREATE TABLE `caretaker_payout_items` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `payout_id` int(11) NOT NULL,
  `booking_id` int(11) NOT NULL,
  `caretaker_user_id` int(11) NOT NULL,
  `amount` decimal(10,2) NOT NULL DEFAULT 0.00,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_payout_booking` (`booking_id`),
  KEY `idx_payout_items_payout` (`payout_id`),
  KEY `idx_payout_items_caretaker` (`caretaker_user_id`),
  CONSTRAINT `fk_payout_items_booking` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_payout_items_caretaker` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_payout_items_payout` FOREIGN KEY (`payout_id`) REFERENCES `caretaker_payouts` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `caretaker_payouts`
-- --------------------------------------------------------
CREATE TABLE `caretaker_payouts` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `caretaker_user_id` int(11) NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  `gross_customer_amount` decimal(10,2) NOT NULL DEFAULT 0.00,
  `total_caretaker_earnings` decimal(10,2) NOT NULL DEFAULT 0.00,
  `total_platform_commission` decimal(10,2) NOT NULL DEFAULT 0.00,
  `week_start` date DEFAULT NULL,
  `week_end` date DEFAULT NULL,
  `status` enum('pending','processing','paid','failed') NOT NULL DEFAULT 'pending',
  `payment_method` varchar(50) DEFAULT NULL,
  `transaction_reference` varchar(255) DEFAULT NULL,
  `payment_reference` varchar(255) DEFAULT NULL,
  `admin_note` text DEFAULT NULL,
  `settled_by` int(11) DEFAULT NULL,
  `settled_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_payout_caretaker` (`caretaker_user_id`),
  KEY `idx_payout_status` (`status`),
  KEY `fk_payout_settled_by` (`settled_by`),
  KEY `idx_payout_week` (`week_start`,`week_end`),
  CONSTRAINT `fk_payout_caretaker` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_payout_settled_by` FOREIGN KEY (`settled_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `caretaker_profiles`
-- --------------------------------------------------------
CREATE TABLE `caretaker_profiles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `full_name` varchar(100) DEFAULT NULL,
  `gender` enum('male','female','other') DEFAULT NULL,
  `date_of_birth` date DEFAULT NULL,
  `experience_years` int(11) DEFAULT 0,
  `qualification` varchar(255) DEFAULT NULL,
  `bio` text DEFAULT NULL,
  `hourly_rate` decimal(10,2) DEFAULT 0.00,
  `pricing_tier_id` bigint(20) DEFAULT NULL,
  `pricing_tier` varchar(30) DEFAULT NULL,
  `skill_level` varchar(30) DEFAULT NULL,
  `customer_hourly_rate` decimal(10,2) NOT NULL DEFAULT 0.00,
  `caretaker_hourly_rate` decimal(10,2) NOT NULL DEFAULT 0.00,
  `platform_commission_hourly` decimal(10,2) NOT NULL DEFAULT 0.00,
  `commission_percentage` decimal(5,2) NOT NULL DEFAULT 0.00,
  `payout_priority` int(11) NOT NULL DEFAULT 0,
  `pricing_override_enabled` tinyint(1) NOT NULL DEFAULT 0,
  `address` text DEFAULT NULL,
  `city` varchar(100) DEFAULT NULL,
  `state` varchar(100) DEFAULT NULL,
  `pincode` varchar(10) DEFAULT NULL,
  `availability_status` enum('available','busy','offline') DEFAULT 'offline',
  `verification_status` enum('pending','pending_review','approved','rejected','needs_resubmission','banned') DEFAULT 'pending',
  `is_banned` tinyint(1) NOT NULL DEFAULT 0,
  `is_available` tinyint(1) NOT NULL DEFAULT 0,
  `manual_availability_enabled` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Caretaker personal preference; preserved across system-forced changes',
  `availability_reason` enum('manual_off','manual_on','on_visit','inactive','pending_review','rejected','admin_forced_off','admin_forced_on') NOT NULL DEFAULT 'manual_off' COMMENT 'Machine-readable reason for current availability state',
  `availability_locked_by_admin` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'When 1, caretaker cannot self-modify availability',
  `availability_locked_note` text DEFAULT NULL COMMENT 'Admin-provided note explaining the lock',
  `availability_locked_at` datetime DEFAULT NULL COMMENT 'UTC timestamp when admin lock was applied',
  `availability_locked_by_user_id` bigint(20) DEFAULT NULL COMMENT 'Admin user_id who applied the lock',
  `availability_auto_restored_at` datetime DEFAULT NULL COMMENT 'UTC timestamp when availability was last auto-restored after a visit',
  `availability_changed_at` datetime DEFAULT NULL COMMENT 'UTC timestamp of last availability state change',
  `availability_changed_by` enum('caretaker','system','admin') NOT NULL DEFAULT 'caretaker' COMMENT 'Actor who last changed availability',
  `availability_version` int(11) NOT NULL DEFAULT 1 COMMENT 'Optimistic locking version; incremented on every availability change',
  `availability_updated_at` datetime DEFAULT NULL,
  `last_active_at` datetime DEFAULT NULL,
  `rating` decimal(3,2) DEFAULT 0.00,
  `total_reviews` int(11) DEFAULT 0,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `rejection_reason` text DEFAULT NULL,
  `ban_reason` text DEFAULT NULL,
  `banned_at` datetime DEFAULT NULL,
  `banned_by_admin_id` int(11) DEFAULT NULL,
  `approved_at` datetime DEFAULT NULL,
  `approved_by_admin_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  KEY `idx_caretaker_pricing_tier` (`pricing_tier`),
  KEY `idx_caretaker_skill_level` (`skill_level`),
  KEY `idx_caretaker_pricing_tier_id` (`pricing_tier_id`),
  KEY `idx_caretaker_pricing_override` (`pricing_override_enabled`),
  KEY `idx_caretaker_is_available` (`is_available`),
  KEY `idx_caretaker_availability_updated_at` (`availability_updated_at`),
  KEY `idx_caretaker_availability_reason` (`availability_reason`),
  KEY `idx_caretaker_last_active_at` (`last_active_at`),
  KEY `idx_caretaker_admin_locked` (`availability_locked_by_admin`),
  KEY `idx_caretaker_verification_status` (`verification_status`),
  CONSTRAINT `caretaker_profiles_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `caregiver_pricing_history`
-- --------------------------------------------------------
CREATE TABLE `caregiver_pricing_history` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `caretaker_user_id` int(11) NOT NULL,
  `old_tier_id` int(11) DEFAULT NULL,
  `new_tier_id` int(11) DEFAULT NULL,
  `old_customer_rate_per_hour` decimal(10,2) DEFAULT NULL,
  `new_customer_rate_per_hour` decimal(10,2) DEFAULT NULL,
  `old_caregiver_rate_per_hour` decimal(10,2) DEFAULT NULL,
  `new_caregiver_rate_per_hour` decimal(10,2) DEFAULT NULL,
  `old_commission_percent` decimal(5,2) DEFAULT NULL,
  `new_commission_percent` decimal(5,2) DEFAULT NULL,
  `admin_user_id` int(11) DEFAULT NULL,
  `admin_note` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_caregiver_pricing_history_caretaker` (`caretaker_user_id`),
  KEY `idx_caregiver_pricing_history_admin` (`admin_user_id`),
  CONSTRAINT `fk_caregiver_pricing_history_admin` FOREIGN KEY (`admin_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_caregiver_pricing_history_caretaker` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `caretaker_feedback`
-- --------------------------------------------------------
CREATE TABLE `caretaker_feedback` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `caretaker_user_id` int(11) NOT NULL,
  `rating` tinyint(4) NOT NULL,
  `feedback` text DEFAULT NULL,
  `suggestion` text DEFAULT NULL,
  `is_anonymous` tinyint(1) NOT NULL DEFAULT 0,
  `status` enum('pending','reviewed','archived') NOT NULL DEFAULT 'pending',
  `admin_note` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `reviewed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_caretaker_feedback_user` (`caretaker_user_id`),
  KEY `idx_caretaker_feedback_rating` (`rating`),
  KEY `idx_caretaker_feedback_status` (`status`),
  KEY `idx_caretaker_feedback_created_at` (`created_at`),
  CONSTRAINT `fk_caretaker_feedback_user` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `complaints`
-- --------------------------------------------------------
CREATE TABLE `complaints` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `booking_id` int(11) NOT NULL,
  `family_user_id` int(11) NOT NULL,
  `caretaker_user_id` int(11) DEFAULT NULL,
  `subject` varchar(150) NOT NULL,
  `description` text NOT NULL,
  `proof_file` varchar(255) DEFAULT NULL,
  `status` enum('open','in_review','resolved','rejected') NOT NULL DEFAULT 'open',
  `admin_note` text DEFAULT NULL,
  `resolved_by` int(11) DEFAULT NULL,
  `resolved_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_complaints_booking` (`booking_id`),
  KEY `idx_complaints_family` (`family_user_id`),
  KEY `idx_complaints_status` (`status`),
  KEY `fk_complaints_caretaker` (`caretaker_user_id`),
  KEY `fk_complaints_resolved_by` (`resolved_by`),
  CONSTRAINT `fk_complaints_booking` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_complaints_caretaker` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_complaints_family` FOREIGN KEY (`family_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_complaints_resolved_by` FOREIGN KEY (`resolved_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `documents`
-- --------------------------------------------------------
CREATE TABLE `documents` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `document_type` varchar(100) NOT NULL,
  `file_path` varchar(255) NOT NULL,
  `original_file_name` varchar(255) DEFAULT NULL,
  `status` enum('uploaded','pending','approved','rejected','reuploaded') DEFAULT 'uploaded',
  `admin_note` text DEFAULT NULL,
  `rejection_reason` text DEFAULT NULL,
  `reviewed_by_admin_id` int(11) DEFAULT NULL,
  `reviewed_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `uploaded_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `documents_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `family_profiles`
-- --------------------------------------------------------
CREATE TABLE `family_profiles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `full_name` varchar(100) DEFAULT NULL,
  `gender` enum('male','female','other') DEFAULT NULL,
  `date_of_birth` date DEFAULT NULL,
  `address` text DEFAULT NULL,
  `city` varchar(100) DEFAULT NULL,
  `state` varchar(100) DEFAULT NULL,
  `pincode` varchar(10) DEFAULT NULL,
  `emergency_contact_name` varchar(100) DEFAULT NULL,
  `emergency_contact_phone` varchar(15) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `family_profiles_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `notifications`
-- --------------------------------------------------------
CREATE TABLE `notifications` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `title` varchar(150) NOT NULL,
  `message` text NOT NULL,
  `type` varchar(60) NOT NULL DEFAULT 'admin_announcement',
  `related_type` varchar(60) DEFAULT NULL,
  `related_id` int(11) DEFAULT NULL,
  `metadata` text DEFAULT NULL,
  `is_read` tinyint(1) DEFAULT 0,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  KEY `idx_notifications_type` (`type`),
  KEY `idx_notifications_user_read` (`user_id`,`is_read`,`id`),
  CONSTRAINT `notifications_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `notification_device_tokens`
-- --------------------------------------------------------
CREATE TABLE `notification_device_tokens` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `device_token` varchar(255) NOT NULL,
  `platform` enum('android','ios','web') NOT NULL,
  `app_type` enum('family','caretaker','admin') NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `last_used_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_device_token` (`device_token`),
  KEY `idx_device_tokens_user` (`user_id`),
  KEY `idx_device_tokens_active` (`is_active`),
  CONSTRAINT `fk_device_tokens_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `otp_codes`
-- --------------------------------------------------------
CREATE TABLE `otp_codes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) DEFAULT NULL,
  `pending_user_id` bigint(20) unsigned DEFAULT NULL,
  `booking_id` int(11) DEFAULT NULL,
  `email` varchar(150) DEFAULT NULL,
  `purpose` enum('register_email','login','password_reset','visit_start','password_reset_authenticated') NOT NULL,
  `otp_hash` varchar(255) NOT NULL,
  `expires_at` datetime NOT NULL,
  `resend_available_at` datetime DEFAULT NULL,
  `attempts` int(11) NOT NULL DEFAULT 0,
  `max_attempts` int(11) NOT NULL DEFAULT 5,
  `used_at` datetime DEFAULT NULL,
  `metadata` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_otp_user_purpose` (`user_id`,`purpose`),
  KEY `idx_otp_booking_purpose` (`booking_id`,`purpose`),
  KEY `idx_otp_email_purpose` (`email`,`purpose`),
  KEY `idx_otp_expires_at` (`expires_at`),
  KEY `idx_otp_codes_pending_user` (`pending_user_id`),
  CONSTRAINT `fk_otp_booking` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_otp_codes_pending_user` FOREIGN KEY (`pending_user_id`) REFERENCES `pending_users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_otp_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `otp_verifications`
-- --------------------------------------------------------
CREATE TABLE `otp_verifications` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) DEFAULT NULL,
  `login_identifier` varchar(190) NOT NULL,
  `purpose` enum('forgot_password') NOT NULL,
  `otp_hash` varchar(255) NOT NULL,
  `attempts` int(11) NOT NULL DEFAULT 0,
  `max_attempts` int(11) NOT NULL DEFAULT 5,
  `expires_at` datetime NOT NULL,
  `resend_available_at` datetime DEFAULT NULL,
  `verified_at` datetime DEFAULT NULL,
  `used_at` datetime DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_otp_verifications_user` (`user_id`),
  KEY `idx_otp_verifications_login_purpose` (`login_identifier`,`purpose`),
  KEY `idx_otp_verifications_expires_at` (`expires_at`),
  CONSTRAINT `fk_otp_verifications_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `password_reset_tokens`
-- --------------------------------------------------------
CREATE TABLE `password_reset_tokens` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `token_hash` varchar(255) NOT NULL,
  `expires_at` datetime NOT NULL,
  `used_at` datetime DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_password_reset_user` (`user_id`),
  KEY `idx_password_reset_expires_at` (`expires_at`),
  CONSTRAINT `fk_password_reset_tokens_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `patient_details`
-- --------------------------------------------------------
CREATE TABLE `patient_details` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `family_user_id` int(11) NOT NULL,
  `patient_name` varchar(100) NOT NULL,
  `age` int(11) DEFAULT NULL,
  `gender` enum('male','female','other') DEFAULT NULL,
  `medical_condition` text DEFAULT NULL,
  `allergies` text DEFAULT NULL,
  `medications` text DEFAULT NULL,
  `special_instructions` text DEFAULT NULL,
  `mobility_status` varchar(100) DEFAULT NULL,
  `care_type` varchar(100) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_patient_details_family_user_id` (`family_user_id`),
  KEY `family_user_id` (`family_user_id`),
  CONSTRAINT `patient_details_ibfk_1` FOREIGN KEY (`family_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `payments`
-- --------------------------------------------------------
CREATE TABLE `payments` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `booking_id` int(11) NOT NULL,
  `family_user_id` int(11) NOT NULL,
  `caretaker_user_id` int(11) DEFAULT NULL,
  `amount` decimal(10,2) NOT NULL,
  `payment_method` enum('card','upi','netbanking','wallet','cash','insurance','other') NOT NULL DEFAULT 'cash',
  `transaction_id` varchar(255) DEFAULT NULL,
  `gateway_transaction_reference` varchar(255) DEFAULT NULL,
  `gateway_response_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`gateway_response_json`)),
  `status` enum('pending','success','failed','refunded') DEFAULT 'pending',
  `verification_status` enum('not_required','pending','verified','failed') NOT NULL DEFAULT 'pending',
  `paid_at` datetime DEFAULT NULL,
  `verified_at` datetime DEFAULT NULL,
  `failure_reason` varchar(255) DEFAULT NULL,
  `idempotency_key` varchar(191) DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `payment_type` enum('advance','remaining','full') DEFAULT 'advance',
  `total_amount` decimal(10,2) DEFAULT 0.00,
  `remaining_amount` decimal(10,2) DEFAULT 0.00,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payments_idempotency_key` (`idempotency_key`),
  KEY `booking_id` (`booking_id`),
  KEY `family_user_id` (`family_user_id`),
  KEY `idx_payments_verification_status` (`verification_status`),
  KEY `idx_payments_gateway_reference` (`gateway_transaction_reference`),
  CONSTRAINT `payments_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `payments_ibfk_2` FOREIGN KEY (`family_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `booking_refunds`
-- --------------------------------------------------------
CREATE TABLE `booking_refunds` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `booking_id` int(11) NOT NULL,
  `family_user_id` int(11) NOT NULL,
  `caretaker_user_id` int(11) DEFAULT NULL,
  `payment_id` int(11) DEFAULT NULL,
  `paid_amount` decimal(10,2) NOT NULL DEFAULT 0.00,
  `refund_amount` decimal(10,2) NOT NULL DEFAULT 0.00,
  `refund_percentage` decimal(5,2) NOT NULL DEFAULT 0.00,
  `refund_method` varchar(50) DEFAULT NULL,
  `refund_transaction_id` varchar(255) DEFAULT NULL,
  `reason` text DEFAULT NULL,
  `status` enum('pending','approved','rejected','processed','failed') NOT NULL DEFAULT 'pending',
  `admin_note` text DEFAULT NULL,
  `processed_by_admin_id` int(11) DEFAULT NULL,
  `approved_at` datetime DEFAULT NULL,
  `rejected_at` datetime DEFAULT NULL,
  `processed_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_booking_refunds_booking` (`booking_id`),
  KEY `idx_booking_refunds_booking` (`booking_id`),
  KEY `idx_booking_refunds_family` (`family_user_id`),
  KEY `idx_booking_refunds_caretaker` (`caretaker_user_id`),
  KEY `idx_booking_refunds_payment` (`payment_id`),
  KEY `idx_booking_refunds_status` (`status`),
  KEY `idx_booking_refunds_created_at` (`created_at`),
  KEY `fk_booking_refunds_admin` (`processed_by_admin_id`),
  CONSTRAINT `fk_booking_refunds_admin` FOREIGN KEY (`processed_by_admin_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_booking_refunds_booking` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_booking_refunds_caretaker` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_booking_refunds_family` FOREIGN KEY (`family_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_booking_refunds_payment` FOREIGN KEY (`payment_id`) REFERENCES `payments` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `pending_users`
-- --------------------------------------------------------
CREATE TABLE `pending_users` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `full_name` varchar(150) DEFAULT NULL,
  `username` varchar(30) NOT NULL,
  `email` varchar(191) NOT NULL,
  `phone_number` varchar(20) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` enum('family','caretaker','admin') NOT NULL,
  `registration_payload` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`registration_payload`)),
  `otp_verified_at` datetime DEFAULT NULL,
  `expires_at` datetime NOT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_pending_users_username` (`username`),
  UNIQUE KEY `uq_pending_users_email` (`email`),
  UNIQUE KEY `uq_pending_users_phone` (`phone_number`),
  KEY `idx_pending_users_expires_at` (`expires_at`),
  KEY `idx_pending_users_role` (`role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------
-- Table structure for `pricing_tiers`
-- --------------------------------------------------------
CREATE TABLE `pricing_tiers` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `slug` varchar(100) NOT NULL,
  `description` text DEFAULT NULL,
  `skill_level` varchar(30) DEFAULT NULL,
  `customer_hourly_rate` decimal(10,2) NOT NULL DEFAULT 0.00,
  `caretaker_hourly_rate` decimal(10,2) NOT NULL DEFAULT 0.00,
  `platform_commission_hourly` decimal(10,2) NOT NULL DEFAULT 0.00,
  `commission_percentage` decimal(5,2) NOT NULL DEFAULT 0.00,
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_pricing_tiers_slug` (`slug`),
  KEY `idx_pricing_tiers_active` (`is_active`),
  KEY `idx_pricing_tiers_skill_level` (`skill_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `rate_limits`
-- --------------------------------------------------------
CREATE TABLE `rate_limits` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `rate_key` varchar(190) NOT NULL,
  `action` varchar(80) NOT NULL,
  `attempts` int(11) NOT NULL DEFAULT 1,
  `window_start` datetime NOT NULL,
  `blocked_until` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rate_key_action` (`rate_key`,`action`),
  KEY `idx_rate_blocked_until` (`blocked_until`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `replacement_tickets`
-- --------------------------------------------------------
CREATE TABLE `replacement_tickets` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `complaint_id` int(11) DEFAULT NULL,
  `booking_id` int(11) NOT NULL,
  `family_user_id` int(11) NOT NULL,
  `requested_by_user_id` int(11) DEFAULT NULL,
  `original_caretaker_user_id` int(11) DEFAULT NULL,
  `replacement_caretaker_user_id` int(11) DEFAULT NULL,
  `reason` text NOT NULL,
  `status` enum('open','assigned','resolved','cancelled') NOT NULL DEFAULT 'open',
  `admin_note` text DEFAULT NULL,
  `resolved_by` int(11) DEFAULT NULL,
  `resolved_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_replacements_complaint` (`complaint_id`),
  KEY `idx_replacements_booking` (`booking_id`),
  KEY `idx_replacements_status` (`status`),
  KEY `fk_replacements_family` (`family_user_id`),
  KEY `fk_replacements_requested_by` (`requested_by_user_id`),
  KEY `fk_replacements_original` (`original_caretaker_user_id`),
  KEY `fk_replacements_new` (`replacement_caretaker_user_id`),
  KEY `fk_replacements_resolved_by` (`resolved_by`),
  CONSTRAINT `fk_replacements_booking` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_replacements_complaint` FOREIGN KEY (`complaint_id`) REFERENCES `complaints` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_replacements_family` FOREIGN KEY (`family_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_replacements_requested_by` FOREIGN KEY (`requested_by_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_replacements_new` FOREIGN KEY (`replacement_caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_replacements_original` FOREIGN KEY (`original_caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_replacements_resolved_by` FOREIGN KEY (`resolved_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `reviews`
-- --------------------------------------------------------
CREATE TABLE `reviews` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `booking_id` int(11) NOT NULL,
  `family_user_id` int(11) NOT NULL,
  `caretaker_user_id` int(11) NOT NULL,
  `rating` int(11) NOT NULL,
  `comment` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `booking_id` (`booking_id`),
  KEY `family_user_id` (`family_user_id`),
  KEY `caretaker_user_id` (`caretaker_user_id`),
  CONSTRAINT `reviews_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `reviews_ibfk_2` FOREIGN KEY (`family_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `reviews_ibfk_3` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `sos_alerts`
-- --------------------------------------------------------
CREATE TABLE `sos_alerts` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `booking_id` int(11) DEFAULT NULL,
  `message` text DEFAULT NULL,
  `latitude` varchar(50) DEFAULT NULL,
  `longitude` varchar(50) DEFAULT NULL,
  `status` enum('open','resolved') DEFAULT 'open',
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  KEY `booking_id` (`booking_id`),
  CONSTRAINT `sos_alerts_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `sos_alerts_ibfk_2` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `support_tickets`
-- --------------------------------------------------------
CREATE TABLE `support_tickets` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `subject` varchar(150) NOT NULL,
  `message` text NOT NULL,
  `status` enum('open','in_progress','closed') DEFAULT 'open',
  `admin_reply` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `support_tickets_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `tokens`
-- --------------------------------------------------------
CREATE TABLE `tokens` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `access_token` text NOT NULL,
  `refresh_token` text NOT NULL,
  `is_blacklisted` tinyint(1) DEFAULT 0,
  `expires_at` datetime NOT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `tokens_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `users`
-- --------------------------------------------------------
CREATE TABLE `users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `email` varchar(100) NOT NULL,
  `username` varchar(100) NOT NULL,
  `phone_number` varchar(15) NOT NULL,
  `password` varchar(255) NOT NULL,
  `role` enum('family','caretaker','admin') NOT NULL,
  `is_verified` tinyint(1) DEFAULT 0,
  `profile_picture` varchar(255) DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT 1,
  `reset_token` varchar(255) DEFAULT NULL,
  `reset_token_expiry` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `phone_number` (`phone_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `visit_tracking`
-- --------------------------------------------------------
CREATE TABLE `visit_tracking` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `booking_id` int(11) NOT NULL,
  `caretaker_user_id` int(11) NOT NULL,
  `check_in_time` datetime DEFAULT NULL,
  `check_out_time` datetime DEFAULT NULL,
  `check_in_lat` varchar(50) DEFAULT NULL,
  `check_in_lng` varchar(50) DEFAULT NULL,
  `check_out_lat` varchar(50) DEFAULT NULL,
  `check_out_lng` varchar(50) DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `booking_id` (`booking_id`),
  KEY `caretaker_user_id` (`caretaker_user_id`),
  CONSTRAINT `visit_tracking_ibfk_1` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `visit_tracking_ibfk_2` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `visit_notes`
-- --------------------------------------------------------
CREATE TABLE `visit_notes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `booking_id` int(11) NOT NULL,
  `visit_id` int(11) DEFAULT NULL,
  `caretaker_user_id` int(11) NOT NULL,
  `note` text NOT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_visit_notes_booking` (`booking_id`),
  KEY `idx_visit_notes_visit` (`visit_id`),
  KEY `idx_visit_notes_caretaker` (`caretaker_user_id`),
  CONSTRAINT `fk_visit_notes_booking` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_visit_notes_visit` FOREIGN KEY (`visit_id`) REFERENCES `visit_tracking` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_visit_notes_caretaker` FOREIGN KEY (`caretaker_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------
-- Table structure for `visit_activity_logs`
-- --------------------------------------------------------
CREATE TABLE `visit_activity_logs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `booking_id` int(11) NOT NULL,
  `visit_id` int(11) DEFAULT NULL,
  `actor_user_id` int(11) DEFAULT NULL,
  `actor_role` varchar(30) NOT NULL,
  `activity_type` varchar(60) NOT NULL,
  `message` varchar(255) NOT NULL,
  `metadata` text DEFAULT NULL,
  `created_at` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_visit_activity_booking` (`booking_id`),
  KEY `idx_visit_activity_visit` (`visit_id`),
  KEY `idx_visit_activity_actor` (`actor_user_id`),
  KEY `idx_visit_activity_type` (`activity_type`),
  CONSTRAINT `fk_visit_activity_booking` FOREIGN KEY (`booking_id`) REFERENCES `bookings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_visit_activity_visit` FOREIGN KEY (`visit_id`) REFERENCES `visit_tracking` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_visit_activity_actor` FOREIGN KEY (`actor_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

SET FOREIGN_KEY_CHECKS=1;


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
TRUNCATE TABLE `visit_activity_logs`;
TRUNCATE TABLE `visit_notes`;
TRUNCATE TABLE `visit_tracking`;
TRUNCATE TABLE `booking_refunds`;
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
    (1, 'admin@wecare.com', 'admin', '9000000001', '$2y$10$Hu72PRxLHDmdPGqETmyLnelj0uGrZHnVNxJe6etFUXGcOYlnc6Aq2', 'admin', 1, 1, NOW(), NOW()),
    (2, 'family@wecare.com', 'family', '9000000002', '$2y$10$Hu72PRxLHDmdPGqETmyLnelj0uGrZHnVNxJe6etFUXGcOYlnc6Aq2', 'family', 1, 1, NOW(), NOW()),
    (3, 'caretaker@wecare.com', 'caretaker', '9000000003', '$2y$10$Hu72PRxLHDmdPGqETmyLnelj0uGrZHnVNxJe6etFUXGcOYlnc6Aq2', 'caretaker', 1, 1, NOW(), NOW());

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
