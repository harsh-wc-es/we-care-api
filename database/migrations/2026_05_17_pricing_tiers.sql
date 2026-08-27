CREATE TABLE IF NOT EXISTS pricing_tiers (
    id bigint NOT NULL AUTO_INCREMENT,
    name varchar(100) NOT NULL,
    slug varchar(100) NOT NULL,
    description text NULL,
    skill_level varchar(30) NULL,
    customer_hourly_rate decimal(10,2) NOT NULL DEFAULT 0.00,
    caretaker_hourly_rate decimal(10,2) NOT NULL DEFAULT 0.00,
    platform_commission_hourly decimal(10,2) NOT NULL DEFAULT 0.00,
    commission_percentage decimal(5,2) NOT NULL DEFAULT 0.00,
    is_active tinyint(1) NOT NULL DEFAULT 1,
    created_at datetime DEFAULT current_timestamp(),
    updated_at datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
    PRIMARY KEY (id),
    UNIQUE KEY uniq_pricing_tiers_slug (slug),
    KEY idx_pricing_tiers_active (is_active),
    KEY idx_pricing_tiers_skill_level (skill_level)
);

ALTER TABLE caretaker_profiles
    ADD COLUMN IF NOT EXISTS pricing_tier_id bigint NULL AFTER hourly_rate,
    ADD COLUMN IF NOT EXISTS pricing_override_enabled tinyint(1) NOT NULL DEFAULT 0 AFTER payout_priority,
    ADD INDEX IF NOT EXISTS idx_caretaker_pricing_tier_id (pricing_tier_id),
    ADD INDEX IF NOT EXISTS idx_caretaker_pricing_override (pricing_override_enabled);

ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS pricing_tier_id bigint NULL AFTER total_amount,
    ADD COLUMN IF NOT EXISTS skill_level varchar(30) NULL AFTER pricing_tier,
    ADD INDEX IF NOT EXISTS idx_booking_pricing_tier_id (pricing_tier_id),
    ADD INDEX IF NOT EXISTS idx_booking_skill_level (skill_level);

INSERT INTO pricing_tiers
    (name, slug, description, skill_level, customer_hourly_rate, caretaker_hourly_rate, platform_commission_hourly, commission_percentage, is_active)
SELECT 'Basic', 'basic', 'Entry-level elder care support', 'beginner', 180.00, 130.00, 50.00, ROUND((50.00 / 180.00) * 100, 2), 1
WHERE NOT EXISTS (SELECT 1 FROM pricing_tiers);

INSERT INTO pricing_tiers
    (name, slug, description, skill_level, customer_hourly_rate, caretaker_hourly_rate, platform_commission_hourly, commission_percentage, is_active)
SELECT 'Standard', 'standard', 'Experienced daily care support', 'intermediate', 250.00, 190.00, 60.00, ROUND((60.00 / 250.00) * 100, 2), 1
WHERE (SELECT COUNT(*) FROM pricing_tiers) = 1
  AND NOT EXISTS (SELECT 1 FROM pricing_tiers WHERE slug = 'standard');

INSERT INTO pricing_tiers
    (name, slug, description, skill_level, customer_hourly_rate, caretaker_hourly_rate, platform_commission_hourly, commission_percentage, is_active)
SELECT 'Professional', 'professional', 'Advanced elder care provider', 'advanced', 350.00, 280.00, 70.00, ROUND((70.00 / 350.00) * 100, 2), 1
WHERE (SELECT COUNT(*) FROM pricing_tiers) = 2
  AND NOT EXISTS (SELECT 1 FROM pricing_tiers WHERE slug = 'professional');

INSERT INTO pricing_tiers
    (name, slug, description, skill_level, customer_hourly_rate, caretaker_hourly_rate, platform_commission_hourly, commission_percentage, is_active)
SELECT 'Medical', 'medical', 'Expert care for medical-support needs', 'expert', 550.00, 450.00, 100.00, ROUND((100.00 / 550.00) * 100, 2), 1
WHERE (SELECT COUNT(*) FROM pricing_tiers) = 3
  AND NOT EXISTS (SELECT 1 FROM pricing_tiers WHERE slug = 'medical');
