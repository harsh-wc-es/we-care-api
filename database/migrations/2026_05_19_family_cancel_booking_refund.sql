-- Family-side booking cancellation and refund metadata.
-- Safe additive migration: no existing booking data is dropped.

ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS cancelled_by_user_id INT NULL AFTER cancelled_at,
    ADD COLUMN IF NOT EXISTS cancelled_by_role VARCHAR(30) NULL AFTER cancelled_by_user_id,
    ADD COLUMN IF NOT EXISTS cancel_reason_code VARCHAR(50) NULL AFTER cancelled_by_role,
    ADD COLUMN IF NOT EXISTS cancel_reason_label VARCHAR(100) NULL AFTER cancel_reason_code,
    ADD COLUMN IF NOT EXISTS cancel_note TEXT NULL AFTER cancel_reason_label,
    ADD COLUMN IF NOT EXISTS refund_percentage DECIMAL(5,2) NOT NULL DEFAULT 0 AFTER cancel_note,
    ADD COLUMN IF NOT EXISTS refund_amount DECIMAL(10,2) NOT NULL DEFAULT 0 AFTER refund_percentage,
    ADD COLUMN IF NOT EXISTS cancellation_fee DECIMAL(10,2) NOT NULL DEFAULT 0 AFTER refund_amount,
    ADD COLUMN IF NOT EXISTS refund_status ENUM('not_applicable','pending','processed','failed') NOT NULL DEFAULT 'not_applicable' AFTER cancellation_fee,
    ADD COLUMN IF NOT EXISTS refund_eligible TINYINT(1) NOT NULL DEFAULT 0 AFTER refund_status,
    ADD INDEX IF NOT EXISTS idx_bookings_cancel_reason_code (cancel_reason_code),
    ADD INDEX IF NOT EXISTS idx_bookings_refund_status (refund_status),
    ADD INDEX IF NOT EXISTS idx_bookings_cancelled_by_user (cancelled_by_user_id);
