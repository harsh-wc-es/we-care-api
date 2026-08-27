-- Migration audit repair pack for confirmed current DB drift.
-- Safe scope: no drops, no truncates, no data deletion.
-- Covers migration intent that exists in older migration files but is not present
-- in the configured database inspected on 2026-05-22.

-- documents.created_at is required by the hardened bulk document upload API.
SET @audit_documents_created_at_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'documents'
      AND COLUMN_NAME = 'created_at'
);
SET @audit_documents_created_at_sql := IF(
    @audit_documents_created_at_exists = 0,
    'ALTER TABLE documents ADD COLUMN created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP AFTER admin_note',
    'SELECT ''documents.created_at already exists'' AS migration_notice'
);
PREPARE audit_documents_created_at_stmt FROM @audit_documents_created_at_sql;
EXECUTE audit_documents_created_at_stmt;
DEALLOCATE PREPARE audit_documents_created_at_stmt;
UPDATE documents
SET created_at = COALESCE(created_at, uploaded_at, NOW())
WHERE created_at IS NULL;

-- Authenticated reset OTP code purpose used by request_password_reset_otp.
ALTER TABLE otp_codes
    MODIFY COLUMN purpose ENUM(
        'register_email',
        'login',
        'password_reset',
        'visit_start',
        'password_reset_authenticated'
    ) NOT NULL;

-- Payment methods are validated in payment_service and must match storage.
UPDATE payments
SET payment_method = 'other'
WHERE payment_method = 'online';
ALTER TABLE payments
    MODIFY COLUMN payment_method ENUM(
        'card',
        'upi',
        'netbanking',
        'wallet',
        'cash',
        'insurance',
        'other'
    ) NOT NULL DEFAULT 'cash';

-- Future payment gateway verification fields are already read/written by pay APIs.
SET @audit_payment_gateway_ref_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payments'
      AND COLUMN_NAME = 'gateway_transaction_reference'
);
SET @audit_payment_gateway_ref_sql := IF(
    @audit_payment_gateway_ref_exists = 0,
    'ALTER TABLE payments ADD COLUMN gateway_transaction_reference VARCHAR(255) NULL AFTER transaction_id',
    'SELECT ''payments.gateway_transaction_reference already exists'' AS migration_notice'
);
PREPARE audit_payment_gateway_ref_stmt FROM @audit_payment_gateway_ref_sql;
EXECUTE audit_payment_gateway_ref_stmt;
DEALLOCATE PREPARE audit_payment_gateway_ref_stmt;

SET @audit_payment_gateway_json_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payments'
      AND COLUMN_NAME = 'gateway_response_json'
);
SET @audit_payment_gateway_json_sql := IF(
    @audit_payment_gateway_json_exists = 0,
    'ALTER TABLE payments ADD COLUMN gateway_response_json LONGTEXT NULL AFTER gateway_transaction_reference',
    'SELECT ''payments.gateway_response_json already exists'' AS migration_notice'
);
PREPARE audit_payment_gateway_json_stmt FROM @audit_payment_gateway_json_sql;
EXECUTE audit_payment_gateway_json_stmt;
DEALLOCATE PREPARE audit_payment_gateway_json_stmt;

SET @audit_payment_verification_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payments'
      AND COLUMN_NAME = 'verification_status'
);
SET @audit_payment_verification_sql := IF(
    @audit_payment_verification_exists = 0,
    'ALTER TABLE payments ADD COLUMN verification_status ENUM(''not_required'',''pending'',''verified'',''failed'') NOT NULL DEFAULT ''pending'' AFTER status',
    'SELECT ''payments.verification_status already exists'' AS migration_notice'
);
PREPARE audit_payment_verification_stmt FROM @audit_payment_verification_sql;
EXECUTE audit_payment_verification_stmt;
DEALLOCATE PREPARE audit_payment_verification_stmt;

SET @audit_payment_verified_at_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payments'
      AND COLUMN_NAME = 'verified_at'
);
SET @audit_payment_verified_at_sql := IF(
    @audit_payment_verified_at_exists = 0,
    'ALTER TABLE payments ADD COLUMN verified_at DATETIME NULL AFTER paid_at',
    'SELECT ''payments.verified_at already exists'' AS migration_notice'
);
PREPARE audit_payment_verified_at_stmt FROM @audit_payment_verified_at_sql;
EXECUTE audit_payment_verified_at_stmt;
DEALLOCATE PREPARE audit_payment_verified_at_stmt;

SET @audit_payment_failure_reason_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payments'
      AND COLUMN_NAME = 'failure_reason'
);
SET @audit_payment_failure_reason_sql := IF(
    @audit_payment_failure_reason_exists = 0,
    'ALTER TABLE payments ADD COLUMN failure_reason VARCHAR(255) NULL AFTER verified_at',
    'SELECT ''payments.failure_reason already exists'' AS migration_notice'
);
PREPARE audit_payment_failure_reason_stmt FROM @audit_payment_failure_reason_sql;
EXECUTE audit_payment_failure_reason_stmt;
DEALLOCATE PREPARE audit_payment_failure_reason_stmt;

SET @audit_payment_idempotency_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payments'
      AND COLUMN_NAME = 'idempotency_key'
);
SET @audit_payment_idempotency_sql := IF(
    @audit_payment_idempotency_exists = 0,
    'ALTER TABLE payments ADD COLUMN idempotency_key VARCHAR(191) NULL AFTER failure_reason',
    'SELECT ''payments.idempotency_key already exists'' AS migration_notice'
);
PREPARE audit_payment_idempotency_stmt FROM @audit_payment_idempotency_sql;
EXECUTE audit_payment_idempotency_stmt;
DEALLOCATE PREPARE audit_payment_idempotency_stmt;

-- Index guards for idempotent payment duplicate protection and admin filters.
SET @audit_payment_idempotency_index_exists := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payments'
      AND INDEX_NAME = 'uq_payments_idempotency_key'
);
SET @audit_payment_idempotency_index_sql := IF(
    @audit_payment_idempotency_index_exists = 0,
    'ALTER TABLE payments ADD UNIQUE KEY uq_payments_idempotency_key (idempotency_key)',
    'SELECT ''uq_payments_idempotency_key already exists'' AS migration_notice'
);
PREPARE audit_payment_idempotency_index_stmt FROM @audit_payment_idempotency_index_sql;
EXECUTE audit_payment_idempotency_index_stmt;
DEALLOCATE PREPARE audit_payment_idempotency_index_stmt;

SET @audit_payment_verification_index_exists := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payments'
      AND INDEX_NAME = 'idx_payments_verification_status'
);
SET @audit_payment_verification_index_sql := IF(
    @audit_payment_verification_index_exists = 0,
    'ALTER TABLE payments ADD KEY idx_payments_verification_status (verification_status)',
    'SELECT ''idx_payments_verification_status already exists'' AS migration_notice'
);
PREPARE audit_payment_verification_index_stmt FROM @audit_payment_verification_index_sql;
EXECUTE audit_payment_verification_index_stmt;
DEALLOCATE PREPARE audit_payment_verification_index_stmt;

SET @audit_payment_gateway_index_exists := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payments'
      AND INDEX_NAME = 'idx_payments_gateway_reference'
);
SET @audit_payment_gateway_index_sql := IF(
    @audit_payment_gateway_index_exists = 0,
    'ALTER TABLE payments ADD KEY idx_payments_gateway_reference (gateway_transaction_reference)',
    'SELECT ''idx_payments_gateway_reference already exists'' AS migration_notice'
);
PREPARE audit_payment_gateway_index_stmt FROM @audit_payment_gateway_index_sql;
EXECUTE audit_payment_gateway_index_stmt;
DEALLOCATE PREPARE audit_payment_gateway_index_stmt;
