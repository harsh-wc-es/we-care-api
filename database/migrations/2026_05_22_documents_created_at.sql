-- Keep caretaker verification document uploads compatible with schema checks.
-- Existing uploaded_at values are preserved as the best available creation time.

SET @documents_created_at_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'documents'
      AND COLUMN_NAME = 'created_at'
);

SET @documents_created_at_sql := IF(
    @documents_created_at_exists = 0,
    'ALTER TABLE documents ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP AFTER admin_note',
    'SELECT ''documents.created_at already exists'' AS migration_notice'
);

PREPARE documents_created_at_stmt FROM @documents_created_at_sql;
EXECUTE documents_created_at_stmt;
DEALLOCATE PREPARE documents_created_at_stmt;

UPDATE documents
SET created_at = COALESCE(created_at, uploaded_at, NOW())
WHERE created_at IS NULL;
