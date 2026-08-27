ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS cancelled_by varchar(30) NULL AFTER status,
    ADD COLUMN IF NOT EXISTS cancellation_reason text NULL AFTER cancelled_by,
    ADD COLUMN IF NOT EXISTS cancelled_at datetime NULL AFTER cancellation_reason,
    ADD INDEX IF NOT EXISTS idx_booking_cancelled_at (cancelled_at);
