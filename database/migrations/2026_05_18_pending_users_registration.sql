CREATE TABLE IF NOT EXISTS pending_users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NULL,
    username VARCHAR(30) NOT NULL,
    email VARCHAR(191) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('family','caretaker','admin') NOT NULL,
    registration_payload JSON NULL,
    otp_verified_at DATETIME NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_pending_users_username (username),
    UNIQUE KEY uq_pending_users_email (email),
    UNIQUE KEY uq_pending_users_phone (phone_number),
    KEY idx_pending_users_expires_at (expires_at),
    KEY idx_pending_users_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE otp_codes
    ADD COLUMN pending_user_id BIGINT UNSIGNED NULL AFTER user_id,
    ADD KEY idx_otp_codes_pending_user (pending_user_id),
    ADD CONSTRAINT fk_otp_codes_pending_user
        FOREIGN KEY (pending_user_id) REFERENCES pending_users(id)
        ON DELETE CASCADE;

INSERT IGNORE INTO pending_users
    (full_name, username, email, phone_number, password_hash, role, registration_payload, expires_at, created_at, updated_at)
SELECT
    COALESCE(fp.full_name, cp.full_name),
    LOWER(TRIM(u.username)),
    LOWER(TRIM(u.email)),
    u.phone_number,
    u.password,
    u.role,
    JSON_OBJECT('migrated_from_users_id', u.id, 'legacy_unverified', true),
    DATE_ADD(NOW(), INTERVAL 30 MINUTE),
    u.created_at,
    NOW()
FROM users u
LEFT JOIN family_profiles fp ON fp.user_id = u.id
LEFT JOIN caretaker_profiles cp ON cp.user_id = u.id
WHERE u.is_verified <> 1
  AND u.role IN ('family','caretaker')
  AND NOT EXISTS (
      SELECT 1 FROM bookings b
      WHERE b.family_user_id = u.id OR b.caretaker_user_id = u.id
  );

DELETE t
FROM tokens t
INNER JOIN users u ON u.id = t.user_id
WHERE u.is_verified <> 1
  AND u.role IN ('family','caretaker')
  AND NOT EXISTS (
      SELECT 1 FROM bookings b
      WHERE b.family_user_id = u.id OR b.caretaker_user_id = u.id
  );

DELETE fp
FROM family_profiles fp
INNER JOIN users u ON u.id = fp.user_id
WHERE u.is_verified <> 1
  AND u.role = 'family'
  AND NOT EXISTS (
      SELECT 1 FROM bookings b
      WHERE b.family_user_id = u.id OR b.caretaker_user_id = u.id
  );

DELETE cp
FROM caretaker_profiles cp
INNER JOIN users u ON u.id = cp.user_id
WHERE u.is_verified <> 1
  AND u.role = 'caretaker'
  AND NOT EXISTS (
      SELECT 1 FROM bookings b
      WHERE b.family_user_id = u.id OR b.caretaker_user_id = u.id
  );

DELETE u
FROM users u
WHERE u.is_verified <> 1
  AND u.role IN ('family','caretaker')
  AND NOT EXISTS (
      SELECT 1 FROM bookings b
      WHERE b.family_user_id = u.id OR b.caretaker_user_id = u.id
  );

DELETE u
FROM users u
WHERE u.is_verified <> 1
  AND (u.role IS NULL OR u.role NOT IN ('family','caretaker','admin'))
  AND NOT EXISTS (
      SELECT 1 FROM bookings b
      WHERE b.family_user_id = u.id OR b.caretaker_user_id = u.id
  );
