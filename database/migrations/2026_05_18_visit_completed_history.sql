-- Visit completed/history support for caretaker Flutter screens.
-- Adds stored care points so completion rewards are persisted server-side.

SET @column_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'bookings'
      AND COLUMN_NAME = 'care_points_earned'
);

SET @sql := IF(
    @column_exists = 0,
    'ALTER TABLE bookings ADD COLUMN care_points_earned INT NOT NULL DEFAULT 0 AFTER platform_commission_amount',
    'SELECT 1'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE bookings
SET care_points_earned = 20
WHERE status = 'completed'
  AND care_points_earned = 0;
