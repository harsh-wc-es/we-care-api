-- Internal caretaker platform feedback and suggestions.

CREATE TABLE IF NOT EXISTS caretaker_feedback (
    id INT NOT NULL AUTO_INCREMENT,
    caretaker_user_id INT NOT NULL,
    rating TINYINT NOT NULL,
    feedback TEXT NULL,
    suggestion TEXT NULL,
    is_anonymous TINYINT(1) NOT NULL DEFAULT 0,
    status ENUM('pending','reviewed','archived') NOT NULL DEFAULT 'pending',
    admin_note TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    reviewed_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY idx_caretaker_feedback_user (caretaker_user_id),
    KEY idx_caretaker_feedback_rating (rating),
    KEY idx_caretaker_feedback_status (status),
    KEY idx_caretaker_feedback_created_at (created_at),
    CONSTRAINT fk_caretaker_feedback_user
        FOREIGN KEY (caretaker_user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
