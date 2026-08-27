ALTER TABLE booking_checklist_tasks
    MODIFY status ENUM('pending','ongoing','completed','done') NOT NULL DEFAULT 'pending';

UPDATE booking_checklist_tasks
SET status = 'completed'
WHERE status = 'done';

ALTER TABLE booking_checklist_tasks
    MODIFY status ENUM('pending','ongoing','completed') NOT NULL DEFAULT 'pending';

CREATE TABLE IF NOT EXISTS visit_notes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    visit_id INT DEFAULT NULL,
    caretaker_user_id INT NOT NULL,
    note TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_visit_notes_booking (booking_id),
    KEY idx_visit_notes_visit (visit_id),
    KEY idx_visit_notes_caretaker (caretaker_user_id),
    CONSTRAINT fk_visit_notes_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    CONSTRAINT fk_visit_notes_visit FOREIGN KEY (visit_id) REFERENCES visit_tracking(id) ON DELETE SET NULL,
    CONSTRAINT fk_visit_notes_caretaker FOREIGN KEY (caretaker_user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS visit_activity_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    visit_id INT DEFAULT NULL,
    actor_user_id INT DEFAULT NULL,
    actor_role VARCHAR(30) NOT NULL,
    activity_type VARCHAR(60) NOT NULL,
    message VARCHAR(255) NOT NULL,
    metadata TEXT DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_visit_activity_booking (booking_id),
    KEY idx_visit_activity_visit (visit_id),
    KEY idx_visit_activity_actor (actor_user_id),
    KEY idx_visit_activity_type (activity_type),
    CONSTRAINT fk_visit_activity_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    CONSTRAINT fk_visit_activity_visit FOREIGN KEY (visit_id) REFERENCES visit_tracking(id) ON DELETE SET NULL,
    CONSTRAINT fk_visit_activity_actor FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
