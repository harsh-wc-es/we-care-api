-- Payment verification preparation and payment method normalization.
-- Keeps current mock-success flow working while preparing for Razorpay/Stripe/webhook verification.

UPDATE payments
SET payment_method = 'other'
WHERE payment_method = 'online';

ALTER TABLE payments
    MODIFY payment_method enum('card','upi','netbanking','wallet','cash','insurance','other') NOT NULL DEFAULT 'cash',
    ADD COLUMN IF NOT EXISTS gateway_transaction_reference varchar(255) DEFAULT NULL AFTER transaction_id,
    ADD COLUMN IF NOT EXISTS gateway_response_json longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`gateway_response_json`)) AFTER gateway_transaction_reference,
    ADD COLUMN IF NOT EXISTS verification_status enum('not_required','pending','verified','failed') NOT NULL DEFAULT 'pending' AFTER status,
    ADD COLUMN IF NOT EXISTS verified_at datetime DEFAULT NULL AFTER paid_at,
    ADD COLUMN IF NOT EXISTS failure_reason varchar(255) DEFAULT NULL AFTER verified_at,
    ADD COLUMN IF NOT EXISTS idempotency_key varchar(191) DEFAULT NULL AFTER failure_reason,
    ADD UNIQUE KEY IF NOT EXISTS uq_payments_idempotency_key (`idempotency_key`),
    ADD KEY IF NOT EXISTS idx_payments_verification_status (`verification_status`),
    ADD KEY IF NOT EXISTS idx_payments_gateway_reference (`gateway_transaction_reference`);
