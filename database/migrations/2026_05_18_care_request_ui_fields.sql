ALTER TABLE bookings
    ADD COLUMN request_priority ENUM('normal','high','urgent') NOT NULL DEFAULT 'normal' AFTER notes,
    ADD COLUMN location_latitude DECIMAL(10,7) NULL AFTER address,
    ADD COLUMN location_longitude DECIMAL(10,7) NULL AFTER location_latitude,
    ADD COLUMN decline_reason_code VARCHAR(50) NULL AFTER cancellation_reason,
    ADD COLUMN decline_reason_label VARCHAR(120) NULL AFTER decline_reason_code,
    ADD COLUMN decline_note TEXT NULL AFTER decline_reason_label,
    ADD COLUMN responded_at DATETIME NULL AFTER decline_note,
    ADD INDEX idx_bookings_request_priority (request_priority),
    ADD INDEX idx_bookings_responded_at (responded_at);
