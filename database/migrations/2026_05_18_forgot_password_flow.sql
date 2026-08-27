CREATE TABLE IF NOT EXISTS otp_verifications (
    id INT(11) NOT NULL AUTO_INCREMENT,
    user_id INT(11) DEFAULT NULL,
    login_identifier VARCHAR(190) NOT NULL,
    purpose ENUM('forgot_password') NOT NULL,
    otp_hash VARCHAR(255) NOT NULL,
    attempts INT(11) NOT NULL DEFAULT 0,
    max_attempts INT(11) NOT NULL DEFAULT 5,
    expires_at DATETIME NOT NULL,
    resend_available_at DATETIME DEFAULT NULL,
    verified_at DATETIME DEFAULT NULL,
    used_at DATETIME DEFAULT NULL,
    ip_address VARCHAR(45) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_otp_verifications_user (user_id),
    KEY idx_otp_verifications_login_purpose (login_identifier, purpose),
    KEY idx_otp_verifications_expires_at (expires_at),
    CONSTRAINT fk_otp_verifications_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INT(11) NOT NULL AUTO_INCREMENT,
    user_id INT(11) NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    expires_at DATETIME NOT NULL,
    used_at DATETIME DEFAULT NULL,
    ip_address VARCHAR(45) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_password_reset_user (user_id),
    KEY idx_password_reset_expires_at (expires_at),
    CONSTRAINT fk_password_reset_tokens_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
