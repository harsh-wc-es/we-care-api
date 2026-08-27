ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS completed_at datetime NULL AFTER updated_at,
    ADD COLUMN IF NOT EXISTS payout_status enum('not_applicable','hold','ready_for_payout','disputed','paid') NOT NULL DEFAULT 'not_applicable' AFTER completed_at,
    ADD COLUMN IF NOT EXISTS payout_hold_until datetime NULL AFTER payout_status,
    ADD COLUMN IF NOT EXISTS payout_paid_at datetime NULL AFTER payout_hold_until,
    ADD COLUMN IF NOT EXISTS payout_id int(11) NULL AFTER payout_paid_at,
    ADD INDEX IF NOT EXISTS idx_booking_payout_status (payout_status),
    ADD INDEX IF NOT EXISTS idx_booking_payout_hold_until (payout_hold_until),
    ADD INDEX IF NOT EXISTS idx_booking_completed_at (completed_at),
    ADD INDEX IF NOT EXISTS idx_booking_payout_id (payout_id);

ALTER TABLE caretaker_payouts
    ADD COLUMN IF NOT EXISTS week_start date NULL AFTER amount,
    ADD COLUMN IF NOT EXISTS week_end date NULL AFTER week_start,
    ADD COLUMN IF NOT EXISTS payment_method varchar(50) NULL AFTER status,
    ADD COLUMN IF NOT EXISTS transaction_reference varchar(255) NULL AFTER payment_method,
    ADD INDEX IF NOT EXISTS idx_payout_week (week_start, week_end);

CREATE TABLE IF NOT EXISTS caretaker_payout_items (
    id int(11) NOT NULL AUTO_INCREMENT,
    payout_id int(11) NOT NULL,
    booking_id int(11) NOT NULL,
    caretaker_user_id int(11) NOT NULL,
    amount decimal(10,2) NOT NULL DEFAULT 0.00,
    created_at datetime DEFAULT current_timestamp(),
    PRIMARY KEY (id),
    UNIQUE KEY uniq_payout_booking (booking_id),
    KEY idx_payout_items_payout (payout_id),
    KEY idx_payout_items_caretaker (caretaker_user_id),
    CONSTRAINT fk_payout_items_payout FOREIGN KEY (payout_id) REFERENCES caretaker_payouts(id) ON DELETE CASCADE,
    CONSTRAINT fk_payout_items_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    CONSTRAINT fk_payout_items_caretaker FOREIGN KEY (caretaker_user_id) REFERENCES users(id) ON DELETE CASCADE
);

UPDATE bookings
SET completed_at = COALESCE(completed_at, updated_at, created_at),
    payout_status = CASE
        WHEN payout_status = 'paid' THEN 'paid'
        WHEN status = 'completed' THEN 'hold'
        ELSE 'not_applicable'
    END,
    payout_hold_until = CASE
        WHEN status = 'completed' AND payout_hold_until IS NULL
        THEN DATE_ADD(COALESCE(completed_at, updated_at, created_at), INTERVAL 24 HOUR)
        ELSE payout_hold_until
    END
WHERE status = 'completed' OR payout_status <> 'not_applicable';
