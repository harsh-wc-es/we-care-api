-- Ensures replacement ticket admin assignment fields exist on older databases.
-- Safe to run multiple times on MySQL/MariaDB through prepared conditional DDL.

SET @rt_requested_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'replacement_tickets'
      AND COLUMN_NAME = 'requested_by_user_id'
);
SET @rt_requested_sql := IF(
    @rt_requested_exists = 0,
    'ALTER TABLE replacement_tickets ADD COLUMN requested_by_user_id INT NULL AFTER family_user_id',
    'SELECT ''replacement_tickets.requested_by_user_id already exists'' AS migration_notice'
);
PREPARE rt_requested_stmt FROM @rt_requested_sql;
EXECUTE rt_requested_stmt;
DEALLOCATE PREPARE rt_requested_stmt;

SET @rt_original_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'replacement_tickets'
      AND COLUMN_NAME = 'original_caretaker_user_id'
);
SET @rt_original_sql := IF(
    @rt_original_exists = 0,
    'ALTER TABLE replacement_tickets ADD COLUMN original_caretaker_user_id INT NULL AFTER requested_by_user_id',
    'SELECT ''replacement_tickets.original_caretaker_user_id already exists'' AS migration_notice'
);
PREPARE rt_original_stmt FROM @rt_original_sql;
EXECUTE rt_original_stmt;
DEALLOCATE PREPARE rt_original_stmt;

SET @rt_replacement_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'replacement_tickets'
      AND COLUMN_NAME = 'replacement_caretaker_user_id'
);
SET @rt_replacement_sql := IF(
    @rt_replacement_exists = 0,
    'ALTER TABLE replacement_tickets ADD COLUMN replacement_caretaker_user_id INT NULL AFTER original_caretaker_user_id',
    'SELECT ''replacement_tickets.replacement_caretaker_user_id already exists'' AS migration_notice'
);
PREPARE rt_replacement_stmt FROM @rt_replacement_sql;
EXECUTE rt_replacement_stmt;
DEALLOCATE PREPARE rt_replacement_stmt;

SET @rt_admin_note_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'replacement_tickets'
      AND COLUMN_NAME = 'admin_note'
);
SET @rt_admin_note_sql := IF(
    @rt_admin_note_exists = 0,
    'ALTER TABLE replacement_tickets ADD COLUMN admin_note TEXT NULL AFTER status',
    'SELECT ''replacement_tickets.admin_note already exists'' AS migration_notice'
);
PREPARE rt_admin_note_stmt FROM @rt_admin_note_sql;
EXECUTE rt_admin_note_stmt;
DEALLOCATE PREPARE rt_admin_note_stmt;

SET @rt_updated_at_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'replacement_tickets'
      AND COLUMN_NAME = 'updated_at'
);
SET @rt_updated_at_sql := IF(
    @rt_updated_at_exists = 0,
    'ALTER TABLE replacement_tickets ADD COLUMN updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER created_at',
    'SELECT ''replacement_tickets.updated_at already exists'' AS migration_notice'
);
PREPARE rt_updated_at_stmt FROM @rt_updated_at_sql;
EXECUTE rt_updated_at_stmt;
DEALLOCATE PREPARE rt_updated_at_stmt;
