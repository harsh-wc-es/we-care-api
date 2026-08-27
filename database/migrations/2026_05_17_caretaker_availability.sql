ALTER TABLE caretaker_profiles
    ADD COLUMN IF NOT EXISTS is_available tinyint(1) NOT NULL DEFAULT 0 AFTER verification_status,
    ADD COLUMN IF NOT EXISTS availability_updated_at datetime NULL AFTER is_available,
    ADD COLUMN IF NOT EXISTS last_active_at datetime NULL AFTER availability_updated_at,
    ADD INDEX IF NOT EXISTS idx_caretaker_is_available (is_available),
    ADD INDEX IF NOT EXISTS idx_caretaker_availability_updated_at (availability_updated_at);

UPDATE caretaker_profiles cp
INNER JOIN users u ON u.id = cp.user_id
SET cp.is_available = 0
WHERE u.is_active = 0
   OR cp.verification_status <> 'approved';
