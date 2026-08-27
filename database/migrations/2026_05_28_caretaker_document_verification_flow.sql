-- Caretaker document verification, approval, resubmission, and ban flow.
-- Safe migration: schema changes only, no data deletion.

ALTER TABLE caretaker_profiles
    MODIFY COLUMN verification_status ENUM('pending','pending_review','approved','rejected','needs_resubmission','banned') DEFAULT 'pending';

ALTER TABLE documents
    MODIFY COLUMN status ENUM('uploaded','pending','approved','rejected','reuploaded') DEFAULT 'uploaded';

SET @cp_is_banned_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'caretaker_profiles' AND COLUMN_NAME = 'is_banned'
);
SET @cp_is_banned_sql := IF(@cp_is_banned_exists = 0,
    'ALTER TABLE caretaker_profiles ADD COLUMN is_banned TINYINT(1) NOT NULL DEFAULT 0 AFTER verification_status',
    'SELECT ''caretaker_profiles.is_banned already exists'' AS migration_notice'
);
PREPARE cp_is_banned_stmt FROM @cp_is_banned_sql;
EXECUTE cp_is_banned_stmt;
DEALLOCATE PREPARE cp_is_banned_stmt;

SET @cp_ban_reason_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'caretaker_profiles' AND COLUMN_NAME = 'ban_reason'
);
SET @cp_ban_reason_sql := IF(@cp_ban_reason_exists = 0,
    'ALTER TABLE caretaker_profiles ADD COLUMN ban_reason TEXT NULL AFTER rejection_reason',
    'SELECT ''caretaker_profiles.ban_reason already exists'' AS migration_notice'
);
PREPARE cp_ban_reason_stmt FROM @cp_ban_reason_sql;
EXECUTE cp_ban_reason_stmt;
DEALLOCATE PREPARE cp_ban_reason_stmt;

SET @cp_banned_at_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'caretaker_profiles' AND COLUMN_NAME = 'banned_at'
);
SET @cp_banned_at_sql := IF(@cp_banned_at_exists = 0,
    'ALTER TABLE caretaker_profiles ADD COLUMN banned_at DATETIME NULL AFTER ban_reason',
    'SELECT ''caretaker_profiles.banned_at already exists'' AS migration_notice'
);
PREPARE cp_banned_at_stmt FROM @cp_banned_at_sql;
EXECUTE cp_banned_at_stmt;
DEALLOCATE PREPARE cp_banned_at_stmt;

SET @cp_banned_by_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'caretaker_profiles' AND COLUMN_NAME = 'banned_by_admin_id'
);
SET @cp_banned_by_sql := IF(@cp_banned_by_exists = 0,
    'ALTER TABLE caretaker_profiles ADD COLUMN banned_by_admin_id INT NULL AFTER banned_at',
    'SELECT ''caretaker_profiles.banned_by_admin_id already exists'' AS migration_notice'
);
PREPARE cp_banned_by_stmt FROM @cp_banned_by_sql;
EXECUTE cp_banned_by_stmt;
DEALLOCATE PREPARE cp_banned_by_stmt;

SET @cp_approved_at_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'caretaker_profiles' AND COLUMN_NAME = 'approved_at'
);
SET @cp_approved_at_sql := IF(@cp_approved_at_exists = 0,
    'ALTER TABLE caretaker_profiles ADD COLUMN approved_at DATETIME NULL AFTER banned_by_admin_id',
    'SELECT ''caretaker_profiles.approved_at already exists'' AS migration_notice'
);
PREPARE cp_approved_at_stmt FROM @cp_approved_at_sql;
EXECUTE cp_approved_at_stmt;
DEALLOCATE PREPARE cp_approved_at_stmt;

SET @cp_approved_by_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'caretaker_profiles' AND COLUMN_NAME = 'approved_by_admin_id'
);
SET @cp_approved_by_sql := IF(@cp_approved_by_exists = 0,
    'ALTER TABLE caretaker_profiles ADD COLUMN approved_by_admin_id INT NULL AFTER approved_at',
    'SELECT ''caretaker_profiles.approved_by_admin_id already exists'' AS migration_notice'
);
PREPARE cp_approved_by_stmt FROM @cp_approved_by_sql;
EXECUTE cp_approved_by_stmt;
DEALLOCATE PREPARE cp_approved_by_stmt;

SET @doc_rejection_reason_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documents' AND COLUMN_NAME = 'rejection_reason'
);
SET @doc_rejection_reason_sql := IF(@doc_rejection_reason_exists = 0,
    'ALTER TABLE documents ADD COLUMN rejection_reason TEXT NULL AFTER admin_note',
    'SELECT ''documents.rejection_reason already exists'' AS migration_notice'
);
PREPARE doc_rejection_reason_stmt FROM @doc_rejection_reason_sql;
EXECUTE doc_rejection_reason_stmt;
DEALLOCATE PREPARE doc_rejection_reason_stmt;

SET @doc_reviewed_by_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documents' AND COLUMN_NAME = 'reviewed_by_admin_id'
);
SET @doc_reviewed_by_sql := IF(@doc_reviewed_by_exists = 0,
    'ALTER TABLE documents ADD COLUMN reviewed_by_admin_id INT NULL AFTER rejection_reason',
    'SELECT ''documents.reviewed_by_admin_id already exists'' AS migration_notice'
);
PREPARE doc_reviewed_by_stmt FROM @doc_reviewed_by_sql;
EXECUTE doc_reviewed_by_stmt;
DEALLOCATE PREPARE doc_reviewed_by_stmt;

SET @doc_reviewed_at_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documents' AND COLUMN_NAME = 'reviewed_at'
);
SET @doc_reviewed_at_sql := IF(@doc_reviewed_at_exists = 0,
    'ALTER TABLE documents ADD COLUMN reviewed_at DATETIME NULL AFTER reviewed_by_admin_id',
    'SELECT ''documents.reviewed_at already exists'' AS migration_notice'
);
PREPARE doc_reviewed_at_stmt FROM @doc_reviewed_at_sql;
EXECUTE doc_reviewed_at_stmt;
DEALLOCATE PREPARE doc_reviewed_at_stmt;

