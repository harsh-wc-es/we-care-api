CREATE TABLE IF NOT EXISTS otp_codes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    booking_id INT NULL,
    email VARCHAR(150) NULL,
    purpose ENUM('register_email','login','password_reset','visit_start') NOT NULL,
    otp_hash VARCHAR(255) NOT NULL,
    expires_at DATETIME NOT NULL,
    resend_available_at DATETIME NULL,
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    used_at DATETIME NULL,
    metadata TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_otp_user_purpose (user_id, purpose),
    INDEX idx_otp_booking_purpose (booking_id, purpose),
    INDEX idx_otp_email_purpose (email, purpose),
    INDEX idx_otp_expires_at (expires_at),
    CONSTRAINT fk_otp_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_otp_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rate_limits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rate_key VARCHAR(190) NOT NULL,
    action VARCHAR(80) NOT NULL,
    attempts INT NOT NULL DEFAULT 1,
    window_start DATETIME NOT NULL,
    blocked_until DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_rate_key_action (rate_key, action),
    INDEX idx_rate_blocked_until (blocked_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS booking_checklist_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    family_user_id INT NOT NULL,
    caretaker_user_id INT NULL,
    title VARCHAR(150) NOT NULL,
    description TEXT NULL,
    status ENUM('pending','done') NOT NULL DEFAULT 'pending',
    completed_by INT NULL,
    completed_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tasks_booking (booking_id),
    INDEX idx_tasks_family (family_user_id),
    INDEX idx_tasks_caretaker (caretaker_user_id),
    CONSTRAINT fk_tasks_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    CONSTRAINT fk_tasks_family FOREIGN KEY (family_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_tasks_caretaker FOREIGN KEY (caretaker_user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_tasks_completed_by FOREIGN KEY (completed_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS complaints (
    id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    family_user_id INT NOT NULL,
    caretaker_user_id INT NULL,
    subject VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    proof_file VARCHAR(255) NULL,
    status ENUM('open','in_review','resolved','rejected') NOT NULL DEFAULT 'open',
    admin_note TEXT NULL,
    resolved_by INT NULL,
    resolved_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_complaints_booking (booking_id),
    INDEX idx_complaints_family (family_user_id),
    INDEX idx_complaints_status (status),
    CONSTRAINT fk_complaints_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    CONSTRAINT fk_complaints_family FOREIGN KEY (family_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_complaints_caretaker FOREIGN KEY (caretaker_user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_complaints_resolved_by FOREIGN KEY (resolved_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS replacement_tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    complaint_id INT NULL,
    booking_id INT NOT NULL,
    family_user_id INT NOT NULL,
    original_caretaker_user_id INT NULL,
    replacement_caretaker_user_id INT NULL,
    reason TEXT NOT NULL,
    status ENUM('open','assigned','resolved','cancelled') NOT NULL DEFAULT 'open',
    admin_note TEXT NULL,
    resolved_by INT NULL,
    resolved_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_replacements_complaint (complaint_id),
    INDEX idx_replacements_booking (booking_id),
    INDEX idx_replacements_status (status),
    CONSTRAINT fk_replacements_complaint FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE SET NULL,
    CONSTRAINT fk_replacements_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    CONSTRAINT fk_replacements_family FOREIGN KEY (family_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_replacements_original FOREIGN KEY (original_caretaker_user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_replacements_new FOREIGN KEY (replacement_caretaker_user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_replacements_resolved_by FOREIGN KEY (resolved_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_user_id INT NULL,
    action VARCHAR(120) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    entity_id INT NULL,
    old_values TEXT NULL,
    new_values TEXT NULL,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(255) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_admin (admin_user_id),
    INDEX idx_audit_entity (entity_type, entity_id),
    INDEX idx_audit_created_at (created_at),
    CONSTRAINT fk_audit_admin FOREIGN KEY (admin_user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS caretaker_payouts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    caretaker_user_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    status ENUM('pending','processing','paid','failed') NOT NULL DEFAULT 'pending',
    payment_reference VARCHAR(255) NULL,
    admin_note TEXT NULL,
    settled_by INT NULL,
    settled_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_payout_caretaker (caretaker_user_id),
    INDEX idx_payout_status (status),
    CONSTRAINT fk_payout_caretaker FOREIGN KEY (caretaker_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_payout_settled_by FOREIGN KEY (settled_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
