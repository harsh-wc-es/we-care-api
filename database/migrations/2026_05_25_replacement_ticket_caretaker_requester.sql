-- Adds an explicit requester column for caretaker-created replacement tickets.
-- Safe to run multiple times on MySQL/MariaDB through prepared conditional DDL.

SET @replacement_requested_by_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'replacement_tickets'
      AND COLUMN_NAME = 'requested_by_user_id'
);

SET @replacement_requested_by_sql := IF(
    @replacement_requested_by_exists = 0,
    'ALTER TABLE replacement_tickets ADD COLUMN requested_by_user_id INT NULL AFTER family_user_id',
    'SELECT ''replacement_tickets.requested_by_user_id already exists'' AS migration_notice'
);
PREPARE replacement_requested_by_stmt FROM @replacement_requested_by_sql;
EXECUTE replacement_requested_by_stmt;
DEALLOCATE PREPARE replacement_requested_by_stmt;

SET @replacement_requested_by_index_exists := (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'replacement_tickets'
      AND INDEX_NAME = 'fk_replacements_requested_by'
);

SET @replacement_requested_by_index_sql := IF(
    @replacement_requested_by_index_exists = 0,
    'ALTER TABLE replacement_tickets ADD INDEX fk_replacements_requested_by (requested_by_user_id)',
    'SELECT ''replacement_tickets.requested_by_user_id index already exists'' AS migration_notice'
);
PREPARE replacement_requested_by_index_stmt FROM @replacement_requested_by_index_sql;
EXECUTE replacement_requested_by_index_stmt;
DEALLOCATE PREPARE replacement_requested_by_index_stmt;

SET @replacement_requested_by_fk_exists := (
    SELECT COUNT(*)
    FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'replacement_tickets'
      AND CONSTRAINT_NAME = 'fk_replacements_requested_by'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);

SET @replacement_requested_by_fk_sql := IF(
    @replacement_requested_by_fk_exists = 0,
    'ALTER TABLE replacement_tickets ADD CONSTRAINT fk_replacements_requested_by FOREIGN KEY (requested_by_user_id) REFERENCES users(id) ON DELETE SET NULL',
    'SELECT ''replacement_tickets.requested_by_user_id foreign key already exists'' AS migration_notice'
);
PREPARE replacement_requested_by_fk_stmt FROM @replacement_requested_by_fk_sql;
EXECUTE replacement_requested_by_fk_stmt;
DEALLOCATE PREPARE replacement_requested_by_fk_stmt;
