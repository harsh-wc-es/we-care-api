ALTER TABLE caretaker_profiles
    ADD COLUMN IF NOT EXISTS pricing_tier varchar(30) NULL AFTER hourly_rate,
    ADD COLUMN IF NOT EXISTS skill_level varchar(30) NULL AFTER pricing_tier,
    ADD COLUMN IF NOT EXISTS customer_hourly_rate decimal(10,2) NOT NULL DEFAULT 0.00 AFTER skill_level,
    ADD COLUMN IF NOT EXISTS caretaker_hourly_rate decimal(10,2) NOT NULL DEFAULT 0.00 AFTER customer_hourly_rate,
    ADD COLUMN IF NOT EXISTS platform_commission_hourly decimal(10,2) NOT NULL DEFAULT 0.00 AFTER caretaker_hourly_rate,
    ADD COLUMN IF NOT EXISTS commission_percentage decimal(5,2) NOT NULL DEFAULT 0.00 AFTER platform_commission_hourly,
    ADD COLUMN IF NOT EXISTS payout_priority int(11) NOT NULL DEFAULT 0 AFTER commission_percentage,
    ADD INDEX IF NOT EXISTS idx_caretaker_pricing_tier (pricing_tier),
    ADD INDEX IF NOT EXISTS idx_caretaker_skill_level (skill_level);

ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS pricing_tier varchar(30) NULL AFTER total_amount,
    ADD COLUMN IF NOT EXISTS customer_hourly_rate decimal(10,2) NOT NULL DEFAULT 0.00 AFTER pricing_tier,
    ADD COLUMN IF NOT EXISTS caretaker_hourly_rate decimal(10,2) NOT NULL DEFAULT 0.00 AFTER customer_hourly_rate,
    ADD COLUMN IF NOT EXISTS platform_commission_hourly decimal(10,2) NOT NULL DEFAULT 0.00 AFTER caretaker_hourly_rate,
    ADD COLUMN IF NOT EXISTS total_customer_amount decimal(10,2) NOT NULL DEFAULT 0.00 AFTER platform_commission_hourly,
    ADD COLUMN IF NOT EXISTS caretaker_earning_amount decimal(10,2) NOT NULL DEFAULT 0.00 AFTER total_customer_amount,
    ADD COLUMN IF NOT EXISTS platform_commission_amount decimal(10,2) NOT NULL DEFAULT 0.00 AFTER caretaker_earning_amount,
    ADD COLUMN IF NOT EXISTS total_hours decimal(6,2) NOT NULL DEFAULT 0.00 AFTER platform_commission_amount,
    ADD INDEX IF NOT EXISTS idx_booking_pricing_tier (pricing_tier),
    ADD INDEX IF NOT EXISTS idx_booking_caretaker_earning (caretaker_earning_amount);

ALTER TABLE caretaker_payouts
    ADD COLUMN IF NOT EXISTS gross_customer_amount decimal(10,2) NOT NULL DEFAULT 0.00 AFTER amount,
    ADD COLUMN IF NOT EXISTS total_caretaker_earnings decimal(10,2) NOT NULL DEFAULT 0.00 AFTER gross_customer_amount,
    ADD COLUMN IF NOT EXISTS total_platform_commission decimal(10,2) NOT NULL DEFAULT 0.00 AFTER total_caretaker_earnings;

UPDATE bookings
SET total_customer_amount = CASE WHEN total_customer_amount = 0 THEN COALESCE(total_amount, 0) ELSE total_customer_amount END,
    caretaker_earning_amount = CASE WHEN caretaker_earning_amount = 0 THEN COALESCE(total_amount, 0) ELSE caretaker_earning_amount END,
    platform_commission_amount = CASE WHEN platform_commission_amount = 0 THEN 0 ELSE platform_commission_amount END
WHERE COALESCE(total_amount, 0) > 0;

UPDATE caretaker_payouts
SET gross_customer_amount = CASE WHEN gross_customer_amount = 0 THEN COALESCE(amount, 0) ELSE gross_customer_amount END,
    total_caretaker_earnings = CASE WHEN total_caretaker_earnings = 0 THEN COALESCE(amount, 0) ELSE total_caretaker_earnings END,
    total_platform_commission = CASE WHEN total_platform_commission = 0 THEN 0 ELSE total_platform_commission END
WHERE COALESCE(amount, 0) > 0;
