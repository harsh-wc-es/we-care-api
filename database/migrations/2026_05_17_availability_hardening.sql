-- ============================================================
-- Migration: Availability Hardening
-- Date: 2026-05-17
-- Purpose: Add operational availability engine columns,
--          admin override controls, reason tracking,
--          version-based optimistic locking, and
--          realtime presence metadata to caretaker_profiles.
-- ============================================================

-- -----------------------------------------------------------
-- 1. Add new availability columns to caretaker_profiles
-- -----------------------------------------------------------

ALTER TABLE caretaker_profiles
    ADD COLUMN IF NOT EXISTS manual_availability_enabled TINYINT(1) NOT NULL DEFAULT 0
        COMMENT 'Caretaker personal preference; preserved across system-forced changes'
        AFTER is_available,

    ADD COLUMN IF NOT EXISTS availability_reason ENUM(
        'manual_off',
        'manual_on',
        'on_visit',
        'inactive',
        'pending_review',
        'rejected',
        'admin_forced_off',
        'admin_forced_on'
    ) NOT NULL DEFAULT 'manual_off'
        COMMENT 'Machine-readable reason for current availability state'
        AFTER manual_availability_enabled,

    ADD COLUMN IF NOT EXISTS availability_locked_by_admin TINYINT(1) NOT NULL DEFAULT 0
        COMMENT 'When 1, caretaker cannot self-modify availability'
        AFTER availability_reason,

    ADD COLUMN IF NOT EXISTS availability_locked_note TEXT NULL
        COMMENT 'Admin-provided note explaining the lock'
        AFTER availability_locked_by_admin,

    ADD COLUMN IF NOT EXISTS availability_locked_at DATETIME NULL
        COMMENT 'UTC timestamp when admin lock was applied'
        AFTER availability_locked_note,

    ADD COLUMN IF NOT EXISTS availability_locked_by_user_id BIGINT NULL
        COMMENT 'Admin user_id who applied the lock'
        AFTER availability_locked_at,

    ADD COLUMN IF NOT EXISTS availability_auto_restored_at DATETIME NULL
        COMMENT 'UTC timestamp when availability was last auto-restored after a visit'
        AFTER availability_locked_by_user_id,

    ADD COLUMN IF NOT EXISTS availability_changed_at DATETIME NULL
        COMMENT 'UTC timestamp of last availability state change'
        AFTER availability_auto_restored_at,

    ADD COLUMN IF NOT EXISTS availability_changed_by ENUM(
        'caretaker',
        'system',
        'admin'
    ) NOT NULL DEFAULT 'caretaker'
        COMMENT 'Actor who last changed availability'
        AFTER availability_changed_at,

    ADD COLUMN IF NOT EXISTS availability_version INT NOT NULL DEFAULT 1
        COMMENT 'Optimistic locking version; incremented on every availability change'
        AFTER availability_changed_by;

-- -----------------------------------------------------------
-- 2. Add indexes for query performance
-- -----------------------------------------------------------

-- idx_caretaker_is_available already exists from prior migration
-- Add new ones only if not present

ALTER TABLE caretaker_profiles
    ADD INDEX IF NOT EXISTS idx_caretaker_availability_reason (availability_reason),
    ADD INDEX IF NOT EXISTS idx_caretaker_last_active_at (last_active_at),
    ADD INDEX IF NOT EXISTS idx_caretaker_admin_locked (availability_locked_by_admin),
    ADD INDEX IF NOT EXISTS idx_caretaker_verification_status (verification_status);

-- -----------------------------------------------------------
-- 3. Backfill existing rows with safe defaults
-- -----------------------------------------------------------

-- Caretakers currently marked available should have manual_availability_enabled = 1
UPDATE caretaker_profiles
SET manual_availability_enabled = 1,
    availability_reason = 'manual_on',
    availability_changed_at = COALESCE(availability_updated_at, NOW()),
    availability_changed_by = 'caretaker'
WHERE is_available = 1;

-- Caretakers currently unavailable keep defaults (manual_availability_enabled = 0, reason = manual_off)
UPDATE caretaker_profiles
SET availability_changed_at = COALESCE(availability_updated_at, NOW()),
    availability_changed_by = 'caretaker'
WHERE is_available = 0
  AND availability_changed_at IS NULL;

-- Rejected caretakers get proper reason
UPDATE caretaker_profiles
SET availability_reason = 'rejected'
WHERE verification_status = 'rejected'
  AND is_available = 0;

-- Pending caretakers get proper reason
UPDATE caretaker_profiles
SET availability_reason = 'pending_review'
WHERE verification_status = 'pending'
  AND is_available = 0;

-- Inactive users get proper reason
UPDATE caretaker_profiles cp
INNER JOIN users u ON u.id = cp.user_id
SET cp.availability_reason = 'inactive'
WHERE u.is_active = 0
  AND cp.is_available = 0;

-- Caretakers with active visits get on_visit reason
UPDATE caretaker_profiles cp
SET cp.availability_reason = 'on_visit',
    cp.is_available = 0,
    cp.manual_availability_enabled = 1
WHERE EXISTS (
    SELECT 1 FROM visit_tracking vt
    INNER JOIN bookings b ON b.id = vt.booking_id
    WHERE vt.caretaker_user_id = cp.user_id
      AND vt.check_out_time IS NULL
      AND b.status = 'ongoing'
);
