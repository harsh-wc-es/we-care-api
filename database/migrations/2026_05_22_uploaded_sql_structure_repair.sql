-- Uploaded SQL structure repair for we1c554167_we_care.sql audit on 2026-05-22.
-- Scope: safe additive or widening repairs only.
-- No table drops, truncation, row deletion, or production data application is performed here.

-- Bulk caretaker upload writes status='uploaded'.
-- Keep all existing document status values while widening the dump enum.
SET @uploaded_sql_documents_status_supports_uploaded := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'documents'
      AND COLUMN_NAME = 'status'
      AND COLUMN_TYPE LIKE '%uploaded%'
);
SET @uploaded_sql_documents_status_sql := IF(
    @uploaded_sql_documents_status_supports_uploaded = 0,
    'ALTER TABLE documents MODIFY COLUMN status ENUM(''uploaded'',''pending'',''approved'',''rejected'') DEFAULT ''uploaded''',
    'SELECT ''documents.status already supports uploaded'' AS migration_notice'
);
PREPARE uploaded_sql_documents_status_stmt FROM @uploaded_sql_documents_status_sql;
EXECUTE uploaded_sql_documents_status_stmt;
DEALLOCATE PREPARE uploaded_sql_documents_status_stmt;

-- Bulk caretaker document reuploads require a stable updated_at column.
SET @uploaded_sql_documents_updated_at_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'documents'
      AND COLUMN_NAME = 'updated_at'
);
SET @uploaded_sql_documents_updated_at_sql := IF(
    @uploaded_sql_documents_updated_at_exists = 0,
    'ALTER TABLE documents ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER uploaded_at',
    'SELECT ''documents.updated_at already exists'' AS migration_notice'
);
PREPARE uploaded_sql_documents_updated_at_stmt FROM @uploaded_sql_documents_updated_at_sql;
EXECUTE uploaded_sql_documents_updated_at_stmt;
DEALLOCATE PREPARE uploaded_sql_documents_updated_at_stmt;

-- Current patient API allows one patient profile per family account.
-- Add DB protection only when existing imported data is already unique.
-- If duplicates exist, this migration leaves rows untouched and prints a notice.
SET @uploaded_sql_patient_family_unique_exists := (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'patient_details'
      AND INDEX_NAME = 'uq_patient_details_family_user_id'
);
SET @uploaded_sql_patient_family_duplicate_groups := (
    SELECT COUNT(*)
    FROM (
        SELECT family_user_id
        FROM patient_details
        GROUP BY family_user_id
        HAVING COUNT(*) > 1
    ) AS duplicate_patient_family_groups
);
SET @uploaded_sql_patient_family_unique_sql := IF(
    @uploaded_sql_patient_family_unique_exists > 0,
    'SELECT ''uq_patient_details_family_user_id already exists'' AS migration_notice',
    IF(
        @uploaded_sql_patient_family_duplicate_groups = 0,
        'ALTER TABLE patient_details ADD UNIQUE KEY uq_patient_details_family_user_id (family_user_id)',
        'SELECT ''patient_details duplicate family_user_id rows found; unique key skipped for manual review'' AS migration_notice'
    )
);
PREPARE uploaded_sql_patient_family_unique_stmt FROM @uploaded_sql_patient_family_unique_sql;
EXECUTE uploaded_sql_patient_family_unique_stmt;
DEALLOCATE PREPARE uploaded_sql_patient_family_unique_stmt;
