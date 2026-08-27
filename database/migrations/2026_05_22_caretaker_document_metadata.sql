-- Preserve original caretaker document names for admin/caretaker display.
-- Additive only: existing file rows and stored paths remain unchanged.

SET @caretaker_document_original_name_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'documents'
      AND COLUMN_NAME = 'original_file_name'
);
SET @caretaker_document_original_name_sql := IF(
    @caretaker_document_original_name_exists = 0,
    'ALTER TABLE documents ADD COLUMN original_file_name VARCHAR(255) NULL AFTER file_path',
    'SELECT ''documents.original_file_name already exists'' AS migration_notice'
);
PREPARE caretaker_document_original_name_stmt FROM @caretaker_document_original_name_sql;
EXECUTE caretaker_document_original_name_stmt;
DEALLOCATE PREPARE caretaker_document_original_name_stmt;
